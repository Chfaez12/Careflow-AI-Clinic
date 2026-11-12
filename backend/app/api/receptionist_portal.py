"""Receptionist schedule, check-in, and waiting-room APIs."""

import asyncio
import json
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import ACCESS_COOKIE, AuthContext, require_clinic_role
from app.db import SessionLocal
from app.models.appointment import Appointment
from app.models.outbox_event import OutboxEvent
from app.models.visit import Visit
from app.repositories.appointments import AppointmentRepository
from app.repositories.audit_events import AuditEventRepository
from app.repositories.clinics import ClinicRepository
from app.repositories.clinic_setup import ClinicSetupRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.waitlist import WaitlistRepository
from app.repositories.visits import VisitRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.users import UserRepository
from app.schemas.receptionist_portal import (
    AppointmentCancel,
    ReceptionAppointmentCreate,
    ReceptionAppointmentRead,
    ReceptionAppointmentReschedule,
    WaitingRoomItem,
)
from app.schemas.waitlist import StaffWaitlistRead
from app.services.scheduling_service import booking_fingerprint, validate_booking
from app.services.auth_service import get_supabase_user


router = APIRouter(prefix="/auth/clinics/{clinic_id}/reception", tags=["Receptionist Portal"])
EDITABLE_APPOINTMENT_STATUSES = {"scheduled", "booked", "confirmed", "requested"}


def _get_receptionist(clinic_id: UUID, context: AuthContext):
    staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff is None or not staff.is_active or staff.role != "receptionist":
        raise HTTPException(status_code=403, detail="An active receptionist profile is required.")
    return staff


def _get_day_bounds(clinic_id: UUID, context: AuthContext, requested_day: date | None):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    try:
        zone = ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    day = requested_day or datetime.now(zone).date()
    return datetime.combine(day, time.min, tzinfo=zone), datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)


@router.get("/waitlist", response_model=list[StaffWaitlistRead])
async def get_reception_waitlist(
    clinic_id: UUID,
    include_closed: bool = Query(default=False),
    context: AuthContext = Depends(require_clinic_role("receptionist", "clinic_admin")),
):
    if not context.user.is_super_admin:
        membership = next((item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"), None)
        if membership is None or membership.role == "receptionist":
            staff = _get_receptionist(clinic_id, context)
        elif membership.role != "clinic_admin":
            raise HTTPException(status_code=403, detail="Receptionist or clinic admin access required.")
    rows = WaitlistRepository(context.db).list_for_clinic(clinic_id, include_closed=include_closed)
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="scheduling.waitlist.read",
        resource_type="waitlist_collection",
        details={"include_closed": include_closed, "result_count": len(rows)},
    )
    context.db.commit()
    return [
        {
            "id": entry.id,
            "patient_id": entry.patient_id,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "requested_staff_member_id": entry.requested_staff_member_id,
            "earliest_at": entry.earliest_at,
            "latest_at": entry.latest_at,
            "reason": entry.reason,
            "status": entry.status,
            "offered_starts_at": offered_slot.starts_at if offered_slot else None,
            "created_at": entry.created_at,
        }
        for entry, patient, offered_slot in rows
    ]


def _appointment_data(appointment: Appointment, patient) -> dict:
    return {
        "id": appointment.id,
        "patient_id": patient.id,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "assigned_staff_id": appointment.assigned_staff_id,
        "room_id": appointment.room_id,
        "starts_at": appointment.starts_at,
        "ends_at": appointment.ends_at,
        "status": appointment.status,
        "reason": appointment.reason,
        "source": appointment.source,
    }


def _validate_assigned_doctor(repository: AppointmentRepository, clinic_id: UUID, staff_member_id: UUID | None):
    if staff_member_id is None:
        return None
    staff = repository.staff_for_clinic(clinic_id, staff_member_id)
    if staff is None or staff.role != "doctor":
        raise HTTPException(status_code=404, detail="Active doctor not found in this clinic.")
    user = UserRepository(repository.session).get(staff.auth_user_id)
    membership = MembershipRepository(repository.session).get_for_user_and_clinic(staff.auth_user_id, clinic_id)
    if (
        user is None or not user.is_active or user.deleted_at is not None
        or membership is None or membership.status != "active" or membership.role != "doctor"
    ):
        raise HTTPException(status_code=409, detail="This doctor account is not active in the clinic.")
    return staff


@router.get("/dashboard")
async def receptionist_dashboard(
    clinic_id: UUID,
    day: date | None = Query(default=None),
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    starts_at, ends_at = _get_day_bounds(clinic_id, context, day)
    rows = AppointmentRepository(context.db).list_for_period(clinic_id, starts_at, ends_at)
    for appointment, patient in rows:
        AuditEventRepository(context.db).record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=patient.id,
            action="appointment.read_by_reception",
            resource_type="appointment",
            resource_id=str(appointment.id),
            details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
        )
    context.db.commit()
    counts: dict[str, int] = {}
    for appointment, _ in rows:
        counts[appointment.status] = counts.get(appointment.status, 0) + 1
    return {
        "staff_member_id": staff.id,
        "day": starts_at.date(),
        "appointment_counts": counts,
        "appointments": [_appointment_data(appointment, patient) for appointment, patient in rows],
    }


@router.get("/appointments", response_model=list[ReceptionAppointmentRead])
async def list_reception_appointments(
    clinic_id: UUID,
    day: date | None = Query(default=None),
    appointment_status: str | None = Query(default=None, alias="status", max_length=30),
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    starts_at, ends_at = _get_day_bounds(clinic_id, context, day)
    rows = AppointmentRepository(context.db).list_for_period(
        clinic_id, starts_at, ends_at, status=appointment_status
    )
    for appointment, patient in rows:
        AuditEventRepository(context.db).record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=patient.id,
            action="appointment.read_by_reception",
            resource_type="appointment",
            resource_id=str(appointment.id),
            details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
        )
    context.db.commit()
    return [_appointment_data(appointment, patient) for appointment, patient in rows]


@router.post("/appointments", response_model=ReceptionAppointmentRead, status_code=status.HTTP_201_CREATED)
async def create_reception_appointment(
    clinic_id: UUID,
    body: ReceptionAppointmentCreate,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    repository = AppointmentRepository(context.db)
    if not repository.patient_exists(clinic_id, body.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    doctor = _validate_assigned_doctor(repository, clinic_id, body.assigned_staff_id)
    if repository.lock_patient(clinic_id, body.patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    fingerprint = booking_fingerprint(patient_id=body.patient_id, starts_at=body.starts_at, ends_at=body.ends_at,
                                      assigned_staff_id=doctor.id if doctor else None,
                                      room_id=body.room_id, reason=body.reason)
    existing = repository.get_by_idempotency_key(clinic_id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for a different appointment request.")
        response.status_code = status.HTTP_200_OK
        patient = repository.get_patient(clinic_id, existing.patient_id)
        return _appointment_data(existing, patient)
    if doctor is not None and repository.lock_staff(clinic_id, doctor.id) is None:
        raise HTTPException(status_code=409, detail="The selected doctor is no longer active.")
    if body.room_id is not None and repository.lock_room(clinic_id, body.room_id) is None:
        raise HTTPException(status_code=404, detail="Active clinic room not found.")
    setup = ClinicSetupRepository(context.db)
    clinic = ClinicRepository(context.db).get(clinic_id)
    validate_booking(setup, clinic, starts_at=body.starts_at, ends_at=body.ends_at,
                    staff_member_id=doctor.id if doctor else None, patient_id=body.patient_id,
                    room_id=body.room_id)
    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=body.patient_id,
        assigned_staff_id=doctor.id if doctor else None,
        room_id=body.room_id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        reason=body.reason,
        status="scheduled",
        source="staff",
    )
    repository.add(appointment)
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.booked",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(body.patient_id),
                 "assigned_staff_id": str(appointment.assigned_staff_id) if appointment.assigned_staff_id else None,
                 "room_id": str(appointment.room_id) if appointment.room_id else None},
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=body.patient_id,
        action="appointment.created_by_reception",
        resource_type="appointment",
        resource_id=str(appointment.id),
        details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
    )
    try:
        context.db.flush()
        context.db.commit()
    except IntegrityError as exc:
        context.db.rollback()
        duplicate = repository.get_by_idempotency_key(clinic_id, idempotency_key)
        if duplicate is not None and duplicate.request_fingerprint == fingerprint:
            response.status_code = status.HTTP_200_OK
            patient = repository.get_patient(clinic_id, duplicate.patient_id)
            return _appointment_data(duplicate, patient)
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for a different appointment request.") from exc
        raise HTTPException(status_code=409, detail="Appointment could not be booked because a scheduling constraint changed.") from exc
    context.db.refresh(appointment)
    patient = repository.get_patient(clinic_id, body.patient_id)
    return _appointment_data(appointment, patient)


@router.patch("/appointments/{appointment_id}/reschedule", response_model=ReceptionAppointmentRead)
async def reschedule_reception_appointment(
    clinic_id: UUID,
    appointment_id: UUID,
    body: ReceptionAppointmentReschedule,
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    repository = AppointmentRepository(context.db)
    appointment = repository.get_for_update(clinic_id, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found in this clinic.")
    if appointment.status.casefold() not in EDITABLE_APPOINTMENT_STATUSES:
        raise HTTPException(status_code=409, detail="This appointment can no longer be rescheduled.")
    values = body.model_dump(exclude_unset=True)
    assigned_id = values.get("assigned_staff_id", appointment.assigned_staff_id)
    doctor = _validate_assigned_doctor(repository, clinic_id, assigned_id)
    if repository.lock_patient(clinic_id, appointment.patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    if doctor is not None and repository.lock_staff(clinic_id, doctor.id) is None:
        raise HTTPException(status_code=409, detail="The selected doctor is no longer active.")
    room_id = values.get("room_id", appointment.room_id)
    if room_id is not None and repository.lock_room(clinic_id, room_id) is None:
        raise HTTPException(status_code=404, detail="Active clinic room not found.")
    validate_booking(ClinicSetupRepository(context.db), ClinicRepository(context.db).get(clinic_id),
                    starts_at=body.starts_at, ends_at=body.ends_at,
                    staff_member_id=doctor.id if doctor else None,
                    patient_id=appointment.patient_id, room_id=room_id,
                    exclude_appointment_id=appointment.id)
    appointment.starts_at = body.starts_at
    appointment.ends_at = body.ends_at
    appointment.assigned_staff_id = doctor.id if doctor else None
    appointment.room_id = room_id
    if "reason" in values:
        appointment.reason = body.reason
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.rescheduled",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(appointment.patient_id),
                 "assigned_staff_id": str(appointment.assigned_staff_id) if appointment.assigned_staff_id else None,
                 "room_id": str(appointment.room_id) if appointment.room_id else None},
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=appointment.patient_id,
        action="appointment.rescheduled_by_reception",
        resource_type="appointment",
        resource_id=str(appointment.id),
        details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    context.db.refresh(appointment)
    patient = repository.get_patient(clinic_id, appointment.patient_id)
    return _appointment_data(appointment, patient)


@router.post("/appointments/{appointment_id}/cancel", response_model=ReceptionAppointmentRead)
async def cancel_reception_appointment(
    clinic_id: UUID,
    appointment_id: UUID,
    body: AppointmentCancel,
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    repository = AppointmentRepository(context.db)
    appointment = repository.get_for_update(clinic_id, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found in this clinic.")
    if appointment.status.casefold() not in EDITABLE_APPOINTMENT_STATUSES:
        raise HTTPException(status_code=409, detail="This appointment can no longer be cancelled.")
    appointment.status = "cancelled"
    appointment.cancellation_reason = body.reason
    WaitlistRepository(context.db).offer_next_for_slot(clinic_id, appointment)
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.cancelled",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "patient_id": str(appointment.patient_id)},
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=appointment.patient_id,
        action="appointment.cancelled_by_reception",
        resource_type="appointment",
        resource_id=str(appointment.id),
        details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    context.db.refresh(appointment)
    patient = repository.get_patient(clinic_id, appointment.patient_id)
    return _appointment_data(appointment, patient)


@router.post("/appointments/{appointment_id}/check-in")
async def check_in_appointment(
    clinic_id: UUID,
    appointment_id: UUID,
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    appointments = AppointmentRepository(context.db)
    appointment = appointments.get_for_update(clinic_id, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found in this clinic.")
    visits = VisitRepository(context.db)
    existing_visit = visits.get_for_appointment(clinic_id, appointment.id)
    if existing_visit is not None:
        return {"appointment_id": appointment.id, "visit_id": existing_visit.id,
                "appointment_status": appointment.status, "visit_status": existing_visit.status}
    if appointment.status.casefold() not in EDITABLE_APPOINTMENT_STATUSES:
        raise HTTPException(status_code=409, detail="This appointment cannot be checked in.")

    appointment.status = "arrived"
    visit = Visit(
        clinic_id=clinic_id,
        patient_id=appointment.patient_id,
        appointment_id=appointment.id,
        clinician_staff_id=appointment.assigned_staff_id,
        status="arrived",
    )
    visits.add(visit)
    context.db.flush()
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="appointment.arrived",
        aggregate_type="appointment",
        aggregate_id=str(appointment.id),
        payload={"appointment_id": str(appointment.id), "visit_id": str(visit.id)},
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=appointment.patient_id,
        action="appointment.checked_in",
        resource_type="appointment",
        resource_id=str(appointment.id),
        details={"source": "receptionist_portal", "visit_id": str(visit.id), "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    return {"appointment_id": appointment.id, "visit_id": visit.id,
            "appointment_status": appointment.status, "visit_status": visit.status}


@router.get("/waiting-room", response_model=list[WaitingRoomItem])
async def get_waiting_room(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    rows = VisitRepository(context.db).list_waiting_room(clinic_id)
    for visit, patient in rows:
        AuditEventRepository(context.db).record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=patient.id,
            action="waiting_room.read",
            resource_type="visit",
            resource_id=str(visit.id),
            details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
        )
    context.db.commit()
    return [
        {
            "visit_id": visit.id,
            "appointment_id": visit.appointment_id,
            "patient_id": patient.id,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "status": visit.status,
            "started_at": visit.started_at,
        }
        for visit, patient in rows
    ]


@router.websocket("/waiting-room/live")
async def live_waiting_room(websocket: WebSocket, clinic_id: UUID):
    await websocket.accept()
    token = websocket.cookies.get(ACCESS_COOKIE)
    if not token:
        await websocket.close(code=4401, reason="Authentication required.")
        return
    try:
        auth_user = await get_supabase_user(token)
        user_id = UUID(auth_user["id"])
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired session.")
        return

    with SessionLocal() as db:
        profile = UserRepository(db).get(user_id)
        clinic = ClinicRepository(db).get(clinic_id)
        memberships = MembershipRepository(db).list_for_user(user_id)
        has_access = bool(profile and profile.is_active and profile.deleted_at is None and clinic and clinic.is_active)
        has_access = has_access and (
            profile.is_super_admin
            or any(m.clinic_id == clinic_id and m.status == "active" and m.role in {"clinic_admin", "receptionist"} for m in memberships)
        )
    if not has_access:
        await websocket.close(code=4403, reason="Receptionist or clinic admin access required.")
        return

    last_payload = None
    try:
        while True:
            with SessionLocal() as db:
                rows = VisitRepository(db).list_waiting_room(clinic_id)
                payload = [
                    {
                        "visit_id": str(visit.id),
                        "appointment_id": str(visit.appointment_id) if visit.appointment_id else None,
                        "patient_id": str(patient.id),
                        "patient_name": f"{patient.first_name} {patient.last_name}",
                        "status": visit.status,
                        "started_at": visit.started_at.isoformat(),
                    }
                    for visit, patient in rows
                ]
            encoded = json.dumps(payload, separators=(",", ":"))
            if encoded != last_payload:
                await websocket.send_text(encoded)
                last_payload = encoded
                with SessionLocal() as db:
                    for visit, patient in rows:
                        AuditEventRepository(db).record(
                            clinic_id=clinic_id,
                            actor_user_id=user_id,
                            patient_id=patient.id,
                            action="waiting_room.live.read",
                            resource_type="visit",
                            resource_id=str(visit.id),
                            details={"source": "waiting_room_websocket", "purpose": "front_desk_workflow"},
                        )
                    db.commit()
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@router.post("/visits/{visit_id}/move-to-room")
async def move_visit_to_room(
    clinic_id: UUID,
    visit_id: UUID,
    context: AuthContext = Depends(require_clinic_role("receptionist")),
):
    staff = _get_receptionist(clinic_id, context)
    visit = VisitRepository(context.db).get(clinic_id, visit_id)
    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found in this clinic.")
    if visit.status != "arrived":
        raise HTTPException(status_code=409, detail="Only an arrived visit can be moved into a room.")
    visit.status = "in_room"
    if visit.appointment_id is not None:
        appointment = AppointmentRepository(context.db).get(clinic_id, visit.appointment_id)
        if appointment is not None:
            appointment.status = "in_room"
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="visit.in_room",
        aggregate_type="visit",
        aggregate_id=str(visit.id),
        payload={"visit_id": str(visit.id), "patient_id": str(visit.patient_id)},
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=visit.patient_id,
        action="waiting_room.visit_moved_to_room",
        resource_type="visit",
        resource_id=str(visit.id),
        details={"source": "receptionist_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    return {"visit_id": visit.id, "status": visit.status}
