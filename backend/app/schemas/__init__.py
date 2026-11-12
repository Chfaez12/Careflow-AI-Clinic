"""Pydantic request and response schemas grouped by API domain."""

from app.schemas.admin import DeleteClinicRequest, DeleteUserRequest
from app.schemas.auth import (
    AcceptInvitationRequest,
    AuthResult,
    BootstrapSuperAdminRequest,
    ClinicSignupRequest,
    EmailRequest,
    LoginRequest,
    PasswordUpdateRequest,
    ProfileUpdateRequest,
)
from app.schemas.billing_portal import ClaimCreate, ClaimList, ClaimRead, ClaimUpdate
from app.schemas.care_team import CareTeamAssignmentCreate
from app.schemas.clinic import ClinicRole, InvitationRequest
from app.schemas.nurse_portal import VitalCreate, VitalRead
from app.schemas.patient import PatientCreate, PatientList, PatientRead, PatientUpdate
from app.schemas.receptionist_portal import (
    AppointmentCancel,
    ReceptionAppointmentCreate,
    ReceptionAppointmentRead,
    ReceptionAppointmentReschedule,
    WaitingRoomItem,
)

__all__ = [
    "AcceptInvitationRequest",
    "AuthResult",
    "BootstrapSuperAdminRequest",
    "ClinicRole",
    "ClinicSignupRequest",
    "DeleteClinicRequest",
    "DeleteUserRequest",
    "EmailRequest",
    "InvitationRequest",
    "LoginRequest",
    "PasswordUpdateRequest",
    "ProfileUpdateRequest",
    "PatientCreate",
    "PatientList",
    "PatientRead",
    "PatientUpdate",
    "AppointmentCancel",
    "CareTeamAssignmentCreate",
    "ClaimCreate",
    "ClaimList",
    "ClaimRead",
    "ClaimUpdate",
    "ReceptionAppointmentCreate",
    "ReceptionAppointmentRead",
    "ReceptionAppointmentReschedule",
    "VitalCreate",
    "VitalRead",
    "WaitingRoomItem",
]
