"""Clinic-admin management of staff-to-patient care-team assignments."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.care_team_assignment import CareTeamAssignment
from app.repositories.audit_events import AuditEventRepository
from app.repositories.care_team import CareTeamRepository
from app.repositories.patients import PatientRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.users import UserRepository
from app.schemas.care_team import CareTeamAssignmentCreate


router = APIRouter(prefix="/auth/clinics/{clinic_id}/care-team/assignments", tags=["Care Team"])


@router.get("")
async def list_staff_assignments(
    clinic_id: UUID,
    patient_id: UUID | None = None,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    if patient_id is not None and PatientRepository(context.db).get_in_clinic(clinic_id, patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    rows = CareTeamRepository(context.db).list_assignments(clinic_id, patient_id)
    return [
        {
            "id": assignment.id,
            "clinic_id": assignment.clinic_id,
            "patient_id": assignment.patient_id,
            "staff_member_id": assignment.staff_member_id,
            "assignment_role": assignment.assignment_role,
            "assigned_at": assignment.assigned_at,
            "staff_name": staff.full_name,
            "staff_role": staff.role,
        }
        for assignment, staff in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def assign_staff_to_patient(
    clinic_id: UUID,
    body: CareTeamAssignmentCreate,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    patient = PatientRepository(context.db).get_in_clinic(clinic_id, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    staff = StaffMemberRepository(context.db).get_for_clinic(clinic_id, body.staff_member_id)
    if staff is None or not staff.is_active:
        raise HTTPException(status_code=404, detail="Active staff member not found in this clinic.")
    if staff.role not in {"doctor", "nurse"}:
        raise HTTPException(status_code=422, detail="Care-team assignments are limited to doctors and nurses.")
    user = UserRepository(context.db).get(staff.auth_user_id)
    membership = MembershipRepository(context.db).get_for_user_and_clinic(staff.auth_user_id, clinic_id)
    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
        or membership is None
        or membership.status != "active"
        or membership.role != staff.role
    ):
        raise HTTPException(status_code=409, detail="This staff account is not active in the clinic.")
    assignments = CareTeamRepository(context.db)
    if assignments.has_assignment(clinic_id, patient.id, staff.id):
        raise HTTPException(status_code=409, detail="This staff member is already assigned to the patient.")

    assignment = CareTeamAssignment(
        clinic_id=clinic_id,
        patient_id=patient.id,
        staff_member_id=staff.id,
        assignment_role=staff.role,
    )
    assignments.add(assignment)
    try:
        context.db.flush()
        AuditEventRepository(context.db).record(
            clinic_id=clinic_id,
            actor_user_id=context.user.id,
            patient_id=patient.id,
            action="patient.care_team.assigned",
            resource_type="care_team_assignment",
            resource_id=str(assignment.id),
            details={"source": "clinic_access", "staff_member_id": str(staff.id)},
        )
        context.db.commit()
    except IntegrityError as exc:
        context.db.rollback()
        raise HTTPException(status_code=409, detail="Could not create the care-team assignment.") from exc
    return {
        "id": assignment.id,
        "clinic_id": clinic_id,
        "patient_id": patient.id,
        "staff_member_id": staff.id,
        "assignment_role": assignment.assignment_role,
        "assigned_at": assignment.assigned_at,
    }


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_staff_assignment(
    clinic_id: UUID,
    assignment_id: UUID,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    assignments = CareTeamRepository(context.db)
    assignment = assignments.get(clinic_id, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Care-team assignment not found.")
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=assignment.patient_id,
        action="patient.care_team.unassigned",
        resource_type="care_team_assignment",
        resource_id=str(assignment.id),
        details={"source": "clinic_access", "staff_member_id": str(assignment.staff_member_id)},
    )
    assignments.delete(assignment)
    context.db.commit()
