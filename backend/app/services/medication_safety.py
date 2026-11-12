"""Conservative matching against this clinic's recorded medication history only."""

from app.models.allergy import Allergy
from app.models.medication import Medication


def record_match_warnings(
    medication_name: str,
    rxnorm_code: str | None,
    allergies: list[Allergy],
    medications: list[Medication],
) -> list[dict]:
    normalized_name = " ".join(medication_name.casefold().split())
    warnings: list[dict] = []
    for allergy in allergies:
        if allergy.status != "active":
            continue
        normalized_substance = " ".join(allergy.substance.casefold().split())
        if normalized_substance and (
            normalized_substance in normalized_name or normalized_name in normalized_substance
        ):
            severity = (allergy.severity or "unknown").casefold().replace("_", "-")
            warnings.append({
                "category": "recorded_allergy_name_match",
                "severity": "severe" if severity in {"severe", "life-threatening", "anaphylaxis"} else "review",
                "source_id": allergy.id,
                "message": f"The prescription name matches an active recorded allergy ({allergy.substance}).",
            })
    for medication in medications:
        if medication.status != "active":
            continue
        same_code = bool(rxnorm_code and medication.rxnorm_code and rxnorm_code == medication.rxnorm_code)
        same_name = " ".join(medication.name.casefold().split()) == normalized_name
        if same_code or same_name:
            warnings.append({
                "category": "possible_duplicate_active_medication",
                "severity": "review",
                "source_id": medication.id,
                "message": f"An active medication record already matches {medication.name}.",
            })
    return warnings
