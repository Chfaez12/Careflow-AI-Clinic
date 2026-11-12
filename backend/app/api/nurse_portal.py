"""Nurse dashboard and vital-observation APIs."""

from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.patient_vital import PatientVital
from app.repositories.appointments import AppointmentRepository
from app.repositories.audit_events import AuditEventRepository
from app.repositories.care_team import CareTeamRepository
from app.repositories.clinics import ClinicRepository
from app.repositories.patient_portal import PatientPortalRepository
from app.repositories.patients import PatientRepository
from app.repositories.patient_vitals import PatientVitalRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.visits import VisitRepository
from app.schemas.nurse_portal import VitalCreate, VitalRead


router = APIRouter(prefix="/auth/clinics/{clinic_id}/nurse", tags=["Nurse Portal"])


def _get_nurse_staff(clinic_id: UUID, context: AuthContext):
    staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff is None or not staff.is_active or staff.role != "nurse":
        raise HTTPException(status_code=403, detail="An active nurse profile is required.")
    return staff


def _clinic_day_bounds(clinic_id: UUID, context: AuthContext, requested_day: date | None):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    try:
        clinic_zone = ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        clinic_zone = timezone.utc
    day = requested_day or datetime.now(clinic_zone).date()
    return (
        datetime.combine(day, time.min, tzinfo=clinic_zone),
        datetime.combine(day, time.max, tzinfo=clinic_zone),
    )


@router.get("/dashboard")
async def nurse_dashboard(
    clinic_id: UUID,
    day: date | None = Query(default=None),
    context: AuthContext = Depends(require_clinic_role("nurse")),
):
    staff = _get_nurse_staff(clinic_id, context)
    assignments = CareTeamRepository(context.db)
    patients = assignments.list_patients_for_staff(clinic_id, staff.id)
    patient_ids = [patient.id for patient in patients]
    starts_at, ends_at = _clinic_day_bounds(clinic_id, context, day)
    appointment_rows = AppointmentRepository(context.db).list_for_period(
        clinic_id, starts_at, ends_at, patient_ids=patient_ids
    )
    visits = VisitRepository(context.db).list_for_patients(clinic_id, patient_ids)
    portal_repository = PatientPortalRepository(context.db)
    messages = portal_repository.list_clinic_messages(clinic_id, pending_only=True)
    for message in messages:
        portal_repository.add_access_audit(
            clinic_id=clinic_id,
            patient_id=message.patient_id,
            actor_user_id=context.user.id,
            action="patient.message.read_by_nurse",
            resource_type="message",
            resource_id=str(message.id),
            details={"source": "nurse_portal", "purpose": "care_team_review"},
        )
    audit = AuditEventRepository(context.db)
    for patient in patients:
        audit.record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=patient.id,
            action="patient.read_by_nurse_dashboard",
            resource_type="patient",
            resource_id=str(patient.id),
            details={"source": "nurse_portal", "staff_member_id": str(staff.id)},
        )
    context.db.commit()
    return {
        "staff_member_id": staff.id,
        "day": starts_at.date(),
        "assigned_patients": [
            {"id": p.id, "first_name": p.first_name, "last_name": p.last_name}
            for p in patients
        ],
        "appointments": [
            {
                "id": appointment.id,
                "patient_id": patient.id,
                "patient_name": f"{patient.first_name} {patient.last_name}",
                "starts_at": appointment.starts_at,
                "ends_at": appointment.ends_at,
                "status": appointment.status,
            }
            for appointment, patient in appointment_rows
        ],
        "active_visits": [
            {"id": visit.id, "patient_id": visit.patient_id, "status": visit.status,
             "started_at": visit.started_at}
            for visit in visits
        ],
        "messages_needing_review": [
            {"id": message.id, "patient_id": message.patient_id, "body": message.body,
             "triage_level": message.triage_level, "created_at": message.created_at}
            for message in messages
        ],
    }


@router.post("/visits/{visit_id}/vitals", response_model=VitalRead, status_code=status.HTTP_201_CREATED)
async def record_visit_vitals(
    clinic_id: UUID,
    visit_id: UUID,
    body: VitalCreate,
    context: AuthContext = Depends(require_clinic_role("nurse")),
):
    staff = _get_nurse_staff(clinic_id, context)
    visit = VisitRepository(context.db).get(clinic_id, visit_id)
    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found in this clinic.")
    if visit.status.casefold() not in {"arrived", "in_room", "in_progress"}:
        raise HTTPException(status_code=409, detail="Vitals can only be recorded for an active visit.")
    if not CareTeamRepository(context.db).has_assignment(clinic_id, visit.patient_id, staff.id):
        raise HTTPException(status_code=403, detail="This patient is not assigned to your care team.")

    observation = PatientVital(
        clinic_id=clinic_id,
        patient_id=visit.patient_id,
        visit_id=visit.id,
        recorded_by_staff_id=staff.id,
        **body.model_dump(),
    )
    repository = PatientVitalRepository(context.db)
    repository.add(observation)
    context.db.flush()
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=visit.patient_id,
        action="patient.vitals.recorded",
        resource_type="patient_vital",
        resource_id=str(observation.id),
        details={"source": "nurse_portal", "visit_id": str(visit.id)},
    )
    context.db.commit()
    context.db.refresh(observation)
    return observation


@router.get("/patients/{patient_id}/vitals", response_model=list[VitalRead])
async def get_patient_vitals(
    clinic_id: UUID,
    patient_id: UUID,
    visit_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    context: AuthContext = Depends(require_clinic_role("nurse")),
):
    staff = _get_nurse_staff(clinic_id, context)
    if not CareTeamRepository(context.db).has_assignment(clinic_id, patient_id, staff.id):
        raise HTTPException(status_code=403, detail="This patient is not assigned to your care team.")
    if PatientRepository(context.db).get_in_clinic(clinic_id, patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    observations = PatientVitalRepository(context.db).list_for_patient(
        clinic_id, patient_id, visit_id=visit_id, limit=limit
    )
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=patient_id,
        action="patient.vitals.read",
        resource_type="patient_vital_collection",
        details={"source": "nurse_portal", "visit_id": str(visit_id) if visit_id else None},
    )
    context.db.commit()
    return observations
