"""Clinic staff inbox for reviewing and answering patient portal messages."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.repositories.care_team import CareTeamRepository
from app.repositories.audit_events import AuditEventRepository
from app.repositories.patient_portal import PatientPortalRepository
from app.repositories.staff_members import StaffMemberRepository
from app.schemas.patient_portal import (
    InternalMessageCreate,
    InternalMessageRead,
    PortalMessageRead,
    StaffMessageReplyRequest,
    StaffMessageThread,
)


router = APIRouter(prefix="/auth/clinics/{clinic_id}/messages", tags=["Clinic Messages"])
STAFF_MESSAGE_ROLES = ("clinic_admin", "doctor", "nurse", "receptionist")
INTERNAL_MESSAGE_ROLES = ("clinic_admin", "doctor", "nurse", "billing_staff", "receptionist")


def _assigned_patient_ids(clinic_id: UUID, context: AuthContext) -> list[UUID] | None:
    if context.user.is_super_admin:
        return None
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    if membership is None or membership.role in {"clinic_admin", "nurse", "receptionist"}:
        return None
    staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff is None or not staff.is_active or staff.role != membership.role:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
    return [
        patient.id
        for patient in CareTeamRepository(context.db).list_patients_for_staff(clinic_id, staff.id)
    ]


@router.get("/inbox", response_model=list[PortalMessageRead])
async def get_message_inbox(
    clinic_id: UUID,
    pending_only: bool = Query(default=True),
    context: AuthContext = Depends(require_clinic_role(*STAFF_MESSAGE_ROLES)),
):
    repository = PatientPortalRepository(context.db)
    patient_ids = _assigned_patient_ids(clinic_id, context)
    assigned_staff_id = None
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    if membership is not None and membership.role == "doctor":
        staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
        if staff is None or not staff.is_active or staff.role != "doctor":
            raise HTTPException(status_code=403, detail="An active doctor profile is required.")
        assigned_staff_id = staff.id
    messages = repository.list_clinic_messages(
        clinic_id,
        pending_only=pending_only,
        patient_ids=patient_ids,
        assigned_staff_id=assigned_staff_id,
    )
    for message in messages:
        repository.add_access_audit(
            clinic_id=clinic_id,
            patient_id=message.patient_id,
            actor_user_id=context.user.id,
            action="patient.message.read_by_staff",
            resource_type="message",
            resource_id=str(message.id),
            details={"source": "clinic_message_inbox", "purpose": "staff_review"},
        )
    context.db.commit()
    return messages


@router.post("/{message_id}/reply", response_model=PortalMessageRead, status_code=201)
async def reply_to_patient_message(
    clinic_id: UUID,
    message_id: UUID,
    body: StaffMessageReplyRequest,
    context: AuthContext = Depends(require_clinic_role(*STAFF_MESSAGE_ROLES)),
):
    repository = PatientPortalRepository(context.db)
    original = repository.get_clinic_message(clinic_id, message_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Message not found in this clinic.")
    if original.direction != "inbound":
        raise HTTPException(status_code=409, detail="Replies can only be sent to patient messages.")
    if original.channel != "portal":
        raise HTTPException(status_code=409, detail="Only patient-portal messages can receive patient-visible replies.")
    if original.status != "needs_review":
        raise HTTPException(status_code=409, detail="This patient message has already been answered or reviewed.")

    patient_ids = _assigned_patient_ids(clinic_id, context)
    if patient_ids is not None and original.patient_id not in patient_ids:
        raise HTTPException(status_code=403, detail="This patient is not assigned to your care team.")

    staff_member = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff_member is None or not staff_member.is_active:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required to reply.")
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    if membership is None or (
        membership.role != "clinic_admin"
        and (membership.role not in {"doctor", "receptionist"} or staff_member.id != original.assigned_staff_id)
    ):
        raise HTTPException(
            status_code=403,
            detail="Only the staff member assigned to this message or a clinic admin can send a patient-visible reply.",
        )

    now = datetime.now(timezone.utc)
    reply = Message(
        clinic_id=clinic_id,
        patient_id=original.patient_id,
        channel="portal",
        direction="outbound",
        body=body.body.strip(),
        status="portal_delivered",
        triage_level=original.triage_level,
        assigned_staff_id=staff_member.id,
        sender_staff_id=staff_member.id,
        reply_to_message_id=original.id,
    )
    original.status = "answered"
    original.reviewed_at = now
    original.reviewed_by_staff_id = staff_member.id
    original.assigned_staff_id = staff_member.id
    repository.add(reply)
    context.db.flush()
    repository.add_access_audit(
        clinic_id=clinic_id,
        patient_id=original.patient_id,
        actor_user_id=context.user.id,
        action="patient.message.replied_by_staff",
        resource_type="message",
        resource_id=str(reply.id),
        details={"source": "clinic_message_inbox", "purpose": "staff_reply"},
    )
    context.db.commit()
    context.db.refresh(reply)
    return reply


@router.get("/{message_id}/thread", response_model=StaffMessageThread)
async def get_staff_message_thread(
    clinic_id: UUID,
    message_id: UUID,
    context: AuthContext = Depends(require_clinic_role(*INTERNAL_MESSAGE_ROLES)),
):
    repository = PatientPortalRepository(context.db)
    original = repository.get_clinic_message(clinic_id, message_id)
    if original is None or original.channel != "portal" or original.direction != "inbound":
        raise HTTPException(status_code=404, detail="Patient message not found in this clinic.")
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    staff_member = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if membership is None or staff_member is None or not staff_member.is_active:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
    if membership.role == "doctor" and staff_member.id != original.assigned_staff_id:
        raise HTTPException(status_code=403, detail="This message is assigned to another doctor.")

    internal_messages = repository.list_internal_messages(clinic_id, original.id)
    repository.add_access_audit(
        clinic_id=clinic_id,
        patient_id=original.patient_id,
        actor_user_id=context.user.id,
        action="patient.message.staff_thread.read",
        resource_type="message_thread",
        resource_id=str(original.id),
        details={"source": "clinic_message_inbox", "purpose": "staff_coordination"},
    )
    context.db.commit()
    return {"patient_message": original, "internal_messages": internal_messages}


@router.get("/internal/{staff_member_id}", response_model=list[InternalMessageRead])
async def get_internal_conversation(
    clinic_id: UUID,
    staff_member_id: UUID,
    context: AuthContext = Depends(require_clinic_role(*INTERNAL_MESSAGE_ROLES)),
):
    repository = PatientPortalRepository(context.db)
    staff_repository = StaffMemberRepository(context.db)
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    sender = staff_repository.get_for_user(clinic_id, context.user.id)
    recipient = staff_repository.get_for_clinic(clinic_id, staff_member_id)
    if membership is None or sender is None or not sender.is_active or sender.role != membership.role:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
    if recipient is None or not recipient.is_active:
        raise HTTPException(status_code=404, detail="Active recipient staff member not found in this clinic.")
    messages = repository.list_staff_conversation(clinic_id, sender.id, recipient.id)
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id, actor_user_id=context.user.id, action="staff.message.conversation.read",
        resource_type="staff_conversation", resource_id=f"{sender.id}:{recipient.id}",
        details={"source": "clinic_messages", "recipient_staff_id": str(recipient.id)},
    )
    context.db.commit()
    return messages


@router.get("/internal-recipients")
async def list_internal_recipients(
    clinic_id: UUID,
    context: AuthContext = Depends(require_clinic_role(*INTERNAL_MESSAGE_ROLES)),
):
    sender = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if sender is None or not sender.is_active:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
    return [
        {"staff_member_id": member.id, "full_name": member.full_name, "role": member.role}
        for member in StaffMemberRepository(context.db).list_internal_recipients(clinic_id)
        if member.id != sender.id
    ]


@router.post("/internal", response_model=InternalMessageRead, status_code=201)
async def send_internal_message(
    clinic_id: UUID,
    body: InternalMessageCreate,
    context: AuthContext = Depends(require_clinic_role(*INTERNAL_MESSAGE_ROLES)),
):
    repository = PatientPortalRepository(context.db)
    membership = next(
        (item for item in context.memberships if item.clinic_id == clinic_id and item.status == "active"),
        None,
    )
    staff_repository = StaffMemberRepository(context.db)
    sender = staff_repository.get_for_user(clinic_id, context.user.id)
    recipient = staff_repository.get_for_clinic(clinic_id, body.recipient_staff_member_id)
    if membership is None or sender is None or not sender.is_active or sender.role != membership.role:
        raise HTTPException(status_code=403, detail="An active clinic staff profile is required.")
    if recipient is None or not recipient.is_active:
        raise HTTPException(status_code=404, detail="Active recipient staff member not found in this clinic.")
    if recipient.id == sender.id:
        raise HTTPException(status_code=422, detail="You cannot send an internal message to yourself.")

    internal = Message(
        clinic_id=clinic_id,
        patient_id=None,
        channel="staff_internal",
        direction="internal",
        body=body.body.strip(),
        status="internal",
        sender_staff_id=sender.id,
        recipient_staff_id=recipient.id,
    )
    repository.add(internal)
    context.db.flush()
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="staff.message.direct",
        aggregate_type="message",
        aggregate_id=f"{sender.id}:{recipient.id}",
        payload={
            "internal_message_id": str(internal.id),
            "sender_staff_id": str(sender.id),
            "recipient_staff_id": str(recipient.id),
        },
    ))
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="staff.message.direct.sent",
        resource_type="staff_conversation",
        resource_id=f"{sender.id}:{recipient.id}",
        details={"source": "clinic_message_inbox", "sender_staff_id": str(sender.id), "recipient_staff_id": str(recipient.id)},
    )
    context.db.commit()
    context.db.refresh(internal)
    return internal
