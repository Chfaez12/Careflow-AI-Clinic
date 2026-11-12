"""Availability search for clinic staff and patient appointment booking."""

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import AuthContext, require_clinic_role
from app.repositories.appointments import AppointmentRepository
from app.repositories.audit_events import AuditEventRepository
from app.repositories.care_team import CareTeamRepository
from app.repositories.clinic_setup import ClinicSetupRepository
from app.repositories.clinics import ClinicRepository
from app.repositories.memberships import MembershipRepository
from app.services.scheduling_service import available_slots, clinic_zone
from app.schemas.scheduling import NoShowPredictionList


router = APIRouter(prefix="/auth/clinics/{clinic_id}/scheduling", tags=["Scheduling"])


@router.get("/doctors")
async def list_bookable_doctors(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient", "clinic_admin", "receptionist")),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    setup = ClinicSetupRepository(context.db)
    membership = MembershipRepository(context.db).get_for_user_and_clinic(context.user.id, clinic_id)
    if membership is not None and membership.role == "patient":
        if membership.patient_id is None:
            raise HTTPException(status_code=403, detail="Patient membership is not linked to a patient record.")
        doctors = CareTeamRepository(context.db).list_assigned_doctors(clinic_id, membership.patient_id)
    else:
        doctors = setup.list_active_doctors(clinic_id)
    return [{"staff_member_id": doctor.id, "full_name": doctor.full_name} for doctor in doctors]


@router.get("/rooms")
async def list_available_rooms(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("patient", "clinic_admin", "receptionist")),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    return [{"id": room.id, "name": room.name, "room_type": room.room_type}
            for room in ClinicSetupRepository(context.db).list_rooms(clinic_id, active_only=True)]


@router.get("/doctors/{staff_member_id}/slots")
async def list_doctor_slots(
    clinic_id: UUID,
    staff_member_id: UUID,
    day: date = Query(...),
    duration_minutes: int = Query(default=30, ge=5, le=240),
    context: AuthContext = Depends(require_clinic_role("patient", "clinic_admin", "receptionist")),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    zone = clinic_zone(clinic)
    if day < datetime.now(zone).date():
        raise HTTPException(status_code=422, detail="Availability can be requested only for today or a future day.")
    setup = ClinicSetupRepository(context.db)
    doctor = next((item for item in setup.list_active_doctors(clinic_id) if item.id == staff_member_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Active doctor not found in this clinic.")
    membership = MembershipRepository(context.db).get_for_user_and_clinic(context.user.id, clinic_id)
    if membership is not None and membership.role == "patient":
        if membership.patient_id is None or CareTeamRepository(context.db).get_assigned_doctor(
            clinic_id, membership.patient_id, staff_member_id
        ) is None:
            raise HTTPException(status_code=403, detail="You can request availability only for a doctor assigned to your care team.")
    slots = available_slots(setup, clinic, staff_member_id=staff_member_id, day=day, duration_minutes=duration_minutes)
    return {"clinic_id": clinic_id, "doctor_id": doctor.id, "day": day,
            "duration_minutes": duration_minutes, "slots": slots}


@router.get("/no-show-predictions", response_model=NoShowPredictionList)
async def get_no_show_predictions(
    clinic_id: UUID,
    day: date = Query(...),
    context: AuthContext = Depends(require_clinic_role("clinic_admin", "receptionist")),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    zone = clinic_zone(clinic)
    if day < datetime.now(zone).date():
        raise HTTPException(status_code=422, detail="Predictions are available only for today or a future day.")
    starts_at = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    ends_at = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    repository = AppointmentRepository(context.db)
    rows = repository.list_for_period(clinic_id, starts_at, ends_at)
    predictions = []
    eligible = {"scheduled", "booked", "confirmed", "requested"}
    for appointment, patient in rows:
        if appointment.status not in eligible:
            continue
        prior_no_shows = repository.count_no_shows_for_patient(
            clinic_id,
            patient.id,
            before=starts_at,
        )
        risk = min(12 + 23 * prior_no_shows, 81)
        band = "low" if risk < 30 else "moderate" if risk < 60 else "high"
        factors = [
            f"{prior_no_shows} prior no-show(s) recorded for this patient in this clinic."
            if prior_no_shows
            else "No previous no-shows recorded for this patient in this clinic."
        ]
        predictions.append({
            "appointment_id": appointment.id,
            "patient_id": patient.id,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "starts_at": appointment.starts_at,
            "status": appointment.status,
            "risk_percent": risk,
            "risk_band": band,
            "factors": factors,
        })

    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="scheduling.no_show_predictions.read",
        resource_type="no_show_prediction_list",
        resource_id=day.isoformat(),
        details={"source": "rule_based_demo", "appointment_count": len(predictions)},
    )
    context.db.commit()
    return {"clinic_id": clinic_id, "day": day, "items": predictions}
