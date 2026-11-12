"""Self-service patient portal endpoints."""

import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.appointment import Appointment
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.models.waitlist_entry import WaitlistEntry
from app.repositories.appointments import AppointmentRepository
from app.repositories.care_team import CareTeamRepository
from app.repositories.clinic_setup import ClinicSetupRepository
from app.repositories.clinics import ClinicRepository
from app.repositories.patient_portal import PatientPortalRepository
from app.repositories.patients import PatientRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.waitlist import WaitlistRepository
from app.schemas.patient_portal import (
    AppointmentBookingRequest,
    AppointmentCancelRequest,
    AppointmentRescheduleRequest,
    PortalDoctorRead,
    PortalMessageRecipientRead,
    PortalAppointmentRead,
    PortalMessageCreate,
    PortalMessageRead,
)
from app.schemas.waitlist import WaitlistJoinRequest, WaitlistRead
from app.services.scheduling_service import booking_fingerprint, validate_booking


router = APIRouter(prefix="/auth/clinics/{clinic_id}/portal", tags=["Patient Portal"])
PATIENT_MUTABLE_APPOINTMENT_STATUSES = {"scheduled", "booked", "confirmed", "requested"}


def _get_linked_patient(clinic_id: UUID, context: AuthContext):
    membership = next(
        (
            item for item in context.memberships
            if item.clinic_id == clinic_id and item.role == "patient" and item.status == "active"
        ),
        None,
    )
    if membership is None or membership.patient_id is None:
        raise HTTPException(status_code=403, detail="This patient account is not linked to a patient record.")
    patient = PatientRepository(context.db).get_in_clinic(clinic_id, membership.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient record not found.")
    return patient


def _audit_portal_action(
    repository: PatientPortalRepository,
    *,
    clinic_id: UUID,
    patient_id: UUID,
    context: AuthContext,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
) -> None:
    repository.add_access_audit(
        clinic_id=clinic_id,
        patient_id=patient_id,
        actor_user_id=context.user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def _triage_message(body: str) -> str:
    text = re.sub(r"\s+", " ", body.casefold())
    emergency_terms = (
        "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
        "unconscious", "not breathing", "severe bleeding", "overdose", "suicid",
        "stroke", "seizure", "anaphylaxis",
    )
    if any(term in text for term in emergency_terms):
        return "emergency"
    urgent_terms = (
        "side effect", "dizzy", "dizziness", "dazy", "dazed", "drowsy", "sleepy",
        "lightheaded", "reaction", "worsening", "severe pain", "high fever",
        "medicine makes", "medication makes",
    )
    if any(term in text for term in urgent_terms):
        return "urgent"
    administrative_terms = ("billing", "insurance", "receipt", "clinic hours", "address")
    if any(term in text for term in administrative_terms):
        return "administrative"
    return "routine"


def _waitlist_data(entry: WaitlistEntry, offered_appointment: Appointment | None = None) -> dict:
    return {
        "id": entry.id,
        "clinic_id": entry.clinic_id,
        "patient_id": entry.patient_id,
        "requested_staff_member_id": entry.requested_staff_member_id,
        "earliest_at": entry.earliest_at,
        "latest_at": entry.latest_at,
        "reason": entry.reason,
        "status": entry.status,
        "offered_appointment_id": entry.offered_appointment_id,
        "appointment_id": entry.appointment_id,
        "offered_at": entry.offered_at,
        "offer_expires_at": entry.offer_expires_at,
        "offered_starts_at": offered_appointment.starts_at if offered_appointment else None,
        "offered_ends_at": offered_appointment.ends_at if offered_appointment else None,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


@router.get("/me")
async def get_my_patient_portal(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = PatientPortalRepository(context.db)
    records = repository.get_records(clinic_id, patient.id)
    _audit_portal_action(
        repository,
        clinic_id=clinic_id,
        patient_id=patient.id,
        context=context,
        action="patient.portal.read",
        resource_type="patient_portal",
    )
    context.db.commit()

    return {
        "patient": {
            "id": patient.id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth,
            "sex": patient.sex,
            "phone": patient.phone,
            "email": patient.email,
            "address": patient.address,
            "emergency_contact_name": patient.emergency_contact_name,
            "emergency_contact_phone": patient.emergency_contact_phone,
        },
        "appointments": [
            {
                "id": item.id,
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
                "status": item.status,
                "reason": item.reason,
            }
            for item in records.appointments
        ],
        "allergies": [
            {
                "id": item.id,
                "substance": item.substance,
                "reaction": item.reaction,
                "severity": item.severity,
                "status": item.status,
            }
            for item in records.allergies
        ],
        "medications": [
            {
                "id": item.id,
                "name": item.name,
                "dose": item.dose,
                "route": item.route,
                "frequency": item.frequency,
                "status": item.status,
                "start_date": item.start_date,
                "end_date": item.end_date,
            }
            for item in records.medications
        ],
        "signed_notes": [
            {
                "id": item.id,
                "visit_id": item.visit_id,
                "content": item.content,
                "signed_at": item.signed_at,
            }
            for item in records.signed_notes
        ],
        "signed_orders": [
            {
                "id": item.id,
                "visit_id": item.visit_id,
                "order_type": item.order_type,
                "status": item.status,
                "details": item.details,
                "notes": item.notes,
                "signed_at": item.signed_at,
                "created_at": item.created_at,
            }
            for item in records.signed_orders
        ],
    }


@router.get("/appointments", response_model=list[PortalAppointmentRead])
async def list_my_appointments(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = PatientPortalRepository(context.db)
    appointments = repository.list_appointments(clinic_id, patient.id)
    _audit_portal_action(
        repository, clinic_id=clinic_id, patient_id=patient.id, context=context,
        action="patient.portal.appointments.read", resource_type="appointment_collection",
    )
    context.db.commit()
    return appointments


@router.get("/waitlist", response_model=list[WaitlistRead])
async def list_my_waitlist_entries(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = WaitlistRepository(context.db)
    entries = repository.list_for_patient(clinic_id, patient.id)
    _audit_portal_action(
        PatientPortalRepository(context.db), clinic_id=clinic_id, patient_id=patient.id,
        context=context, action="patient.portal.waitlist.read", resource_type="waitlist_collection",
    )
    context.db.commit()
    return [
        _waitlist_data(entry, context.db.query(Appointment).filter_by(
            clinic_id=clinic_id, id=entry.offered_appointment_id,
        ).first() if entry.offered_appointment_id else None)
        for entry in entries
    ]


@router.post("/waitlist", response_model=WaitlistRead, status_code=status.HTTP_201_CREATED)
async def join_waitlist(
    clinic_id: UUID,
    body: WaitlistJoinRequest,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    now = datetime.now(timezone.utc)
    if body.earliest_at <= now:
        raise HTTPException(status_code=422, detail="Waitlist window must start in the future.")
    if body.requested_staff_member_id and CareTeamRepository(context.db).get_assigned_doctor(
        clinic_id, patient.id, body.requested_staff_member_id,
    ) is None:
        raise HTTPException(status_code=403, detail="You can wait for a doctor assigned to your care team.")
    repository = WaitlistRepository(context.db)
    if repository.has_open_entry(clinic_id, patient.id):
        raise HTTPException(status_code=409, detail="You already have an active waitlist request for this clinic.")
    entry = WaitlistEntry(
        clinic_id=clinic_id,
        patient_id=patient.id,
        requested_staff_member_id=body.requested_staff_member_id,
        earliest_at=body.earliest_at,
        latest_at=body.latest_at,
        reason=body.reason.strip() if body.reason else None,
        status="waiting",
    )
    repository.add(entry)
    context.db.flush()
    _audit_portal_action(
        PatientPortalRepository(context.db), clinic_id=clinic_id, patient_id=patient.id,
        context=context, action="patient.portal.waitlist.joined", resource_type="waitlist_entry",
        resource_id=str(entry.id),
    )
    context.db.commit()
    context.db.refresh(entry)
    return _waitlist_data(entry)


@router.delete("/waitlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave_waitlist(
    clinic_id: UUID,
    entry_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = WaitlistRepository(context.db)
    entry = repository.get_for_patient(clinic_id, patient.id, entry_id, for_update=True)
    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist request not found.")
    if entry.status not in {"waiting", "offered"}:
        raise HTTPException(status_code=409, detail="This waitlist request is already closed.")
    offered_appointment = None
    if entry.status == "offered" and entry.offered_appointment_id:
        offered_appointment = AppointmentRepository(context.db).get(clinic_id, entry.offered_appointment_id)
    entry.status = "cancelled"
    if offered_appointment is not None:
        repository.offer_next_for_slot(clinic_id, offered_appointment)
    _audit_portal_action(
        PatientPortalRepository(context.db), clinic_id=clinic_id, patient_id=patient.id,
        context=context, action="patient.portal.waitlist.cancelled", resource_type="waitlist_entry",
        resource_id=str(entry.id),
    )
    context.db.commit()


@router.post("/waitlist/{entry_id}/accept", response_model=PortalAppointmentRead, status_code=status.HTTP_201_CREATED)
async def accept_waitlist_offer(
    clinic_id: UUID,
    entry_id: UUID,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    entries = WaitlistRepository(context.db)
    entry = entries.get_for_patient(clinic_id, patient.id, entry_id, for_update=True)
    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist request not found.")
    if entry.status == "booked" and entry.appointment_id:
        booked = AppointmentRepository(context.db).get(clinic_id, entry.appointment_id)
        if booked is not None:
            response.status_code = status.HTTP_200_OK
            return booked
    if entry.status != "offered" or entry.offered_appointment_id is None:
        raise HTTPException(status_code=409, detail="This waitlist entry has no active slot offer.")
    slot = AppointmentRepository(context.db).get(clinic_id, entry.offered_appointment_id)
    if slot is None or slot.status != "cancelled":
        entry.status = "expired"
        context.db.commit()
        raise HTTPException(status_code=409, detail="The offered appointment slot is no longer available.")
    if entry.offer_expires_at is None or entry.offer_expires_at <= datetime.now(timezone.utc):
        entry.status = "expired"
        entries.offer_next_for_slot(clinic_id, slot)
        context.db.commit()
        raise HTTPException(status_code=409, detail="This slot offer has expired. A new offer will be sent if another slot opens.")

    appointments = AppointmentRepository(context.db)
    if appointments.lock_patient(clinic_id, patient.id) is None:
        raise HTTPException(status_code=404, detail="Patient record not found.")
    doctor = next((item for item in ClinicSetupRepository(context.db).list_active_doctors(clinic_id)
                   if item.id == slot.assigned_staff_id), None)
    if doctor is None or CareTeamRepository(context.db).get_assigned_doctor(clinic_id, patient.id, doctor.id) is None:
        raise HTTPException(status_code=403, detail="The offered doctor is no longer assigned to your care team.")
    if appointments.lock_staff(clinic_id, doctor.id) is None:
        raise HTTPException(status_code=409, detail="The offered doctor is no longer active.")
    if slot.room_id and appointments.lock_room(clinic_id, slot.room_id) is None:
        slot.room_id = None
    fingerprint = booking_fingerprint(
        patient_id=patient.id, starts_at=slot.starts_at, ends_at=slot.ends_at,
        assigned_staff_id=doctor.id, room_id=slot.room_id, reason=entry.reason,
    )
    existing = appointments.get_by_idempotency_key(clinic_id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for another request.")
        response.status_code = status.HTTP_200_OK
        return existing
    validate_booking(
        ClinicSetupRepository(context.db), ClinicRepository(context.db).get(clinic_id),
        starts_at=slot.starts_at, ends_at=slot.ends_at, staff_member_id=doctor.id,
        patient_id=patient.id, room_id=slot.room_id,
    )
    appointment = Appointment(
        clinic_id=clinic_id, patient_id=patient.id, assigned_staff_id=doctor.id,
        room_id=slot.room_id, idempotency_key=idempotency_key,
        request_fingerprint=fingerprint, starts_at=slot.starts_at, ends_at=slot.ends_at,
        reason=entry.reason, status="scheduled", source="patient_waitlist",
    )
    appointments.add(appointment)
    context.db.flush()
    entry.status = "booked"
    entry.appointment_id = appointment.id
    context.db.add(OutboxEvent(
        clinic_id=clinic_id, event_type="appointment.booked",
        aggregate_type="appointment", aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(patient.id),
                 "assigned_staff_id": str(doctor.id), "source": "waitlist"},
    ))
    _audit_portal_action(
        PatientPortalRepository(context.db), clinic_id=clinic_id, patient_id=patient.id,
        context=context, action="patient.portal.waitlist.offer_accepted",
        resource_type="appointment", resource_id=str(appointment.id),
    )
    context.db.commit()
    context.db.refresh(appointment)
    return appointment


@router.post("/appointments", response_model=PortalAppointmentRead, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    clinic_id: UUID,
    body: AppointmentBookingRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    appointments = AppointmentRepository(context.db)
    if appointments.lock_patient(clinic_id, patient.id) is None:
        raise HTTPException(status_code=404, detail="Patient record not found.")
    fingerprint = booking_fingerprint(
        patient_id=patient.id, starts_at=body.starts_at, ends_at=body.ends_at,
        assigned_staff_id=body.assigned_staff_id, room_id=body.room_id, reason=body.reason,
    )
    existing = appointments.get_by_idempotency_key(clinic_id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for a different appointment request.")
        response.status_code = status.HTTP_200_OK
        return existing

    setup = ClinicSetupRepository(context.db)
    doctor = next((item for item in setup.list_active_doctors(clinic_id) if item.id == body.assigned_staff_id), None)
    if doctor is None or CareTeamRepository(context.db).get_assigned_doctor(clinic_id, patient.id, body.assigned_staff_id) is None:
        raise HTTPException(status_code=403, detail="You can book only with an active doctor assigned to your care team.")
    if appointments.lock_staff(clinic_id, doctor.id) is None:
        raise HTTPException(status_code=409, detail="The selected doctor is no longer active.")
    if body.room_id is not None and appointments.lock_room(clinic_id, body.room_id) is None:
        raise HTTPException(status_code=404, detail="Active clinic room not found.")
    clinic = ClinicRepository(context.db).get(clinic_id)
    validate_booking(setup, clinic, starts_at=body.starts_at, ends_at=body.ends_at,
                    staff_member_id=doctor.id, patient_id=patient.id, room_id=body.room_id)

    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient.id,
        assigned_staff_id=doctor.id,
        room_id=body.room_id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        reason=body.reason,
        status="scheduled",
        source="patient_portal",
    )
    appointments.add(appointment)
    portal_repository = PatientPortalRepository(context.db)
    portal_repository.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.booked",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(patient.id),
                 "assigned_staff_id": str(doctor.id), "room_id": str(body.room_id) if body.room_id else None},
    ))
    _audit_portal_action(
        portal_repository, clinic_id=clinic_id, patient_id=patient.id, context=context,
        action="patient.portal.appointment.booked", resource_type="appointment",
        resource_id=str(appointment.id),
    )
    try:
        context.db.flush()
        context.db.commit()
    except IntegrityError as exc:
        context.db.rollback()
        duplicate = appointments.get_by_idempotency_key(clinic_id, idempotency_key)
        if duplicate is not None and duplicate.request_fingerprint == fingerprint:
            response.status_code = status.HTTP_200_OK
            return duplicate
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for a different appointment request.") from exc
        raise HTTPException(status_code=409, detail="Appointment could not be booked because a scheduling constraint changed.") from exc
    context.db.refresh(appointment)
    return appointment


@router.patch("/appointments/{appointment_id}/reschedule", response_model=PortalAppointmentRead)
async def reschedule_appointment(
    clinic_id: UUID,
    appointment_id: UUID,
    body: AppointmentRescheduleRequest,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    appointments = AppointmentRepository(context.db)
    if appointments.lock_patient(clinic_id, patient.id) is None:
        raise HTTPException(status_code=404, detail="Patient record not found.")
    repository = PatientPortalRepository(context.db)
    appointment = repository.get_appointment(clinic_id, patient.id, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if appointment.status.casefold() not in PATIENT_MUTABLE_APPOINTMENT_STATUSES:
        raise HTTPException(status_code=409, detail="This appointment cannot be rescheduled.")
    setup = ClinicSetupRepository(context.db)
    doctor = next((item for item in setup.list_active_doctors(clinic_id) if item.id == body.assigned_staff_id), None)
    if doctor is None or CareTeamRepository(context.db).get_assigned_doctor(clinic_id, patient.id, body.assigned_staff_id) is None:
        raise HTTPException(status_code=403, detail="You can book only with an active doctor assigned to your care team.")
    if appointments.lock_staff(clinic_id, doctor.id) is None:
        raise HTTPException(status_code=409, detail="The selected doctor is no longer active.")
    if body.room_id is not None and appointments.lock_room(clinic_id, body.room_id) is None:
        raise HTTPException(status_code=404, detail="Active clinic room not found.")
    clinic = ClinicRepository(context.db).get(clinic_id)
    validate_booking(setup, clinic, starts_at=body.starts_at, ends_at=body.ends_at,
                    staff_member_id=doctor.id, patient_id=patient.id, room_id=body.room_id,
                    exclude_appointment_id=appointment.id)

    appointment.starts_at = body.starts_at
    appointment.ends_at = body.ends_at
    appointment.assigned_staff_id = doctor.id
    appointment.room_id = body.room_id
    if body.reason is not None:
        appointment.reason = body.reason
    _audit_portal_action(
        repository, clinic_id=clinic_id, patient_id=patient.id, context=context,
        action="patient.portal.appointment.rescheduled", resource_type="appointment",
        resource_id=str(appointment.id),
    )
    repository.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.rescheduled",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(patient.id),
                 "assigned_staff_id": str(doctor.id), "room_id": str(body.room_id) if body.room_id else None},
    ))
    context.db.commit()
    context.db.refresh(appointment)
    return appointment


@router.post("/appointments/{appointment_id}/cancel", response_model=PortalAppointmentRead)
async def cancel_appointment(
    clinic_id: UUID,
    appointment_id: UUID,
    body: AppointmentCancelRequest,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = PatientPortalRepository(context.db)
    appointment = repository.get_appointment(clinic_id, patient.id, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if appointment.status.casefold() not in PATIENT_MUTABLE_APPOINTMENT_STATUSES:
        raise HTTPException(status_code=409, detail="This appointment cannot be cancelled.")
    appointment.status = "cancelled"
    appointment.cancellation_reason = body.reason
    WaitlistRepository(context.db).offer_next_for_slot(clinic_id, appointment)
    _audit_portal_action(
        repository, clinic_id=clinic_id, patient_id=patient.id, context=context,
        action="patient.portal.appointment.cancelled", resource_type="appointment",
        resource_id=str(appointment.id),
    )
    repository.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.cancelled",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(patient.id)},
    ))
    context.db.commit()
    context.db.refresh(appointment)
    return appointment


@router.get("/messages", response_model=list[PortalMessageRead])
async def list_my_messages(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = PatientPortalRepository(context.db)
    messages = repository.list_messages(clinic_id, patient.id)
    _audit_portal_action(
        repository, clinic_id=clinic_id, patient_id=patient.id, context=context,
        action="patient.portal.messages.read", resource_type="message_collection",
    )
    context.db.commit()
    return messages


@router.get("/doctors", response_model=list[PortalDoctorRead])
async def list_my_assigned_doctors(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    doctors = CareTeamRepository(context.db).list_assigned_doctors(clinic_id, patient.id)
    repository = PatientPortalRepository(context.db)
    _audit_portal_action(
        repository,
        clinic_id=clinic_id,
        patient_id=patient.id,
        context=context,
        action="patient.portal.assigned_doctors.read",
        resource_type="care_team",
    )
    context.db.commit()
    return [
        {"staff_member_id": doctor.id, "full_name": doctor.full_name}
        for doctor in doctors
    ]


@router.get("/message-recipients", response_model=list[PortalMessageRecipientRead])
async def list_message_recipients(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    doctors = CareTeamRepository(context.db).list_assigned_doctors(clinic_id, patient.id)
    doctor_ids = {doctor.id for doctor in doctors}
    candidates = StaffMemberRepository(context.db).list_message_recipients(clinic_id)
    return [
        {"staff_member_id": staff.id, "full_name": staff.full_name, "role": staff.role}
        for staff in candidates
        if staff.role == "receptionist" or staff.id in doctor_ids
    ]


@router.post("/messages", response_model=PortalMessageRead, status_code=status.HTTP_201_CREATED)
async def send_patient_message(
    clinic_id: UUID,
    body: PortalMessageCreate,
    context: AuthContext = Depends(require_clinic_role("patient")),
):
    patient = _get_linked_patient(clinic_id, context)
    repository = PatientPortalRepository(context.db)
    target = StaffMemberRepository(context.db).get_for_clinic(clinic_id, body.target_staff_member_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Active clinic staff member not found.")
    if body.target_role == "doctor":
        target = CareTeamRepository(context.db).get_assigned_doctor(clinic_id, patient.id, target.id)
        if target is None:
            raise HTTPException(status_code=403, detail="You can only message a doctor assigned to your care team.")
    elif target.role != "receptionist":
        raise HTTPException(status_code=403, detail="You can message only an active clinic receptionist or assigned doctor.")
    message = Message(
        clinic_id=clinic_id,
        patient_id=patient.id,
        channel="portal",
        direction="inbound",
        body=body.body.strip(),
        status="needs_review",
        triage_level=_triage_message(body.body),
        assigned_staff_id=target.id,
    )
    repository.add(message)
    context.db.flush()
    repository.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="patient.message.received",
        aggregate_type="message",
        aggregate_id=str(message.id),
        payload={
            "message_id": str(message.id),
            "patient_id": str(patient.id),
            "target_staff_member_id": str(target.id),
            "target_role": target.role,
            "triage_level": message.triage_level,
        },
    ))
    _audit_portal_action(
        repository, clinic_id=clinic_id, patient_id=patient.id, context=context,
        action="patient.portal.message.sent", resource_type="message",
        resource_id=str(message.id),
    )
    context.db.commit()
    context.db.refresh(message)
    result = PortalMessageRead.model_validate(message).model_dump()
    result["confirmation"] = "Your message was sent to the clinic for staff review."
    if message.triage_level == "emergency":
        result["safety_notice"] = (
            "If you may be in immediate danger, contact your local emergency service now. "
            "Your message has been marked urgent for clinic staff."
        )
    return result
