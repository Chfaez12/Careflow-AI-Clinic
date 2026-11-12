"""Doctor dashboard, patient chart, visit, note and order APIs."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.allergy import Allergy
from app.models.ai_suggestion import AISuggestion
from app.models.clinical_note import ClinicalNote
from app.models.medical_condition import MedicalCondition
from app.models.medication import Medication
from app.models.order import Order
from app.models.outbox_event import OutboxEvent
from app.repositories.audit_events import AuditEventRepository
from app.repositories.clinics import ClinicRepository
from app.repositories.doctor_portal import DoctorPortalRepository
from app.repositories.patient_portal import PatientPortalRepository
from app.repositories.appointments import AppointmentRepository
from app.repositories.staff_members import StaffMemberRepository
from app.schemas.doctor_portal import (
    AISuggestionRead,
    AllergyCreate,
    AllergyUpdate,
    ConditionCreate,
    ConditionUpdate,
    DraftNoteRequest,
    LabOrderCreate,
    NoteCreate,
    NoteAmendmentCreate,
    NoteRead,
    NoteUpdate,
    OrderSignRequest,
    OrderDraftUpdate,
    OrderRead,
    PrescriptionCreate,
    SuggestionDecision,
    VisitConsentRequest,
    VisitUpdate,
)
from app.schemas.previsit_summary import PrevisitSummaryRead
from app.services.previsit_summary_service import build_previsit_summary
from app.services.medication_safety import record_match_warnings


router = APIRouter(prefix="/auth/clinics/{clinic_id}/doctor", tags=["Doctor Portal"])


def _doctor_staff(clinic_id: UUID, context: AuthContext):
    staff = StaffMemberRepository(context.db).get_for_user(clinic_id, context.user.id)
    if staff is None or not staff.is_active or staff.role != "doctor":
        raise HTTPException(status_code=403, detail="An active doctor profile is required.")
    return staff


def _day_bounds(clinic_id: UUID, context: AuthContext, requested_day: date | None):
    clinic = ClinicRepository(context.db).get(clinic_id)
    if clinic is None or not clinic.is_active:
        raise HTTPException(status_code=404, detail="Clinic not found or inactive.")
    try:
        clinic_zone = ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        clinic_zone = timezone.utc
    day = requested_day or datetime.now(clinic_zone).date()
    return (
        datetime.combine(day, time.min, tzinfo=clinic_zone),
        datetime.combine(day + timedelta(days=1), time.min, tzinfo=clinic_zone),
    )


def _require_patient_access(repository: DoctorPortalRepository, clinic_id: UUID, patient_id: UUID, staff_id: UUID):
    patient = repository.get_patient(clinic_id, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found in this clinic.")
    if not repository.can_access_patient(clinic_id, patient_id, staff_id):
        raise HTTPException(status_code=403, detail="This patient is not assigned to your care team.")
    return patient


def _require_visit_access(repository: DoctorPortalRepository, clinic_id: UUID, visit_id: UUID, staff_id: UUID, *, for_update: bool = False):
    visit = repository.get_visit(clinic_id, visit_id)
    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found in this clinic.")
    if visit.clinician_staff_id is not None and visit.clinician_staff_id != staff_id:
        raise HTTPException(status_code=403, detail="This visit is assigned to another doctor.")
    _require_patient_access(repository, clinic_id, visit.patient_id, staff_id)
    if for_update and visit.status.casefold() not in {"arrived", "in_room", "in_progress"}:
        raise HTTPException(status_code=409, detail="This visit is not active.")
    return visit


def _audit(context: AuthContext, clinic_id: UUID, patient_id: UUID, action: str, resource_type: str, resource_id: UUID | None = None, details: dict | None = None):
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        patient_id=patient_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details={"source": "doctor_portal", **(details or {})},
    )


@router.get("/dashboard")
async def doctor_dashboard(
    clinic_id: UUID,
    day: date | None = Query(default=None),
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    starts_at, ends_at = _day_bounds(clinic_id, context, day)
    patients = repository.list_patients(clinic_id, staff.id, limit=200)
    appointments = repository.list_appointments(clinic_id, staff.id, starts_at, ends_at)
    visits = repository.list_visits(clinic_id, staff.id)
    messages = PatientPortalRepository(context.db).list_clinic_messages(
        clinic_id, pending_only=True, assigned_staff_id=staff.id
    )
    for appointment, patient in appointments:
        _audit(context, clinic_id, patient.id, "appointment.read_by_doctor", "appointment", appointment.id)
    for message in messages:
        _audit(context, clinic_id, message.patient_id, "patient.message.read_by_doctor", "message", message.id)
    context.db.commit()
    return {
        "staff_member_id": staff.id,
        "day": starts_at.date(),
        "assigned_patient_count": len(patients),
        "appointments": [
            {"id": appointment.id, "patient_id": patient.id,
             "patient_name": f"{patient.first_name} {patient.last_name}",
             "starts_at": appointment.starts_at, "ends_at": appointment.ends_at,
             "status": appointment.status, "reason": appointment.reason}
            for appointment, patient in appointments
        ],
        "active_visits": [
            {"id": visit.id, "patient_id": patient.id,
             "patient_name": f"{patient.first_name} {patient.last_name}",
             "status": visit.status, "started_at": visit.started_at}
            for visit, patient in visits
        ],
        "messages_needing_review": [
            {"id": message.id, "patient_id": message.patient_id, "body": message.body,
             "triage_level": message.triage_level, "created_at": message.created_at}
            for message in messages
        ],
    }


@router.get("/patients")
async def list_doctor_patients(
    clinic_id: UUID,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    patients = DoctorPortalRepository(context.db).list_patients(
        clinic_id, staff.id, search=search, limit=limit + 1, offset=offset
    )
    has_more = len(patients) > limit
    patients = patients[:limit]
    for patient in patients:
        _audit(context, clinic_id, patient.id, "patient.read_by_doctor", "patient", patient.id)
    context.db.commit()
    return {"items": patients, "limit": limit, "offset": offset, "has_more": has_more}


@router.get("/patients/{patient_id}/chart")
async def get_patient_chart(
    clinic_id: UUID,
    patient_id: UUID,
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    patient = _require_patient_access(repository, clinic_id, patient_id, staff.id)
    appointments = repository.list_appointments_for_patient(clinic_id, patient_id)
    visits = repository.list_patient_visits(clinic_id, patient_id)
    _audit(context, clinic_id, patient_id, "patient.chart.read_by_doctor", "patient_chart", patient_id)
    context.db.commit()
    return {
        "patient": patient,
        "appointments": appointments,
        "visits": visits,
        "allergies": repository.list_allergies(clinic_id, patient_id),
        "conditions": repository.list_conditions(clinic_id, patient_id),
        "medications": repository.list_medications(clinic_id, patient_id),
        "vitals": repository.list_vitals(clinic_id, patient_id),
        "notes": [note for visit in visits for note in repository.list_notes(clinic_id, visit.id)],
        "orders": [order for visit in visits for order in repository.list_orders(clinic_id, visit.id)],
    }


@router.get("/appointments")
async def list_doctor_appointments(
    clinic_id: UUID,
    day: date | None = Query(default=None),
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    starts_at, ends_at = _day_bounds(clinic_id, context, day)
    rows = DoctorPortalRepository(context.db).list_appointments(clinic_id, staff.id, starts_at, ends_at)
    for appointment, patient in rows:
        _audit(context, clinic_id, patient.id, "appointment.read_by_doctor", "appointment", appointment.id)
    context.db.commit()
    return [{"id": a.id, "patient_id": p.id, "patient_name": f"{p.first_name} {p.last_name}",
             "starts_at": a.starts_at, "ends_at": a.ends_at, "status": a.status,
             "reason": a.reason, "source": a.source} for a, p in rows]


@router.get("/appointments/{appointment_id}/previsit-summary", response_model=PrevisitSummaryRead)
async def get_previsit_summary(
    clinic_id: UUID,
    appointment_id: UUID,
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    appointment = AppointmentRepository(context.db).get(clinic_id, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found in this clinic.")
    if appointment.assigned_staff_id != staff.id:
        raise HTTPException(status_code=403, detail="This appointment is not assigned to your doctor profile.")
    repository = DoctorPortalRepository(context.db)
    patient = _require_patient_access(repository, clinic_id, appointment.patient_id, staff.id)
    summary = build_previsit_summary(clinic_id, appointment, patient, repository)
    _audit(context, clinic_id, patient.id, "previsit_summary.read", "previsit_summary", appointment.id,
           {"generator": "deterministic_demo", "source_count": len(summary["sources"])})
    context.db.commit()
    return summary


@router.get("/visits/{visit_id}")
async def get_doctor_visit(clinic_id: UUID, visit_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id)
    patient = repository.get_patient(clinic_id, visit.patient_id)
    _audit(context, clinic_id, visit.patient_id, "visit.read_by_doctor", "visit", visit.id)
    context.db.commit()
    return {"visit": visit, "patient": patient,
            "allergies": repository.list_allergies(clinic_id, visit.patient_id),
            "conditions": repository.list_conditions(clinic_id, visit.patient_id),
            "medications": repository.list_medications(clinic_id, visit.patient_id),
            "vitals": repository.list_vitals(clinic_id, visit.patient_id),
            "notes": repository.list_notes(clinic_id, visit.id),
            "orders": repository.list_orders(clinic_id, visit.id)}


@router.post("/visits/{visit_id}/start")
async def start_visit(clinic_id: UUID, visit_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    if visit.status == "in_progress" and visit.clinician_staff_id == staff.id:
        return {"id": visit.id, "status": visit.status, "started_at": visit.started_at}
    visit.clinician_staff_id = staff.id
    visit.status = "in_progress"
    context.db.add(OutboxEvent(
        clinic_id=clinic_id,
        event_type="visit.started",
        aggregate_type="visit",
        aggregate_id=str(visit.id),
        payload={"visit_id": str(visit.id), "patient_id": str(visit.patient_id), "doctor_staff_id": str(staff.id)},
    ))
    _audit(context, clinic_id, visit.patient_id, "visit.started_by_doctor", "visit", visit.id)
    context.db.commit()
    context.db.refresh(visit)
    return {"id": visit.id, "status": visit.status, "started_at": visit.started_at}


@router.patch("/visits/{visit_id}")
async def update_doctor_visit(clinic_id: UUID, visit_id: UUID, body: VisitUpdate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    visit.clinician_staff_id = staff.id
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Provide a visit field to update.")
    if "chief_complaint" in values:
        visit.chief_complaint = body.chief_complaint.strip() if body.chief_complaint else None
    _audit(context, clinic_id, visit.patient_id, "visit.updated_by_doctor", "visit", visit.id)
    context.db.commit()
    context.db.refresh(visit)
    return visit


@router.post("/patients/{patient_id}/allergies", status_code=status.HTTP_201_CREATED)
async def add_patient_allergy(clinic_id: UUID, patient_id: UUID, body: AllergyCreate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    _require_patient_access(repository, clinic_id, patient_id, staff.id)
    allergy = Allergy(clinic_id=clinic_id, patient_id=patient_id, recorded_by_staff_id=staff.id,
                      substance=body.substance.strip(), reaction=body.reaction, severity=body.severity, status="active")
    repository.add(allergy)
    context.db.flush()
    _audit(context, clinic_id, patient_id, "allergy.recorded_by_doctor", "allergy", allergy.id)
    context.db.commit()
    context.db.refresh(allergy)
    return allergy


@router.patch("/allergies/{allergy_id}")
async def update_patient_allergy(clinic_id: UUID, allergy_id: UUID, body: AllergyUpdate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    allergy = repository.get_allergy(clinic_id, allergy_id)
    if allergy is None:
        raise HTTPException(status_code=404, detail="Allergy not found in this clinic.")
    _require_patient_access(repository, clinic_id, allergy.patient_id, staff.id)
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        if key == "status" and value is None:
            continue
        setattr(allergy, key, value)
    _audit(context, clinic_id, allergy.patient_id, "allergy.updated_by_doctor", "allergy", allergy.id)
    context.db.commit()
    context.db.refresh(allergy)
    return allergy


@router.post("/patients/{patient_id}/conditions", status_code=status.HTTP_201_CREATED)
async def add_patient_condition(clinic_id: UUID, patient_id: UUID, body: ConditionCreate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    _require_patient_access(repository, clinic_id, patient_id, staff.id)
    condition = MedicalCondition(clinic_id=clinic_id, patient_id=patient_id, recorded_by_staff_id=staff.id,
                                name=body.name.strip(), code=body.code, code_system=body.code_system,
                                onset_date=body.onset_date, notes=body.notes, status="active")
    repository.add(condition)
    context.db.flush()
    _audit(context, clinic_id, patient_id, "medical_condition.recorded", "medical_condition", condition.id)
    context.db.commit()
    context.db.refresh(condition)
    return condition


@router.patch("/conditions/{condition_id}")
async def update_patient_condition(clinic_id: UUID, condition_id: UUID, body: ConditionUpdate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    condition = repository.get_condition(clinic_id, condition_id)
    if condition is None:
        raise HTTPException(status_code=404, detail="Medical condition not found in this clinic.")
    _require_patient_access(repository, clinic_id, condition.patient_id, staff.id)
    if body.status is not None:
        condition.status = body.status
        if body.status == "resolved":
            condition.resolved_date = body.resolved_date or datetime.now(timezone.utc).date()
        else:
            condition.resolved_date = None
    elif "resolved_date" in body.model_fields_set:
        condition.resolved_date = body.resolved_date
    if "notes" in body.model_fields_set:
        condition.notes = body.notes
    _audit(context, clinic_id, condition.patient_id, "medical_condition.updated", "medical_condition", condition.id)
    context.db.commit()
    context.db.refresh(condition)
    return condition


@router.put("/visits/{visit_id}/recording-consent")
async def record_visit_consent(clinic_id: UUID, visit_id: UUID, body: VisitConsentRequest, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    visit.recording_consent = body.consent_given
    visit.recording_consent_at = datetime.now(timezone.utc)
    _audit(context, clinic_id, visit.patient_id, "visit.recording_consent.recorded", "visit", visit.id,
           {"consent_given": body.consent_given})
    context.db.commit()
    return {"visit_id": visit.id, "consent_given": visit.recording_consent,
            "recorded_at": visit.recording_consent_at}


@router.get("/visits/{visit_id}/notes", response_model=list[NoteRead])
async def list_visit_notes(clinic_id: UUID, visit_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id)
    _audit(context, clinic_id, visit.patient_id, "clinical_note.read_by_doctor", "clinical_note_collection", visit.id)
    context.db.commit()
    return repository.list_notes(clinic_id, visit.id)


@router.post("/visits/{visit_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_visit_note(clinic_id: UUID, visit_id: UUID, body: NoteCreate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    versions = repository.list_notes(clinic_id, visit.id)
    note = ClinicalNote(clinic_id=clinic_id, visit_id=visit.id, author_staff_id=staff.id,
                        version=max((item.version for item in versions), default=0) + 1,
                        content=body.content.strip(), status="draft")
    repository.add(note)
    context.db.flush()
    _audit(context, clinic_id, visit.patient_id, "clinical_note.draft_created", "clinical_note", note.id)
    context.db.commit()
    context.db.refresh(note)
    return note


@router.patch("/notes/{note_id}", response_model=NoteRead)
async def update_doctor_note(clinic_id: UUID, note_id: UUID, body: NoteUpdate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    note = repository.get_note(clinic_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Clinical note not found in this clinic.")
    visit = _require_visit_access(repository, clinic_id, note.visit_id, staff.id, for_update=True)
    if note.author_staff_id != staff.id or note.status != "draft":
        raise HTTPException(status_code=409, detail="Only your own unsigned draft notes can be edited.")
    note.content = body.content.strip()
    _audit(context, clinic_id, visit.patient_id, "clinical_note.draft_updated", "clinical_note", note.id)
    context.db.commit()
    context.db.refresh(note)
    return note


@router.post("/notes/{note_id}/amendments", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note_amendment(
    clinic_id: UUID,
    note_id: UUID,
    body: NoteAmendmentCreate,
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    original = repository.get_note(clinic_id, note_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Clinical note not found in this clinic.")
    if original.status != "signed":
        raise HTTPException(status_code=409, detail="Only a signed note can receive a signed correction amendment.")
    visit = _require_visit_access(repository, clinic_id, original.visit_id, staff.id)
    versions = repository.list_notes(clinic_id, visit.id)
    amendment = ClinicalNote(
        clinic_id=clinic_id,
        visit_id=visit.id,
        amends_note_id=original.id,
        amendment_reason=body.reason.strip(),
        author_staff_id=staff.id,
        version=max((item.version for item in versions), default=0) + 1,
        content=body.content.strip(),
        status="draft",
    )
    repository.add(amendment)
    context.db.flush()
    _audit(context, clinic_id, visit.patient_id, "clinical_note.amendment_draft_created", "clinical_note", amendment.id,
           {"amends_note_id": str(original.id), "reason": body.reason.strip()})
    context.db.commit()
    context.db.refresh(amendment)
    return amendment


@router.post("/notes/{note_id}/sign", response_model=NoteRead)
async def sign_doctor_note(clinic_id: UUID, note_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    note = repository.get_note(clinic_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Clinical note not found in this clinic.")
    if note.status == "signed" and note.signed_by_staff_id == staff.id:
        signed_visit = repository.get_visit(clinic_id, note.visit_id)
        if signed_visit is None:
            raise HTTPException(status_code=404, detail="Visit not found in this clinic.")
        if signed_visit.clinician_staff_id is not None and signed_visit.clinician_staff_id != staff.id:
            raise HTTPException(status_code=403, detail="This visit is assigned to another doctor.")
        _require_patient_access(repository, clinic_id, signed_visit.patient_id, staff.id)
        return note
    visit = _require_visit_access(repository, clinic_id, note.visit_id, staff.id, for_update=True)
    if note.author_staff_id != staff.id or note.status != "draft":
        raise HTTPException(status_code=409, detail="Only your own unsigned draft notes can be signed.")
    note.status = "signed"
    note.signed_by_staff_id = staff.id
    note.signed_at = datetime.now(timezone.utc)
    event_type = "clinical_note.amended" if note.amends_note_id else "clinical_note.signed"
    context.db.add(OutboxEvent(clinic_id=clinic_id, event_type=event_type, aggregate_type="clinical_note",
                               aggregate_id=str(note.id), payload={"note_id": str(note.id), "visit_id": str(visit.id), "patient_id": str(visit.patient_id)}))
    _audit(context, clinic_id, visit.patient_id, event_type, "clinical_note", note.id,
           {"amends_note_id": str(note.amends_note_id)} if note.amends_note_id else None)
    context.db.commit()
    context.db.refresh(note)
    return note


@router.post("/visits/{visit_id}/prescriptions", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_prescription(clinic_id: UUID, visit_id: UUID, body: PrescriptionCreate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    order = Order(clinic_id=clinic_id, patient_id=visit.patient_id, visit_id=visit.id,
                  created_by_staff_id=staff.id, order_type="prescription", status="draft",
                  details=body.model_dump(), notes=body.instructions)
    repository.add(order)
    context.db.flush()
    _audit(context, clinic_id, visit.patient_id, "prescription.draft_created", "order", order.id)
    context.db.commit()
    context.db.refresh(order)
    return order


@router.post("/visits/{visit_id}/prescriptions/check")
async def check_prescription_record_matches(
    clinic_id: UUID,
    visit_id: UUID,
    body: PrescriptionCreate,
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id)
    warnings = record_match_warnings(
        body.medication_name,
        body.rxnorm_code,
        repository.list_allergies(clinic_id, visit.patient_id),
        repository.list_medications(clinic_id, visit.patient_id),
    )
    _audit(context, clinic_id, visit.patient_id, "prescription.record_match_check", "visit", visit.id,
           {"warning_count": len(warnings), "checker": "clinic_record_match_only"})
    context.db.commit()
    return {
        "patient_id": visit.patient_id,
        "medication_name": body.medication_name,
        "warnings": warnings,
        "checks_not_performed": [
            "drug-drug interactions",
            "dose ranges and age/weight adjustment",
            "external medication-reference database checks",
        ],
        "disclaimer": "Record matching only; this is not a complete medication safety check. The prescribing clinician must verify the full medication history and clinical appropriateness.",
    }


@router.post("/visits/{visit_id}/lab-orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_lab_order(clinic_id: UUID, visit_id: UUID, body: LabOrderCreate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    order = Order(clinic_id=clinic_id, patient_id=visit.patient_id, visit_id=visit.id,
                  created_by_staff_id=staff.id, order_type="lab", status="draft",
                  details=body.model_dump(), notes=body.instructions)
    repository.add(order)
    context.db.flush()
    _audit(context, clinic_id, visit.patient_id, "lab_order.draft_created", "order", order.id)
    context.db.commit()
    context.db.refresh(order)
    return order


@router.post("/orders/{order_id}/sign", response_model=OrderRead)
async def sign_doctor_order(
    clinic_id: UUID,
    order_id: UUID,
    body: OrderSignRequest | None = None,
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    order = repository.get_order(clinic_id, order_id)
    if order is None or order.visit_id is None:
        raise HTTPException(status_code=404, detail="Visit order not found in this clinic.")
    if order.status == "signed" and order.signed_by_staff_id == staff.id:
        completed_visit = repository.get_visit(clinic_id, order.visit_id)
        if completed_visit is None:
            raise HTTPException(status_code=404, detail="Visit not found in this clinic.")
        if completed_visit.clinician_staff_id is not None and completed_visit.clinician_staff_id != staff.id:
            raise HTTPException(status_code=403, detail="This visit is assigned to another doctor.")
        _require_patient_access(repository, clinic_id, completed_visit.patient_id, staff.id)
        return order
    visit = _require_visit_access(repository, clinic_id, order.visit_id, staff.id, for_update=True)
    if order.created_by_staff_id != staff.id or order.status != "draft":
        raise HTTPException(status_code=409, detail="Only your own draft orders can be signed.")
    if order.order_type not in {"prescription", "lab"}:
        raise HTTPException(status_code=409, detail="This order type cannot be signed through the doctor portal.")
    if order.order_type == "prescription":
        try:
            PrescriptionCreate.model_validate(order.details)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="The prescription draft is incomplete and cannot be signed.") from exc
        warnings = record_match_warnings(
            order.details["medication_name"],
            order.details.get("rxnorm_code"),
            repository.list_allergies(clinic_id, visit.patient_id),
            repository.list_medications(clinic_id, visit.patient_id),
        )
        severe_matches = [warning for warning in warnings if warning["severity"] == "severe"]
        override_reason = body.override_reason.strip() if body and body.override_reason else None
        if severe_matches and not override_reason:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A severe active allergy name match blocks signing unless the doctor records an override reason.",
                    "warnings": warnings,
                    "required_field": "override_reason",
                },
            )
        if severe_matches and override_reason:
            order.details = {
                **order.details,
                "safety_override": {
                    "reason": override_reason,
                    "staff_member_id": str(staff.id),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "warning_source_ids": [str(item["source_id"]) for item in severe_matches],
                },
            }
    now = datetime.now(timezone.utc)
    order.status = "signed"
    order.signed_by_staff_id = staff.id
    order.signed_at = now
    if order.order_type == "prescription":
        data = order.details
        repository.add(Medication(
            clinic_id=clinic_id, patient_id=visit.patient_id,
            name=data["medication_name"], rxnorm_code=data.get("rxnorm_code"),
            dose=data["dose"], route=data["route"], frequency=data["frequency"],
            instructions=data.get("instructions"), status="active",
            start_date=now.date(),
            end_date=(now.date() + timedelta(days=data["duration_days"] - 1)) if data.get("duration_days") else None,
            prescribed_by_staff_id=staff.id,
        ))
    context.db.add(OutboxEvent(clinic_id=clinic_id, event_type=f"{order.order_type}.order.signed", aggregate_type="order",
                               aggregate_id=str(order.id), payload={"order_id": str(order.id), "visit_id": str(visit.id), "patient_id": str(visit.patient_id)}))
    _audit(context, clinic_id, visit.patient_id, f"{order.order_type}.order.signed", "order", order.id,
           {"safety_override_recorded": bool(order.details.get("safety_override"))} if order.order_type == "prescription" else None)
    context.db.commit()
    context.db.refresh(order)
    return order


@router.patch("/orders/{order_id}", response_model=OrderRead)
async def update_doctor_order(clinic_id: UUID, order_id: UUID, body: OrderDraftUpdate, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    order = repository.get_order(clinic_id, order_id)
    if order is None or order.visit_id is None:
        raise HTTPException(status_code=404, detail="Visit order not found in this clinic.")
    visit = _require_visit_access(repository, clinic_id, order.visit_id, staff.id, for_update=True)
    if order.created_by_staff_id != staff.id or order.status != "draft":
        raise HTTPException(status_code=409, detail="Only your own draft orders can be edited.")
    try:
        if order.order_type == "prescription":
            normalized = PrescriptionCreate.model_validate(body.details).model_dump()
        elif order.order_type == "lab":
            normalized = LabOrderCreate.model_validate(body.details).model_dump()
        else:
            raise HTTPException(status_code=409, detail="This order type cannot be edited through the doctor portal.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    order.details = normalized
    order.notes = body.notes
    _audit(context, clinic_id, visit.patient_id, "order.draft_updated", "order", order.id)
    context.db.commit()
    context.db.refresh(order)
    return order


@router.post("/orders/{order_id}/cancel", response_model=OrderRead)
async def cancel_doctor_order(clinic_id: UUID, order_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    order = repository.get_order(clinic_id, order_id)
    if order is None or order.visit_id is None:
        raise HTTPException(status_code=404, detail="Visit order not found in this clinic.")
    visit = _require_visit_access(repository, clinic_id, order.visit_id, staff.id, for_update=True)
    if order.created_by_staff_id != staff.id or order.status != "draft":
        raise HTTPException(status_code=409, detail="Only your own draft orders can be cancelled.")
    order.status = "cancelled"
    _audit(context, clinic_id, visit.patient_id, "order.draft_cancelled", "order", order.id)
    context.db.commit()
    context.db.refresh(order)
    return order


@router.post("/medications/{medication_id}/discontinue")
async def discontinue_doctor_medication(clinic_id: UUID, medication_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    medication = repository.get_medication(clinic_id, medication_id)
    if medication is None:
        raise HTTPException(status_code=404, detail="Medication not found in this clinic.")
    _require_patient_access(repository, clinic_id, medication.patient_id, staff.id)
    if medication.status != "active":
        raise HTTPException(status_code=409, detail="Only active medications can be discontinued.")
    medication.status = "discontinued"
    medication.end_date = datetime.now(timezone.utc).date()
    _audit(context, clinic_id, medication.patient_id, "medication.discontinued", "medication", medication.id)
    context.db.commit()
    return {"medication_id": medication.id, "status": medication.status, "end_date": medication.end_date}


@router.get("/visits/{visit_id}/ai-suggestions", response_model=list[AISuggestionRead])
async def list_visit_suggestions(clinic_id: UUID, visit_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id)
    suggestions = repository.list_suggestions(clinic_id, visit.id)
    _audit(context, clinic_id, visit.patient_id, "ai_suggestion.read_by_doctor", "ai_suggestion_collection", visit.id)
    context.db.commit()
    return suggestions


@router.post("/visits/{visit_id}/ai-suggestions/draft-note", response_model=AISuggestionRead, status_code=status.HTTP_201_CREATED)
async def create_deterministic_note_draft(
    clinic_id: UUID,
    visit_id: UUID,
    body: DraftNoteRequest,
    context: AuthContext = Depends(require_clinic_role("doctor")),
):
    """Format doctor-entered sections as a visibly pending draft; no model makes clinical claims."""
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    sections = (
        ("Subjective", body.subjective),
        ("Objective", body.objective),
        ("Assessment", body.assessment),
        ("Plan", body.plan),
    )
    note_text = "DRAFT — Requires clinician review and signature\n\n" + "\n\n".join(
        f"{label}:\n{value.strip()}" for label, value in sections if value and value.strip()
    )
    suggestion = AISuggestion(
        clinic_id=clinic_id,
        patient_id=visit.patient_id,
        visit_id=visit.id,
        created_by_staff_id=staff.id,
        suggestion_type="note",
        content=note_text,
        structured_data={
            "generator": "deterministic_template",
            "prompt_version": "careflow-note-template-v1",
            "source_ids": [str(visit.id)],
            "clinician_supplied_sections": [label.lower() for label, value in sections if value and value.strip()],
        },
        model_name="deterministic-template",
        model_version="1",
        status="pending",
    )
    repository.add(suggestion)
    context.db.flush()
    _audit(context, clinic_id, visit.patient_id, "ai_note.draft_created", "ai_suggestion", suggestion.id,
           {"generator": "deterministic_template", "requires_human_review": True})
    context.db.commit()
    context.db.refresh(suggestion)
    return suggestion


@router.post("/visits/{visit_id}/ai-suggestions/{suggestion_id}/decision", response_model=AISuggestionRead)
async def decide_visit_suggestion(clinic_id: UUID, visit_id: UUID, suggestion_id: UUID, body: SuggestionDecision, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    suggestion = repository.get_suggestion(clinic_id, visit.id, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="AI suggestion not found for this visit.")
    if suggestion.status != "pending":
        raise HTTPException(status_code=409, detail="This AI suggestion has already been reviewed.")
    now = datetime.now(timezone.utc)
    suggestion.status = body.decision
    suggestion.decision_by_staff_id = staff.id
    suggestion.decision_at = now
    suggestion.decision_notes = body.decision_notes
    if body.decision == "accepted" and suggestion.suggestion_type.casefold() in {"note", "clinical_note", "clinical-note"}:
        versions = repository.list_notes(clinic_id, visit.id)
        repository.add(ClinicalNote(clinic_id=clinic_id, visit_id=visit.id, author_staff_id=staff.id,
                                    version=max((item.version for item in versions), default=0) + 1,
                                    content=suggestion.content, status="draft"))
    _audit(context, clinic_id, visit.patient_id, f"ai_suggestion.{body.decision}", "ai_suggestion", suggestion.id)
    context.db.commit()
    context.db.refresh(suggestion)
    return suggestion


@router.post("/visits/{visit_id}/complete")
async def complete_doctor_visit(clinic_id: UUID, visit_id: UUID, context: AuthContext = Depends(require_clinic_role("doctor"))):
    staff = _doctor_staff(clinic_id, context)
    repository = DoctorPortalRepository(context.db)
    existing = repository.get_visit(clinic_id, visit_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Visit not found in this clinic.")
    if existing.status == "completed":
        if existing.clinician_staff_id is not None and existing.clinician_staff_id != staff.id:
            raise HTTPException(status_code=403, detail="This visit is assigned to another doctor.")
        _require_patient_access(repository, clinic_id, existing.patient_id, staff.id)
        return {"visit_id": existing.id, "status": existing.status, "ended_at": existing.ended_at}
    visit = _require_visit_access(repository, clinic_id, visit_id, staff.id, for_update=True)
    if not any(note.status == "signed" for note in repository.list_notes(clinic_id, visit.id)):
        raise HTTPException(status_code=409, detail="Sign a clinical note before completing this visit.")
    visit.status = "completed"
    visit.ended_at = datetime.now(timezone.utc)
    if visit.appointment_id:
        from app.repositories.appointments import AppointmentRepository
        appointment = AppointmentRepository(context.db).get(clinic_id, visit.appointment_id)
        if appointment is not None:
            appointment.status = "completed"
    context.db.add(OutboxEvent(clinic_id=clinic_id, event_type="visit.completed", aggregate_type="visit",
                               aggregate_id=str(visit.id), payload={"visit_id": str(visit.id), "patient_id": str(visit.patient_id)}))
    _audit(context, clinic_id, visit.patient_id, "visit.completed_by_doctor", "visit", visit.id)
    context.db.commit()
    return {"visit_id": visit.id, "status": visit.status, "ended_at": visit.ended_at}
