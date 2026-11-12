"""Clinic-admin audit history and patient access-log export."""

import csv
import io
import json
import unicodedata
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.patient import Patient
from app.repositories.audit_events import AuditEventRepository
from app.schemas.audit_log import AuditEventRead


router = APIRouter(prefix="/auth/clinics/{clinic_id}/audit-log", tags=["Audit Log"])


def _load_patient_export(clinic_id: UUID, patient_id: UUID, context: AuthContext, file_format: str):
    if context.db.query(Patient.id).filter_by(clinic_id=clinic_id, id=patient_id).first() is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    repository = AuditEventRepository(context.db)
    events = repository.list_patient_export(clinic_id, patient_id)
    repository.record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=patient_id,
        action="audit_log.patient_exported",
        resource_type="audit_log_export",
        resource_id=str(patient_id),
        details={"source": "audit_log_api", "format": file_format, "result_count": len(events)},
    )
    context.db.commit()
    return events


def _pdf_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return ascii_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(lines: list[str]) -> bytes:
    wrapped_lines = [
        line[start:start + 145]
        for line in lines
        for start in range(0, max(len(line), 1), 145)
    ]
    page_lines = [wrapped_lines[index:index + 56] for index in range(0, len(wrapped_lines), 56)] or [[]]
    objects: list[bytes] = []
    page_ids = [4 + 2 * index for index in range(len(page_lines))]
    objects.extend((
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ))
    for index, chunk in enumerate(page_lines):
        page_id = page_ids[index]
        content_id = page_id + 1
        commands = ["BT", "/F1 8 Tf", "40 800 Td"]
        for line_index, line in enumerate(chunk):
            if line_index:
                commands.append("0 -13 Td")
            commands.append(f"({_pdf_text(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii"))
    return bytes(pdf)


@router.get("", response_model=list[AuditEventRead])
async def list_audit_events(
    clinic_id: UUID,
    patient_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    action: str | None = Query(default=None, max_length=100),
    resource_type: str | None = Query(default=None, max_length=100),
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(status_code=422, detail="from_at must be earlier than to_at.")
    repository = AuditEventRepository(context.db)
    events = repository.list_events(
        clinic_id,
        patient_id=patient_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        from_at=from_at,
        to_at=to_at,
        limit=limit,
        offset=offset,
    )
    repository.record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action="audit_log.read",
        resource_type="audit_log",
        details={"source": "audit_log_api", "result_count": len(events)},
    )
    context.db.commit()
    return events


@router.get("/patients/{patient_id}/export.csv", response_class=StreamingResponse)
async def export_patient_audit_csv(
    clinic_id: UUID,
    patient_id: UUID,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    events = _load_patient_export(clinic_id, patient_id, context, "csv")

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("event_id", "created_at", "actor_user_id", "actor_staff_id", "action", "resource_type", "resource_id", "ip_address", "details"))
    for event in events:
        writer.writerow((
            event.id,
            event.created_at.isoformat() if event.created_at else "",
            event.actor_user_id or "",
            event.actor_staff_id or "",
            event.action,
            event.resource_type,
            event.resource_id or "",
            event.ip_address or "",
            json.dumps(event.details or {}, ensure_ascii=False, sort_keys=True),
        ))
    output.seek(0)
    filename = f"patient-{patient_id}-audit.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/patients/{patient_id}/export.pdf", response_class=StreamingResponse)
async def export_patient_audit_pdf(
    clinic_id: UUID,
    patient_id: UUID,
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    events = _load_patient_export(clinic_id, patient_id, context, "pdf")
    lines = [
        f"CareFlow patient audit export | Clinic {clinic_id} | Patient {patient_id}",
        f"Generated {datetime.now().astimezone().isoformat()} | {len(events)} events",
        "Event ID | Timestamp | Actor user | Actor staff | Action | Resource | Resource ID | IP",
        "-" * 118,
    ]
    for event in events:
        lines.append(" | ".join((
            str(event.id),
            event.created_at.isoformat() if event.created_at else "",
            str(event.actor_user_id or ""),
            str(event.actor_staff_id or ""),
            event.action,
            event.resource_type,
            event.resource_id or "",
            event.ip_address or "",
        )))
        if event.details:
            lines.append(f"  Details: {json.dumps(event.details, ensure_ascii=False, sort_keys=True)}")
    filename = f"patient-{patient_id}-audit.pdf"
    return StreamingResponse(
        iter([_build_pdf(lines)]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
