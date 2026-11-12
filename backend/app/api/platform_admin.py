"""Super-admin endpoints for tenant and account administration."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import AuthContext, require_platform_admin
from app.repositories.clinics import ClinicRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.users import UserRepository
from app.schemas.admin import DeleteClinicRequest
from app.services.account_service import membership_data, profile_data


router = APIRouter(prefix="/auth/platform", tags=["Platform Administration"])


@router.get("/users")
async def list_users(
    search: str | None = Query(default=None, max_length=150),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_platform_admin),
):
    users = UserRepository(context.db).list_all(
        search=search, is_active=is_active, limit=limit, offset=offset
    )
    return [profile_data(user) for user in users]


@router.get("/users/{user_id}")
async def get_user(user_id: UUID, context: AuthContext = Depends(require_platform_admin)):
    user = UserRepository(context.db).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    memberships = MembershipRepository(context.db).list_for_user(user.id)
    return {
        "profile": profile_data(user),
        "memberships": [membership_data(item) for item in memberships],
    }


@router.get("/clinics")
async def list_clinics(
    search: str | None = Query(default=None, max_length=150),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_platform_admin),
):
    clinics = ClinicRepository(context.db).list_all(
        search=search, is_active=is_active, limit=limit, offset=offset
    )
    return [
        {
            "id": clinic.id,
            "name": clinic.name,
            "slug": clinic.slug,
            "email": clinic.email,
            "is_active": clinic.is_active,
            "deleted_at": clinic.deleted_at,
        }
        for clinic in clinics
    ]


@router.get("/clinics/{clinic_id}")
async def get_clinic(clinic_id: UUID, context: AuthContext = Depends(require_platform_admin)):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=404, detail="Clinic not found.")
    members = MembershipRepository(context.db).list_clinic_members(clinic_id)
    return {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "email": clinic.email,
        "phone": clinic.phone,
        "timezone": clinic.timezone,
        "is_active": clinic.is_active,
        "deleted_at": clinic.deleted_at,
        "created_at": clinic.created_at,
        "member_count": len(members),
    }


@router.get("/clinics/{clinic_id}/members")
async def list_clinic_members(
    clinic_id: UUID,
    context: AuthContext = Depends(require_platform_admin),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=404, detail="Clinic not found.")
    return [
        {"profile": profile_data(user), "membership": membership_data(membership)}
        for membership, user in MembershipRepository(context.db).list_clinic_members(clinic_id)
    ]


@router.delete("/clinics/{clinic_id}")
async def delete_clinic(
    clinic_id: UUID,
    body: DeleteClinicRequest,
    context: AuthContext = Depends(require_platform_admin),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=404, detail="Clinic not found.")
    if body.confirm_clinic_name.strip().casefold() != clinic.name.strip().casefold():
        raise HTTPException(status_code=422, detail="confirm_clinic_name must match the clinic name.")
    if clinic.deleted_at is not None:
        raise HTTPException(status_code=409, detail="This clinic is already deleted.")

    clinic.is_active_before_delete = clinic.is_active
    clinic.is_active = False
    clinic.deleted_at = datetime.now(timezone.utc)
    clinic.deleted_by_user_id = context.user.id
    context.db.commit()
    return {"id": clinic.id, "name": clinic.name, "deleted_at": clinic.deleted_at}


@router.post("/clinics/{clinic_id}/restore")
async def restore_clinic(
    clinic_id: UUID,
    body: DeleteClinicRequest,
    context: AuthContext = Depends(require_platform_admin),
):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=404, detail="Clinic not found.")
    if body.confirm_clinic_name.strip().casefold() != clinic.name.strip().casefold():
        raise HTTPException(status_code=422, detail="confirm_clinic_name must match the clinic name.")
    if clinic.deleted_at is None:
        raise HTTPException(status_code=409, detail="This clinic is not deleted.")
    clinic.deleted_at = None
    clinic.deleted_by_user_id = None
    clinic.is_active = clinic.is_active_before_delete if clinic.is_active_before_delete is not None else True
    clinic.is_active_before_delete = None
    context.db.commit()
    return {"id": clinic.id, "name": clinic.name, "is_active": clinic.is_active}
