"""Billing staff claim dashboard and claim-preparation APIs."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.claim import Claim
from app.models.outbox_event import OutboxEvent
from app.repositories.audit_events import AuditEventRepository
from app.repositories.claims import ClaimRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.visits import VisitRepository
from app.schemas.billing_portal import ClaimCreate, ClaimList, ClaimListItem, ClaimRead, ClaimUpdate


router = APIRouter(prefix="/auth/clinics/{clinic_id}/billing", tags=["Billing Portal"])


def _get_billing_staff(clinic_id: UUID, context: AuthContext):
    staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff is None or not staff.is_active or staff.role != "billing_staff":
        raise HTTPException(status_code=403, detail="An active billing staff profile is required.")
    return staff


def _claim_list_item(claim: Claim, patient) -> dict:
    return {**ClaimRead.model_validate(claim).model_dump(), "patient_name": f"{patient.first_name} {patient.last_name}"}


@router.get("/dashboard")
async def billing_dashboard(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    staff = _get_billing_staff(clinic_id, context)
    summary = ClaimRepository(context.db).summary(clinic_id)
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="billing.dashboard.read",
        resource_type="billing_dashboard",
        details={"source": "billing_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    return {"staff_member_id": staff.id, **summary}


@router.get("/claims", response_model=ClaimList)
async def list_claims(
    clinic_id: UUID,
    claim_status: str | None = Query(default=None, alias="status", max_length=30),
    search: str | None = Query(default=None, max_length=150),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    staff = _get_billing_staff(clinic_id, context)
    rows = ClaimRepository(context.db).list_for_clinic(
        clinic_id,
        status=claim_status,
        search=search,
        limit=limit + 1,
        offset=offset,
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    for claim, _ in rows:
        AuditEventRepository(context.db).record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=claim.patient_id,
            action="claim.read_by_billing",
            resource_type="claim",
            resource_id=str(claim.id),
            details={"source": "billing_portal", "staff_member_id": str(staff.id)},
        )
    context.db.commit()
    return {
        "items": [_claim_list_item(claim, patient) for claim, patient in rows],
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.get("/eligible-visits")
async def list_claimable_visits(
    clinic_id: UUID,
    search: str | None = Query(default=None, max_length=150),
    limit: int = Query(default=100, ge=1, le=200),
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    """Return clinic visits with a signed note that do not already have an active claim."""
    staff = _get_billing_staff(clinic_id, context)
    rows = VisitRepository(context.db).list_billable(clinic_id, search=search, limit=limit)
    for visit, patient in rows:
        AuditEventRepository(context.db).record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=patient.id,
            action="billing.eligible_visit.read",
            resource_type="visit",
            resource_id=str(visit.id),
            details={"staff_member_id": str(staff.id)},
        )
    context.db.commit()
    return [{
        "visit_id": visit.id,
        "patient_id": patient.id,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "started_at": visit.started_at,
        "status": visit.status,
        "chief_complaint": visit.chief_complaint,
    } for visit, patient in rows]


@router.post("/claims", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
async def create_claim(
    clinic_id: UUID,
    body: ClaimCreate,
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    staff = _get_billing_staff(clinic_id, context)
    visits = VisitRepository(context.db)
    visit = visits.get(clinic_id, body.visit_id)
    if visit is None or visit.patient_id != body.patient_id:
        raise HTTPException(status_code=404, detail="Visit was not found for this patient in the clinic.")
    if not visits.has_signed_note(clinic_id, visit.id):
        raise HTTPException(status_code=409, detail="A signed clinical note is required before drafting a claim.")
    claim = Claim(
        clinic_id=clinic_id,
        patient_id=body.patient_id,
        visit_id=visit.id,
        payer_name=body.payer_name,
        diagnosis_codes=body.diagnosis_codes,
        procedure_codes=body.procedure_codes,
        amount=body.amount,
        status="draft",
    )
    ClaimRepository(context.db).add(claim)
    context.db.flush()
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=claim.patient_id,
        action="claim.created_by_billing",
        resource_type="claim",
        resource_id=str(claim.id),
        details={"source": "billing_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    context.db.refresh(claim)
    return claim


@router.get("/claims/{claim_id}", response_model=ClaimRead)
async def get_claim(
    clinic_id: UUID,
    claim_id: UUID,
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    staff = _get_billing_staff(clinic_id, context)
    claim = ClaimRepository(context.db).get(clinic_id, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found in this clinic.")
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=claim.patient_id,
        action="claim.read_by_billing",
        resource_type="claim",
        resource_id=str(claim.id),
        details={"source": "billing_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    return claim


@router.patch("/claims/{claim_id}", response_model=ClaimRead)
async def update_claim(
    clinic_id: UUID,
    claim_id: UUID,
    body: ClaimUpdate,
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    staff = _get_billing_staff(clinic_id, context)
    claim = ClaimRepository(context.db).get(clinic_id, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found in this clinic.")
    if claim.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected claims can be edited.")
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Provide at least one claim field to update.")
    for key, value in values.items():
        setattr(claim, key, value)
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=claim.patient_id,
        action="claim.updated_by_billing",
        resource_type="claim",
        resource_id=str(claim.id),
        details={"source": "billing_portal", "fields": sorted(values), "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    context.db.refresh(claim)
    return claim


@router.post("/claims/{claim_id}/submit", response_model=ClaimRead)
async def submit_claim(
    clinic_id: UUID,
    claim_id: UUID,
    context: AuthContext = Depends(require_clinic_role("billing_staff")),
):
    staff = _get_billing_staff(clinic_id, context)
    repository = ClaimRepository(context.db)
    claim = repository.get(clinic_id, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found in this clinic.")
    if claim.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="This claim has already been queued or submitted.")
    if claim.visit_id is None or not VisitRepository(context.db).has_signed_note(clinic_id, claim.visit_id):
        raise HTTPException(status_code=409, detail="A signed clinical note is required before submitting a claim.")
    claim.status = "queued"
    claim.rejection_reason = None
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="claim.submission.requested",
        aggregate_type="claim",
        aggregate_id=str(claim.id),
        payload={"claim_id": str(claim.id), "patient_id": str(claim.patient_id)},
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=claim.patient_id,
        action="claim.queued_for_submission",
        resource_type="claim",
        resource_id=str(claim.id),
        details={"source": "billing_portal", "staff_member_id": str(staff.id)},
    )
    context.db.commit()
    context.db.refresh(claim)
    return claim
