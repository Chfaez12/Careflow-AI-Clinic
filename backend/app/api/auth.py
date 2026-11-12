"""Signup, login, session, password, and profile endpoints."""

import hmac
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.dependencies.auth import AuthContext, get_current_context
from app.models.clinic import Clinic
from app.models.clinic_membership import ClinicMembership
from app.models.staff_member import StaffMember
from app.models.user import UserProfile
from app.repositories.clinics import ClinicRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.users import UserRepository
from app.schemas.auth import (
    AcceptInvitationRequest,
    AuthResult,
    BootstrapSuperAdminRequest,
    ClinicSignupRequest,
    EmailRequest,
    LoginRequest,
    PasswordUpdateRequest,
    ProfileUpdateRequest,
    SessionExchangeRequest,
)
from app.services.account_service import (
    MEMBER_ROLES,
    STAFF_ROLES,
    generate_clinic_slug,
    membership_data,
    profile_data,
    session_result,
    verified_at,
)
from app.services.auth_service import auth_request, delete_auth_user, get_supabase_user


router = APIRouter(prefix="/auth", tags=["Authentication"])
ACCESS_COOKIE = "careflow_access_token"
REFRESH_COOKIE = "careflow_refresh_token"
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def _set_session_cookies(response: Response, data: dict) -> None:
    response.headers["Cache-Control"] = "no-store"
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token or not refresh_token:
        return
    secure = settings.environment.lower() not in {"development", "local", "test"}
    common = {"httponly": True, "secure": secure, "samesite": "lax", "path": "/"}
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=max(1, int(data.get("expires_in") or 3600)),
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=int(data.get("refresh_token_expires_in") or REFRESH_COOKIE_MAX_AGE),
        **common,
    )


def _clear_session_cookies(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    secure = settings.environment.lower() not in {"development", "local", "test"}
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")


def _auth_user(data: dict) -> dict:
    user = data.get("user")
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=502, detail="Supabase Auth did not return a user identity.")
    return user


async def _create_clinic_signup(body: ClinicSignupRequest, db: Session, response: Response):
    """Create a Supabase identity, clinic tenant, and first clinic admin."""
    normalized_email = str(body.email).strip().lower()
    users = UserRepository(db)
    if users.get_by_email(normalized_email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Log in or reset its password.",
        )

    data = await auth_request(
        "signup",
        payload={
            "email": normalized_email,
            "password": body.password,
            "data": {"full_name": body.full_name, "phone_number": body.phone_number},
        },
    )
    auth_user = _auth_user(data)
    user_id = UUID(auth_user["id"])
    try:
        clinics = ClinicRepository(db)
        memberships_repo = MembershipRepository(db)
        staff_repo = StaffMemberRepository(db)
        clinic = Clinic(
            name=body.clinic_name,
            slug=generate_clinic_slug(body.clinic_name, clinics),
            email=normalized_email,
            phone=body.clinic_phone,
            timezone=body.timezone,
        )
        clinics.add(clinic)
        db.flush()
        profile = UserProfile(
            id=user_id,
            email=normalized_email,
            full_name=body.full_name,
            phone_number=body.phone_number,
            email_verified_at=verified_at(auth_user),
        )
        users.add(profile)
        # Persist the FK target before inserting memberships/staff rows.
        db.flush([profile])
        membership = ClinicMembership(
            clinic_id=clinic.id,
            user_id=user_id,
            role="clinic_admin",
            status="active",
            accepted_at=datetime.now(timezone.utc),
        )
        memberships_repo.add(membership)
        staff_repo.add(StaffMember(
            clinic_id=clinic.id,
            auth_user_id=user_id,
            full_name=body.full_name,
            email=normalized_email,
            phone=body.phone_number,
            role="clinic_admin",
            is_active=True,
        ))
        db.commit()
        db.refresh(clinic)
        result = session_result(data, profile, [membership])
        result["clinic"] = {"id": clinic.id, "name": clinic.name, "slug": clinic.slug}
        _set_session_cookies(response, data)
        return result
    except IntegrityError as exc:
        db.rollback()
        await delete_auth_user(str(user_id))
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint in {"ix_users_email", "users_email_key", "uq_users_email", "pk_users", "users_pkey"}:
            detail = "An account with this email already exists. Log in or reset its password."
        elif constraint in {"ix_clinics_slug", "clinics_slug_key", "uq_clinics_slug"}:
            detail = "A clinic with this generated slug already exists. Try a different clinic name."
        else:
            conflict = constraint or "unknown database constraint"
            detail = f"Clinic signup conflicted with database constraint '{conflict}'. Contact support with this code."
        raise HTTPException(status_code=409, detail=detail) from exc
    except Exception as exc:
        db.rollback()
        await delete_auth_user(str(user_id))
        raise HTTPException(status_code=500, detail="Could not create the clinic account.") from exc


@router.post("/register", response_model=AuthResult, status_code=status.HTTP_201_CREATED)
async def register_clinic(
    body: ClinicSignupRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Register a clinic using the alternate registration path."""
    return await _create_clinic_signup(body, db, response)


@router.post("/bootstrap-super-admin", response_model=AuthResult, status_code=status.HTTP_201_CREATED)
async def bootstrap_super_admin(
    body: BootstrapSuperAdminRequest,
    response: Response,
    x_bootstrap_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Create the first platform admin using a one-time operator secret."""
    expected = settings.super_admin_bootstrap_key
    if (
        expected is None
        or len(expected.get_secret_value()) < 32
        or expected.get_secret_value() == "replace-with-a-long-random-one-time-secret"
        or not x_bootstrap_key
        or not hmac.compare_digest(x_bootstrap_key, expected.get_secret_value())
    ):
        raise HTTPException(status_code=404, detail="Bootstrap is unavailable.")

    users = UserRepository(db)
    if users.has_super_admin():
        raise HTTPException(status_code=409, detail="A platform super admin already exists.")

    email = str(body.email).strip().lower()
    if users.get_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="An account already uses this email.")
    data = await auth_request(
        "signup",
        payload={"email": email, "password": body.password,
                 "data": {"full_name": body.full_name}},
    )
    auth_user = _auth_user(data)
    profile = UserProfile(
        id=UUID(auth_user["id"]),
        email=email,
        full_name=body.full_name,
        role="super_admin",
        is_super_admin=True,
        email_verified_at=verified_at(auth_user),
    )
    try:
        users.add(profile)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        await delete_auth_user(str(profile.id))
        raise HTTPException(status_code=409, detail="Could not create the initial super admin.") from exc
    _set_session_cookies(response, data)
    return session_result(data, profile, [])


@router.post("/login", response_model=AuthResult)
async def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    data = await auth_request(
        "token?grant_type=password",
        payload={"email": str(body.email), "password": body.password},
    )
    auth_user = _auth_user(data)
    users = UserRepository(db)
    memberships_repo = MembershipRepository(db)
    profile = users.get(UUID(auth_user["id"]))
    if profile is not None and profile.deleted_at is not None:
        raise HTTPException(status_code=403, detail="This CareFlow account has been deleted.")
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=403, detail="CareFlow account is not active.")
    if verified_at(auth_user) and profile.email_verified_at is None:
        profile.email_verified_at = verified_at(auth_user)
        db.commit()
    memberships = memberships_repo.list_for_user(profile.id)
    if not profile.is_super_admin and not any(m.status in {"active", "invited"} for m in memberships):
        raise HTTPException(status_code=403, detail="No clinic membership is assigned to this account.")
    _set_session_cookies(response, data)
    return session_result(data, profile, memberships)


@router.post("/session/exchange", response_model=AuthResult)
async def exchange_supabase_session(
    body: SessionExchangeRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Validate a Supabase email-link session and store it in HTTP-only cookies."""
    auth_user = await get_supabase_user(body.access_token)
    try:
        user_id = UUID(auth_user["id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authenticated user.") from exc
    profile = UserRepository(db).get(user_id)
    if profile is None or not profile.is_active or profile.deleted_at is not None:
        raise HTTPException(status_code=403, detail="CareFlow account is not active.")
    observed_verified_at = verified_at(auth_user)
    if observed_verified_at and profile.email_verified_at is None:
        profile.email_verified_at = observed_verified_at
        db.commit()
    memberships = MembershipRepository(db).list_for_user(profile.id)
    session_data = {
        "user": auth_user,
        "access_token": body.access_token,
        "refresh_token": body.refresh_token,
        "expires_in": body.expires_in,
        "refresh_token_expires_in": body.refresh_token_expires_in,
    }
    _set_session_cookies(response, session_data)
    return session_result(session_data, profile, memberships)


@router.post("/refresh", response_model=AuthResult)
async def refresh_session(
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: Session = Depends(get_db),
):
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="Refresh session cookie is missing.")
    data = await auth_request(
        "token?grant_type=refresh_token", payload={"refresh_token": refresh_cookie}
    )
    auth_user = _auth_user(data)
    profile = UserRepository(db).get(UUID(auth_user["id"]))
    if profile is not None and profile.deleted_at is not None:
        raise HTTPException(status_code=403, detail="This CareFlow account has been deleted.")
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=403, detail="CareFlow account is not active.")
    memberships = MembershipRepository(db).list_for_user(profile.id)
    _set_session_cookies(response, data)
    return session_result(data, profile, memberships)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    access_cookie: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
    authorization: str | None = Header(default=None),
):
    """End the browser session and clear cookies even if the access token expired."""
    token = access_cookie
    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value

    # Local logout must still succeed when Supabase cannot revoke an expired or
    # already-invalid token. Clearing the HTTP-only cookies is the user-visible
    # session boundary; a valid token is also revoked remotely when possible.
    try:
        if token:
            await auth_request("logout", access_token=token)
    except Exception:
        pass
    finally:
        _clear_session_cookies(response)


@router.post("/password/reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: EmailRequest):
    await auth_request(
        "recover",
        payload={
            "email": str(body.email),
            "redirect_to": f"{settings.frontend_url.rstrip('/')}/auth/reset-password",
        },
    )
    return {"message": "If an account exists for that email, recovery instructions have been sent."}


@router.put("/password")
async def update_password(body: PasswordUpdateRequest, context: AuthContext = Depends(get_current_context)):
    return await auth_request(
        "user", method="PUT", payload={"password": body.password}, access_token=context.access_token
    )


@router.get("/my-profile")
async def get_me(context: AuthContext = Depends(get_current_context)):
    return {
        "profile": profile_data(context.user),
        "memberships": [membership_data(item) for item in context.memberships],
    }


@router.get("/verify")
async def verify_access_token(context: AuthContext = Depends(get_current_context)):
    return {"authenticated": True, "user_id": str(context.user.id), "email": context.user.email}


@router.patch("/update-profile")
async def update_my_profile(
    body: ProfileUpdateRequest,
    context: AuthContext = Depends(get_current_context),
):
    if body.full_name is not None:
        context.user.full_name = body.full_name
    if body.phone_number is not None:
        context.user.phone_number = body.phone_number
    staff_repo = StaffMemberRepository(context.db)
    for membership in context.memberships:
        if membership.role in MEMBER_ROLES:
            staff = staff_repo.get_for_user(membership.clinic_id, context.user.id)
            if staff:
                staff.full_name = context.user.full_name
                staff.phone = context.user.phone_number
    context.db.commit()
    return {
        "profile": profile_data(context.user),
        "memberships": [membership_data(item) for item in context.memberships],
    }


@router.post("/invitations/accept")
async def accept_invitation(
    body: AcceptInvitationRequest,
    context: AuthContext = Depends(get_current_context),
):
    now = datetime.now(timezone.utc)
    if context.user.email_verified_at is None:
        auth_user = await auth_request("user", method="GET", access_token=context.access_token)
        if not verified_at(auth_user):
            raise HTTPException(status_code=403, detail="Confirm your email from the invitation first.")
        context.user.email_verified_at = now

    membership = next((
        item for item in context.memberships
        if item.clinic_id == body.clinic_id and item.status == "invited"
    ), None)
    if membership is None:
        raise HTTPException(status_code=409, detail="There are no pending invitations for this clinic.")
    membership.status = "active"
    membership.accepted_at = now
    if membership.role in STAFF_ROLES:
        staff = StaffMemberRepository(context.db).get_for_user(
            membership.clinic_id,
            context.user.id,
        )
        if staff:
            staff.is_active = True
    context.db.commit()
    return {"accepted": membership_data(membership)}
