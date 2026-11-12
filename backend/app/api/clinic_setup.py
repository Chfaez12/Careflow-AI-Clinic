"""Clinic profile, onboarding, hours, rooms and doctor availability APIs."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.clinic_room import ClinicRoom
from app.models.doctor_availability import DoctorAvailability
from app.repositories.audit_events import AuditEventRepository
from app.repositories.appointments import AppointmentRepository
from app.repositories.clinic_setup import ClinicSetupRepository
from app.repositories.clinics import ClinicRepository
from app.repositories.staff_members import StaffMemberRepository
from app.schemas.clinic_setup import (
    BusinessHoursReplace,
    ClinicProfileUpdate,
    DoctorAvailabilityCreate,
    DoctorAvailabilityRead,
    RoomCreate,
    RoomRead,
    RoomUpdate,
)


router = APIRouter(prefix="/auth/clinics/{clinic_id}/setup", tags=["Clinic Setup"])


def _clinic(clinic_id: UUID, context: AuthContext):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    return clinic


def _audit(context: AuthContext, clinic_id: UUID, action: str, resource_type: str, resource_id: UUID | None = None):
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details={"source": "clinic_setup_api"},
    )


@router.get("/profile")
async def get_clinic_setup_profile(clinic_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    clinic = _clinic(clinic_id, context)
    return {"id": clinic.id, "name": clinic.name, "slug": clinic.slug, "email": clinic.email,
            "phone": clinic.phone, "address": clinic.address, "timezone": clinic.timezone}


@router.patch("/profile")
async def update_clinic_setup_profile(clinic_id: UUID, body: ClinicProfileUpdate, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    clinic = _clinic(clinic_id, context)
    values = body.model_dump(exclude_unset=True)
    if any(key in values and values[key] is None for key in ("name", "timezone")):
        raise HTTPException(status_code=422, detail="Clinic name and timezone cannot be cleared.")
    if "timezone" in values and values["timezone"]:
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="timezone must be a valid IANA timezone name.") from exc
    for key, value in values.items():
        setattr(clinic, key, value)
    _audit(context, clinic_id, "clinic.setup.profile_updated", "clinic", clinic_id)
    context.db.commit()
    context.db.refresh(clinic)
    return {"id": clinic.id, "name": clinic.name, "slug": clinic.slug, "email": clinic.email,
            "phone": clinic.phone, "address": clinic.address, "timezone": clinic.timezone}


@router.get("/onboarding")
async def get_clinic_onboarding_status(clinic_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    clinic = _clinic(clinic_id, context)
    repository = ClinicSetupRepository(context.db)
    hours = repository.list_business_hours(clinic_id)
    counts = repository.setup_counts(clinic_id)
    checks = {
        "clinic_profile": bool(clinic.name and clinic.phone and clinic.address and clinic.timezone),
        "business_hours": len(hours) == 7,
        "active_doctor": counts["doctors"] > 0,
        "doctor_availability": counts["availability_rules"] > 0,
        "room_configured": counts["rooms"] > 0,
        "patient_record_imported": counts.get("imported_jobs", 0) > 0,
    }
    _audit(context, clinic_id, "clinic.setup.onboarding_read", "clinic_onboarding")
    context.db.commit()
    return {"complete": all(checks[key] for key in ("clinic_profile", "business_hours", "active_doctor", "doctor_availability")),
            "checklist": checks, "counts": counts}


@router.get("/appointments")
async def list_setup_appointments(
    clinic_id: UUID,
    day: date | None = None,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    clinic = _clinic(clinic_id, context)
    try:
        zone = ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    selected_day = day or datetime.now(zone).date()
    starts_at = datetime.combine(selected_day, time.min, tzinfo=zone)
    ends_at = starts_at + timedelta(days=1)
    rows = AppointmentRepository(context.db).list_for_period(clinic_id, starts_at, ends_at)
    _audit(context, clinic_id, "clinic.setup.appointments_read", "appointment_collection")
    context.db.commit()
    return [
        {
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
        for appointment, patient in rows
    ]


@router.get("/business-hours")
async def get_business_hours(clinic_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    return ClinicSetupRepository(context.db).list_business_hours(clinic_id)


@router.put("/business-hours")
async def replace_business_hours(clinic_id: UUID, body: BusinessHoursReplace, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    repository = ClinicSetupRepository(context.db)
    repository.replace_business_hours(clinic_id, [item.model_dump() for item in body.days])
    _audit(context, clinic_id, "clinic.setup.business_hours_updated", "business_hours")
    context.db.commit()
    return repository.list_business_hours(clinic_id)


@router.get("/rooms", response_model=list[RoomRead])
async def list_clinic_rooms(clinic_id: UUID, include_inactive: bool = False, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    return ClinicSetupRepository(context.db).list_rooms(clinic_id, active_only=not include_inactive)


@router.post("/rooms", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_clinic_room(clinic_id: UUID, body: RoomCreate, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    room = ClinicRoom(clinic_id=clinic_id, name=body.name.strip(), room_type=body.room_type)
    repository = ClinicSetupRepository(context.db)
    repository.add_room(room)
    try:
        context.db.flush()
        _audit(context, clinic_id, "clinic.setup.room_created", "clinic_room", room.id)
        context.db.commit()
    except IntegrityError as exc:
        context.db.rollback()
        raise HTTPException(status_code=409, detail="A room with this name already exists in the clinic.") from exc
    context.db.refresh(room)
    return room


@router.patch("/rooms/{room_id}", response_model=RoomRead)
async def update_clinic_room(clinic_id: UUID, room_id: UUID, body: RoomUpdate, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    repository = ClinicSetupRepository(context.db)
    room = repository.get_room(clinic_id, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found in this clinic.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(room, key, value.strip() if key == "name" and value else value)
    try:
        _audit(context, clinic_id, "clinic.setup.room_updated", "clinic_room", room.id)
        context.db.commit()
    except IntegrityError as exc:
        context.db.rollback()
        raise HTTPException(status_code=409, detail="A room with this name already exists in the clinic.") from exc
    context.db.refresh(room)
    return room


@router.get("/doctors")
async def list_setup_doctors(clinic_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    return [{"staff_member_id": doctor.id, "full_name": doctor.full_name, "email": doctor.email}
            for doctor in ClinicSetupRepository(context.db).list_active_doctors(clinic_id)]


@router.get("/doctor-availability", response_model=list[DoctorAvailabilityRead])
async def list_doctor_availability(clinic_id: UUID, staff_member_id: UUID | None = None, context: AuthContext = Depends(require_clinic_role("clinic_admin", "doctor"))):
    _clinic(clinic_id, context)
    if not context.user.is_super_admin:
        membership = next((item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"), None)
        if membership and membership.role == "doctor":
            doctor = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
            if doctor is None or not doctor.is_active or (staff_member_id and staff_member_id != doctor.id):
                raise HTTPException(status_code=403, detail="Doctors can view only their own availability.")
            staff_member_id = doctor.id
    return ClinicSetupRepository(context.db).list_availability(clinic_id, staff_member_id=staff_member_id)


@router.post("/doctor-availability", response_model=DoctorAvailabilityRead, status_code=status.HTTP_201_CREATED)
async def create_doctor_availability(clinic_id: UUID, body: DoctorAvailabilityCreate, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    setup = ClinicSetupRepository(context.db)
    doctor = next((item for item in setup.list_active_doctors(clinic_id) if item.id == body.staff_member_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Active doctor not found in this clinic.")
    hours = setup.get_business_hour(clinic_id, body.weekday)
    if hours is None or hours.is_closed or body.starts_at < hours.opens_at or body.ends_at > hours.closes_at:
        raise HTTPException(status_code=409, detail="Availability must fit within the clinic's business hours for that weekday.")
    for current in setup.list_availability(clinic_id, staff_member_id=doctor.id):
        date_ranges_overlap = (current.effective_to is None or current.effective_to >= body.effective_from) and (body.effective_to is None or body.effective_to >= current.effective_from)
        time_ranges_overlap = body.starts_at < current.ends_at and body.ends_at > current.starts_at
        if current.is_active and current.weekday == body.weekday and date_ranges_overlap and time_ranges_overlap:
            raise HTTPException(status_code=409, detail="This availability overlaps an existing rule for the doctor.")
    availability = DoctorAvailability(clinic_id=clinic_id, **body.model_dump())
    setup.add_availability(availability)
    try:
        context.db.flush()
        _audit(context, clinic_id, "clinic.setup.doctor_availability_created", "doctor_availability", availability.id)
        context.db.commit()
    except IntegrityError as exc:
        context.db.rollback()
        raise HTTPException(status_code=409, detail="This doctor availability rule already exists.") from exc
    context.db.refresh(availability)
    return availability


@router.delete("/doctor-availability/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_doctor_availability(clinic_id: UUID, availability_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    _clinic(clinic_id, context)
    availability = ClinicSetupRepository(context.db).get_availability(clinic_id, availability_id)
    if availability is None:
        raise HTTPException(status_code=404, detail="Doctor availability rule not found in this clinic.")
    availability.is_active = False
    _audit(context, clinic_id, "clinic.setup.doctor_availability_deactivated", "doctor_availability", availability.id)
    context.db.commit()
