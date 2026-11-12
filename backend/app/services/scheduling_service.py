"""Clinic-timezone scheduling rule validation and slot generation."""

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from app.models.clinic import Clinic
from app.repositories.clinic_setup import ClinicSetupRepository


def booking_fingerprint(*, patient_id: UUID, starts_at: datetime, ends_at: datetime,
                        assigned_staff_id: UUID | None, room_id: UUID | None, reason: str | None) -> str:
    canonical = {
        "patient_id": str(patient_id),
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "assigned_staff_id": str(assigned_staff_id) if assigned_staff_id else None,
        "room_id": str(room_id) if room_id else None,
        "reason": reason,
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clinic_zone(clinic: Clinic):
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=409, detail="Clinic timezone is not a valid IANA timezone.")


def validate_booking(
    repository: ClinicSetupRepository,
    clinic: Clinic,
    *,
    starts_at: datetime,
    ends_at: datetime,
    staff_member_id: UUID | None,
    patient_id: UUID,
    room_id: UUID | None = None,
    exclude_appointment_id: UUID | None = None,
) -> None:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="Appointment times must include timezone offsets.")
    zone = clinic_zone(clinic)
    local_start, local_end = starts_at.astimezone(zone), ends_at.astimezone(zone)
    if ends_at <= starts_at:
        raise HTTPException(status_code=422, detail="Appointment end must be later than its start.")
    if local_start.date() != local_end.date():
        raise HTTPException(status_code=422, detail="Appointments must start and end on the same clinic-local day.")
    hours = repository.get_business_hour(clinic.id, local_start.weekday())
    if hours is None:
        raise HTTPException(status_code=409, detail="Clinic business hours have not been configured for this day.")
    if hours.is_closed or local_start.time().replace(tzinfo=None) < hours.opens_at or local_end.time().replace(tzinfo=None) > hours.closes_at:
        raise HTTPException(status_code=409, detail="Appointment is outside the clinic's business hours.")

    if staff_member_id is not None:
        rules = repository.list_availability_for_date(clinic.id, staff_member_id, local_start.date())
        if not any(rule.starts_at <= local_start.time().replace(tzinfo=None) and rule.ends_at >= local_end.time().replace(tzinfo=None) for rule in rules):
            raise HTTPException(status_code=409, detail="The selected doctor is not available for this interval.")
    if room_id is not None:
        room = repository.get_room(clinic.id, room_id)
        if room is None or not room.is_active:
            raise HTTPException(status_code=404, detail="Active clinic room not found.")
    if repository.overlaps(
        clinic.id, starts_at, ends_at,
        staff_member_id=staff_member_id,
        room_id=room_id,
        patient_id=patient_id,
        exclude_appointment_id=exclude_appointment_id,
    ):
        raise HTTPException(status_code=409, detail="Patient, doctor, or room already has an appointment during this interval.")


def available_slots(repository: ClinicSetupRepository, clinic: Clinic, *, staff_member_id: UUID, day: date, duration_minutes: int):
    zone = clinic_zone(clinic)
    hours = repository.get_business_hour(clinic.id, day.weekday())
    if hours is None or hours.is_closed or hours.opens_at is None or hours.closes_at is None:
        return []
    rules = repository.list_availability_for_date(clinic.id, staff_member_id, day)
    rooms = repository.list_rooms(clinic.id, active_only=True)
    starts = datetime.combine(day, time.min, tzinfo=zone)
    ends = starts + timedelta(days=1)
    from app.models.appointment import Appointment
    existing = repository.session.query(Appointment).filter(
        Appointment.clinic_id == clinic.id,
        Appointment.starts_at < ends,
        Appointment.ends_at > starts,
        Appointment.status.notin_(("cancelled", "completed", "no_show", "void")),
    ).all()
    step = timedelta(minutes=duration_minutes)
    result = []
    now = datetime.now(timezone.utc)
    for rule in rules:
        candidate = datetime.combine(day, rule.starts_at, tzinfo=zone)
        rule_end = datetime.combine(day, rule.ends_at, tzinfo=zone)
        while candidate + step <= rule_end:
            candidate_end = candidate + step
            if candidate.astimezone(timezone.utc) > now and candidate.time() >= hours.opens_at and candidate_end.time() <= hours.closes_at:
                conflict = any(
                    appointment.assigned_staff_id == staff_member_id
                    and appointment.starts_at < candidate_end.astimezone(timezone.utc)
                    and appointment.ends_at > candidate.astimezone(timezone.utc)
                    for appointment in existing
                )
                free_rooms = [room.id for room in rooms if not any(
                    appointment.room_id == room.id
                    and appointment.starts_at < candidate_end.astimezone(timezone.utc)
                    and appointment.ends_at > candidate.astimezone(timezone.utc)
                    for appointment in existing
                )]
                if not conflict and (not rooms or free_rooms):
                    result.append({
                        "starts_at": candidate.astimezone(timezone.utc),
                        "ends_at": candidate_end.astimezone(timezone.utc),
                        "available_room_ids": free_rooms,
                    })
            candidate += step
    return list({slot["starts_at"]: slot for slot in result}.values())
