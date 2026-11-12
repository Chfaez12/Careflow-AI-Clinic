"""Evidence-linked, deterministic summary builder for the free demo stack."""

from datetime import datetime, timezone
from uuid import UUID

from app.models.appointment import Appointment
from app.models.patient import Patient
from app.repositories.doctor_portal import DoctorPortalRepository


def build_previsit_summary(
    clinic_id: UUID,
    appointment: Appointment,
    patient: Patient,
    repository: DoctorPortalRepository,
) -> dict:
    facts: list[dict] = []
    sources: list[dict] = []

    def add_fact(text: str, source_type: str, source_id: UUID, recorded_at, label: str):
        facts.append({"text": text, "source_ids": [source_id]})
        sources.append({
            "source_type": source_type,
            "source_id": source_id,
            "recorded_at": recorded_at,
            "label": label,
        })

    add_fact(
        f"Scheduled visit: {appointment.reason or 'No reason supplied'}.",
        "appointment", appointment.id, appointment.created_at, "Scheduled appointment",
    )

    for allergy in repository.list_allergies(clinic_id, patient.id):
        if allergy.status == "active":
            reaction = f"; reaction: {allergy.reaction}" if allergy.reaction else ""
            severity = f"; severity: {allergy.severity}" if allergy.severity else ""
            add_fact(
                f"Active allergy: {allergy.substance}{reaction}{severity}.",
                "allergy", allergy.id, allergy.created_at, f"Allergy: {allergy.substance}",
            )

    for condition in repository.list_conditions(clinic_id, patient.id):
        if condition.status == "active":
            add_fact(
                f"Active condition: {condition.name}.",
                "medical_condition", condition.id, condition.created_at, f"Condition: {condition.name}",
            )

    for medication in repository.list_medications(clinic_id, patient.id):
        if medication.status == "active":
            instructions = ", ".join(value for value in (medication.dose, medication.route, medication.frequency) if value)
            add_fact(
                f"Active medication: {medication.name}{f' ({instructions})' if instructions else ''}.",
                "medication", medication.id, medication.created_at, f"Medication: {medication.name}",
            )

    visits = repository.list_patient_visits(clinic_id, patient.id)
    signed_notes = [
        note
        for visit in visits
        for note in repository.list_notes(clinic_id, visit.id)
        if note.status == "signed"
    ]
    if signed_notes:
        latest = max(signed_notes, key=lambda note: note.signed_at or note.created_at)
        excerpt = " ".join(latest.content.split())[:360]
        if len(" ".join(latest.content.split())) > 360:
            excerpt += "…"
        add_fact(
            f"Latest signed note excerpt: {excerpt}",
            "clinical_note", latest.id, latest.signed_at or latest.created_at, "Latest signed clinical note",
        )

    return {
        "clinic_id": clinic_id,
        "appointment_id": appointment.id,
        "patient_id": patient.id,
        "generated_at": datetime.now(timezone.utc),
        "facts": facts,
        "sources": sources,
        "disclaimer": "Draft for clinician review. Verify each fact against its linked source; this summary does not provide diagnosis or treatment advice.",
    }
