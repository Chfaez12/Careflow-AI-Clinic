"""Profile serialization and tenant membership provisioning."""

from datetime import datetime, timezone
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.clinic_membership import ClinicMembership
from app.models.staff_member import StaffMember
from app.models.user import UserProfile
from app.repositories.clinics import ClinicRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.patients import PatientRepository
from app.repositories.staff_members import StaffMemberRepository
from app.repositories.users import UserRepository
from app.schemas.clinic import ClinicRole, InvitationRequest
from app.services.auth_service import delete_auth_user, invite_auth_user


STAFF_ROLES = {"doctor", "nurse", "receptionist", "billing_staff"}
CLINIC_ADMIN_ROLES = STAFF_ROLES | {"patient"}
MEMBER_ROLES = CLINIC_ADMIN_ROLES | {"clinic_admin"}


def generate_clinic_slug(clinic_name: str, clinics: ClinicRepository) -> str:
    """Create a lowercase, URL-safe, unique slug from mixed-script names."""
    normalized = unicodedata.normalize("NFKC", clinic_name).casefold()
    words: list[str] = []
    current: list[str] = []
    for character in normalized:
        if character.isalnum() or (current and unicodedata.category(character).startswith("M")):
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))

    base = "-".join(words) or "clinic"
    base = base[:100].rstrip("-") or "clinic"
    candidate = base
    suffix = 2
    while clinics.slug_exists(candidate):
        tail = f"-{suffix}"
        candidate = f"{base[:100 - len(tail)].rstrip('-')}{tail}"
        suffix += 1
    return candidate


def profile_data(user: UserProfile) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "role": "super_admin" if user.is_super_admin else "user",
        "is_super_admin": user.is_super_admin,
        "is_active": user.is_active,
        "deleted_at": user.deleted_at,
        "email_verified": user.email_verified_at is not None,
        "created_at": user.created_at,
    }


def membership_data(membership: ClinicMembership) -> dict:
    return {
        "id": membership.id,
        "clinic_id": membership.clinic_id,
        "user_id": str(membership.user_id),
        "role": membership.role,
        "status": membership.status,
        "patient_id": membership.patient_id,
        "invited_at": membership.invited_at,
        "accepted_at": membership.accepted_at,
    }


def session_result(
    data: dict,
    profile: UserProfile,
    memberships: list[ClinicMembership],
) -> dict:
    return {
        "token_type": data.get("token_type", "bearer"),
        "expires_in": data.get("expires_in"),
        "user": data.get("user"),
        "profile": profile_data(profile),
        "memberships": [membership_data(item) for item in memberships],
    }


def verified_at(auth_user: dict) -> datetime | None:
    if auth_user.get("email_confirmed_at") or auth_user.get("confirmed_at"):
        return datetime.now(timezone.utc)
    return None


async def provision_invited_member(
    *,
    db: Session,
    clinic_id: UUID,
    inviter: UserProfile,
    request: InvitationRequest,
    allowed_roles: set[str],
) -> dict:
    users = UserRepository(db)
    clinics = ClinicRepository(db)
    memberships = MembershipRepository(db)
    patients = PatientRepository(db)
    staff_members = StaffMemberRepository(db)
    role = request.role.value
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="You cannot assign that role.")

    normalized_email = str(request.email).strip().lower()
    patient_id: UUID | None = None
    if role == ClinicRole.patient:
        matches = patients.list_for_email(clinic_id, normalized_email)
        if not matches:
            raise HTTPException(
                status_code=404,
                detail="No patient record in this clinic matches the invitation email.",
            )
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail="Multiple patient records match this email; correct the duplicate patient records before inviting.",
            )
        patient_id = matches[0].id

    existing = users.get_by_email(normalized_email)
    if existing:
        existing_membership = memberships.get_for_user_and_clinic(existing.id, clinic_id)
        if existing_membership:
            raise HTTPException(status_code=409, detail="This account already has a clinic membership.")
        if existing.is_super_admin or not existing.is_active:
            raise HTTPException(status_code=409, detail="This account cannot be added to a clinic.")
        if existing.email_verified_at is None:
            raise HTTPException(status_code=409, detail="This email already has a pending account.")

        now = datetime.now(timezone.utc)
        membership = ClinicMembership(
            clinic_id=clinic_id,
            user_id=existing.id,
            role=role,
            status="active",
            patient_id=patient_id,
            invited_by_user_id=inviter.id,
            accepted_at=now,
        )
        memberships.add(membership)
        if role in STAFF_ROLES:
            staff_members.add(StaffMember(
                clinic_id=clinic_id,
                auth_user_id=existing.id,
                full_name=existing.full_name,
                email=existing.email,
                phone=existing.phone_number,
                role=role,
                is_active=True,
            ))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Could not create this clinic membership.") from exc
        return {"user_id": str(existing.id), "email": existing.email, "role": role, "status": "active"}

    if clinics.get(clinic_id) is None:
        raise HTTPException(status_code=404, detail="Clinic not found.")

    auth_user = await invite_auth_user(
        normalized_email,
        full_name=request.full_name,
        redirect_to=f"{settings.frontend_url.rstrip('/')}/auth/accept-invite",
    )
    user_id: UUID | None = None
    try:
        user_id = UUID(auth_user["id"])
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            id=user_id,
            email=normalized_email,
            full_name=request.full_name,
            is_active=True,
            email_verified_at=verified_at(auth_user),
        )
        users.add(profile)
        # Ensure the profile exists before rows reference users.id.
        db.flush([profile])
        membership = ClinicMembership(
            clinic_id=clinic_id,
            user_id=user_id,
            role=role,
            status="invited",
            patient_id=patient_id,
            invited_by_user_id=inviter.id,
            invited_at=now,
        )
        memberships.add(membership)
        if role in STAFF_ROLES:
            staff_members.add(StaffMember(
                clinic_id=clinic_id,
                auth_user_id=user_id,
                full_name=request.full_name,
                email=normalized_email,
                role=role,
                is_active=False,
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        if user_id is not None:
            await delete_auth_user(str(user_id))
        raise HTTPException(status_code=409, detail="Could not provision the invited account.") from exc

    return {"user_id": str(user_id), "email": normalized_email, "role": role, "status": "invited"}
