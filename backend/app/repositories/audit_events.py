"""Audit event write helpers for staff portal APIs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


class AuditEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        clinic_id: UUID,
        actor_user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        patient_id: UUID | None = None,
        details: dict | None = None,
    ) -> None:
        self.session.add(AuditEvent(
            clinic_id=clinic_id,
            actor_user_id=actor_user_id,
            patient_id=patient_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {"source": "staff_portal"},
        ))

    def list_events(
        self,
        clinic_id: UUID,
        *,
        patient_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        query = self.session.query(AuditEvent).filter(AuditEvent.clinic_id == clinic_id)
        if patient_id is not None:
            query = query.filter(AuditEvent.patient_id == patient_id)
        if actor_user_id is not None:
            query = query.filter(AuditEvent.actor_user_id == actor_user_id)
        if action:
            query = query.filter(AuditEvent.action == action)
        if resource_type:
            query = query.filter(AuditEvent.resource_type == resource_type)
        if from_at is not None:
            query = query.filter(AuditEvent.created_at >= from_at)
        if to_at is not None:
            query = query.filter(AuditEvent.created_at < to_at)
        return query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).offset(offset).all()

    def list_patient_export(self, clinic_id: UUID, patient_id: UUID) -> list[AuditEvent]:
        return self.session.query(AuditEvent).filter(
            AuditEvent.clinic_id == clinic_id,
            AuditEvent.patient_id == patient_id,
        ).order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc()).all()
