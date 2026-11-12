"""Clinic-admin membership, invitation, and access-removal endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import AuthContext, require_clinic_role
from app.repositories.memberships import MembershipRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.users import UserRepository
from app.schemas.admin import DeleteUserRequest
from app.schemas.clinic import InvitationRequest
from app.services.account_service import (
    CLINIC_ADMIN_ROLES,
    MEMBER_ROLES,
    membership_data,
    profile_data,
    provision_invited_member,
)


router = APIRouter(prefix="/auth/clinics/{clinic_id}", tags=["Clinic Access"])


@router.get("/members")
async def list_members(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    rows = MembershipRepository(context.db).list_clinic_members(clinic_id)
    return [
        {**membership_data(membership), "user": profile_data(user)}
        for membership, user in rows
    ]


@router.get("/membership")
async def get_my_membership(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role(*MEMBER_ROLES)),
):
    if context.user.is_super_admin:
        return {"clinic_id": clinic_id, "role": "super_admin", "status": "active"}
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id),
        None,
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Clinic membership not found.")
    return membership_data(membership)


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def invite_member(
    clinic_id: UUID,
    body: InvitationRequest,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    allowed_roles = MEMBER_ROLES if context.user.is_super_admin else CLINIC_ADMIN_ROLES
    return await provision_invited_member(
        db=context.db,
        clinic_id=clinic_id,
        inviter=context.user,
        request=body,
        allowed_roles=allowed_roles,
    )


@router.delete("/members/{user_id}")
async def remove_member(
    clinic_id: UUID,
    user_id: UUID,
    body: DeleteUserRequest,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    memberships = MembershipRepository(context.db)
    staff_members = StaffMemberRepository(context.db)
    membership = memberships.get_for_user_and_clinic(user_id, clinic_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Clinic membership not found.")
    if str(body.confirm_email).strip().lower() != membership.user.email.lower():
        raise HTTPException(status_code=422, detail="confirm_email must match the member's email.")
    if membership.user_id == context.user.id:
        raise HTTPException(status_code=409, detail="You cannot remove your own clinic access.")
    if membership.role == "clinic_admin" and not context.user.is_super_admin:
        raise HTTPException(status_code=403, detail="Only a super admin may remove a clinic admin.")
    if membership.user.is_super_admin:
        raise HTTPException(status_code=403, detail="Super admin accounts cannot be removed from a clinic here.")

    staff = staff_members.get_for_user(clinic_id, user_id)
    if staff is not None:
        staff_members.delete(staff)
    memberships.delete(membership)
    context.db.commit()
    return {"clinic_id": str(clinic_id), "user_id": str(user_id), "status": "removed_from_clinic"}


@router.post("/members/{user_id}/restore")
async def restore_member_account(
    clinic_id: UUID,
    user_id: UUID,
    body: DeleteUserRequest,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    membership = MembershipRepository(context.db).get_for_user_and_clinic(user_id, clinic_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Clinic membership not found.")
    user = UserRepository(context.db).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.is_super_admin:
        raise HTTPException(status_code=403, detail="Super admin accounts cannot be restored through clinic access.")
    if str(body.confirm_email).strip().lower() != user.email.lower():
        raise HTTPException(status_code=422, detail="confirm_email must match the user's email.")
    if user.deleted_at is None:
        raise HTTPException(status_code=409, detail="This account is not deleted.")

    user.deleted_at = None
    user.deleted_by_user_id = None
    user.is_active = user.is_active_before_delete if user.is_active_before_delete is not None else True
    user.is_active_before_delete = None
    context.db.commit()
    return profile_data(user)
