from dataclasses import dataclass
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.clinic_membership import ClinicMembership
from app.models.user import UserProfile
from app.repositories.clinics import ClinicRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.users import UserRepository
from app.services.auth_service import get_supabase_user


bearer_scheme = HTTPBearer(auto_error=False)
ACCESS_COOKIE = "careflow_access_token"


@dataclass
class AuthContext:
    user: UserProfile
    memberships: list[ClinicMembership]
    db: Session
    access_token: str


async def get_current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_cookie: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
    db: Session = Depends(get_db),
) -> AuthContext:
    access_token = (
        credentials.credentials
        if credentials is not None and credentials.scheme.lower() == "bearer"
        else access_cookie
    )
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_user = await get_supabase_user(access_token)
    try:
        user_id = UUID(auth_user["id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authenticated user.") from exc

    profile = UserRepository(db).get(user_id)
    if profile is None:
        raise HTTPException(status_code=403, detail="CareFlow account is not provisioned.")
    if profile.deleted_at is not None:
        raise HTTPException(status_code=403, detail="This CareFlow account has been deleted.")
    if not profile.is_active:
        raise HTTPException(status_code=403, detail="This CareFlow account is disabled.")

    memberships = MembershipRepository(db).list_for_user(user_id)
    return AuthContext(
        user=profile,
        memberships=memberships,
        db=db,
        access_token=access_token,
    )


def require_platform_admin(context: AuthContext = Depends(get_current_context)) -> AuthContext:
    if not context.user.is_super_admin:
        raise HTTPException(status_code=403, detail="Super admin role required.")
    return context


def require_clinic_role(*roles: str):
    async def dependency(
        clinic_id: UUID,
        context: AuthContext = Depends(get_current_context),
    ) -> AuthContext:
        if context.user.is_super_admin:
            return context

        clinic = ClinicRepository(context.db).get(clinic_id)
        if clinic is None or not clinic.is_active:
            raise HTTPException(status_code=404, detail="Clinic not found or inactive.")

        membership = next(
            (
                item for item in context.memberships
                if item.clinic_id == clinic_id and item.status == "active"
            ),
            None,
        )
        if membership is None or membership.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have access to this clinic action.")
        return context

    return dependency
