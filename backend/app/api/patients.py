"""Clinic-scoped patient record APIs for authorized care team members."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.care_team_assignment import CareTeamAssignment
from app.models.patient import Patient
from app.repositories.care_team import CareTeamRepository
from app.repositories.patients import PatientRepository
from app.repositories.patient_timeline import PatientTimelineRepository
from app.repositories.staff_members import StaffMemberRepository
from app.schemas.patient import PatientCreate, PatientList, PatientRead, PatientUpdate
from app.schemas.patient_timeline import PatientTimelineRead


router = APIRouter(prefix="/auth/clinics/{clinic_id}/patients", tags=["Patients"])
PATIENT_ROLES = ("clinic_admin", "doctor", "nurse", "receptionist")


def _member_role(clinic_id: UUID, context: AuthContext) -> str:
    if context.user.is_super_admin:
        return "super_admin"
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="You do not have active access to this clinic.")
    return membership.role


def _assigned_patient_ids(clinic_id: UUID, context: AuthContext) -> list[UUID] | None:
    role = _member_role(clinic_id, context)
    if role not in {"doctor", "nurse"}:
        return None
    staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff is None or not staff.is_active or staff.role != role:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
    return [patient.id for patient in CareTeamRepository(context.db).list_patients_for_staff(clinic_id, staff.id)]


def _require_patient_scope(clinic_id: UUID, patient_id: UUID, context: AuthContext) -> str:
    role = _member_role(clinic_id, context)
    if role in {"doctor", "nurse"}:
        staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
        if staff is None or not staff.is_active or staff.role != role or not CareTeamRepository(context.db).has_assignment(
            clinic_id, patient_id, staff.id
        ):
            raise HTTPException(status_code=403, detail="This patient is not assigned to your care team.")
    return role


@router.get("", response_model=PatientList)
async def list_patients(
    clinic_id: UUID,
    search: str | None = Query(default=None, max_length=150),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role(*PATIENT_ROLES)),
):
    repository = PatientRepository(context.db)
    patient_ids = _assigned_patient_ids(clinic_id, context)
    patients = repository.list_in_clinic(
        clinic_id,
        search=search,
        patient_ids=patient_ids,
        limit=limit + 1,
        offset=offset,
    )
    has_more = len(patients) > limit
    patients = patients[:limit]
    repository.add_access_audit(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="patients.list",
        resource_id=f"offset:{offset};limit:{limit}",
    )
    context.db.commit()
    return {"items": patients, "limit": limit, "offset": offset, "has_more": has_more}


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
async def create_patient(
    clinic_id: UUID,
    body: PatientCreate,
    context: AuthContext = Depends(require_clinic_role(*PATIENT_ROLES)),
):
    repository = PatientRepository(context.db)
    role = _member_role(clinic_id, context)
    values = body.model_dump()
    external_id = values.get("external_patient_id")
    if external_id and repository.external_id_exists(clinic_id, external_id):
        raise HTTPException(status_code=409, detail="This external patient ID is already used in this clinic.")

    patient = Patient(clinic_id=clinic_id, **values)
    repository.add(patient)
    context.db.flush()
    if role in {"doctor", "nurse"}:
        staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
        if staff is None or not staff.is_active:
            raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
        CareTeamRepository(context.db).add(CareTeamAssignment(
            clinic_id=clinic_id,
            patient_id=patient.id,
            staff_member_id=staff.id,
            assignment_role="primary_care",
        ))
    repository.add_access_audit(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="patient.created",
        patient_id=patient.id,
    )
    context.db.commit()
    context.db.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(
    clinic_id: UUID,
    patient_id: UUID,
    context: AuthContext = Depends(require_clinic_role(*PATIENT_ROLES)),
):
    repository = PatientRepository(context.db)
    _require_patient_scope(clinic_id, patient_id, context)
    patient = repository.get_in_clinic(clinic_id, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    repository.add_access_audit(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="patient.read",
        patient_id=patient.id,
    )
    context.db.commit()
    return patient


@router.patch("/{patient_id}", response_model=PatientRead)
async def update_patient(
    clinic_id: UUID,
    patient_id: UUID,
    body: PatientUpdate,
    context: AuthContext = Depends(require_clinic_role(*PATIENT_ROLES)),
):
    repository = PatientRepository(context.db)
    _require_patient_scope(clinic_id, patient_id, context)
    patient = repository.get_in_clinic(clinic_id, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Provide at least one patient field to update.")
    external_id = values.get("external_patient_id")
    if external_id and repository.external_id_exists(
        clinic_id,
        external_id,
        exclude_patient_id=patient.id,
    ):
        raise HTTPException(status_code=409, detail="This external patient ID is already used in this clinic.")

    for key, value in values.items():
        setattr(patient, key, value)
    repository.add_access_audit(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="patient.updated",
        patient_id=patient.id,
    )
    context.db.commit()
    context.db.refresh(patient)
    return patient


@router.get("/{patient_id}/timeline", response_model=PatientTimelineRead)
async def get_patient_timeline(
    clinic_id: UUID,
    patient_id: UUID,
    from_at: datetime | None = Query(default=None),
    to_at: datetime | None = Query(default=None),
    event_types: list[str] | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role(*PATIENT_ROLES)),
):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(status_code=422, detail="from_at must be earlier than to_at.")
    allowed_types = {"appointment", "visit", "vitals", "allergy", "condition", "clinical_note", "order", "message"}
    if event_types and any(value not in allowed_types for value in event_types):
        raise HTTPException(status_code=422, detail=f"type must be one of: {', '.join(sorted(allowed_types))}.")
    role = _require_patient_scope(clinic_id, patient_id, context)
    patient = PatientRepository(context.db).get_in_clinic(clinic_id, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    items = PatientTimelineRepository(context.db).list_items(
        clinic_id,
        patient_id,
        include_clinical=role in {"clinic_admin", "doctor"},
        include_messages=role in {"clinic_admin", "doctor", "receptionist"},
        from_at=from_at,
        to_at=to_at,
    )
    if event_types:
        requested_types = set(event_types)
        items = [item for item in items if item["event_type"] in requested_types]
    page = items[offset:offset + limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    PatientRepository(context.db).add_access_audit(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="patient.timeline.read",
        patient_id=patient_id,
        resource_id=f"offset:{offset};limit:{limit}",
    )
    context.db.commit()
    return {
        "patient_id": patient_id,
        "clinic_id": clinic_id,
        "items": page,
        "limit": limit,
        "has_more": has_more,
    }
