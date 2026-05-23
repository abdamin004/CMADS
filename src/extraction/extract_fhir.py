"""Phase 2: FHIR R4/R5 Bundle or single-resource JSON → deterministic parse.

No LLM call. Walks the standard FHIR resources and maps them to
TestPatientPayload shape. Accepts both raw Bundle entries and a top-level
single Patient/Observation/etc resource.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Any

import structlog

from src.extraction.guards import (
    assert_json_depth,
    MAX_FHIR_RESOURCES,
    validate_labs,
    validate_conditions,
    validate_medications,
    sanitize_demographics,
)

logger = structlog.get_logger(__name__)

MAX_FHIR_BYTES = 5 * 1024 * 1024  # 5 MB cap


def _age_from_birthdate(birth_date: str | None) -> int | None:
    if not birth_date:
        return None
    try:
        dob = datetime.fromisoformat(birth_date[:10])
        today = datetime.utcnow()
        years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return max(0, min(120, years))
    except (ValueError, TypeError):
        return None


def _gender_from_fhir(g: str | None) -> str | None:
    if not g:
        return None
    g = g.lower()
    if g in ("male", "m"):   return "M"
    if g in ("female", "f"): return "F"
    if g in ("other", "unknown"):
        return "Other"
    return None


def _extract_patient(res: dict) -> dict[str, Any]:
    return {
        "age":    _age_from_birthdate(res.get("birthDate")),
        "gender": _gender_from_fhir(res.get("gender")),
    }


def _extract_condition(res: dict) -> dict[str, Any] | None:
    clinical = (res.get("clinicalStatus") or {})
    coding = clinical.get("coding") or []
    is_active = any((c.get("code") or "").lower() == "active" for c in coding) or not coding
    if not is_active:
        return None
    code_block = res.get("code") or {}
    text = code_block.get("text")
    code_codings = code_block.get("coding") or []
    snomed = next((c.get("code") for c in code_codings
                   if "snomed" in (c.get("system") or "").lower()), None)
    display = text or (code_codings[0].get("display") if code_codings else None)
    if not display:
        return None
    return {"condition": display, "code": snomed}


def _extract_medication(res: dict) -> dict[str, Any] | None:
    status = (res.get("status") or "").lower()
    if status and status not in ("active", "on-hold"):
        return None
    code_block = res.get("medicationCodeableConcept") or res.get("medication") or {}
    if isinstance(code_block, dict):
        text = code_block.get("text")
        codings = code_block.get("coding") or []
        rxnorm = next((c.get("code") for c in codings
                       if "rxnorm" in (c.get("system") or "").lower()), None)
        display = text or (codings[0].get("display") if codings else None)
        if not display:
            return None
        return {"medication": display, "rx_code": rxnorm}
    return None


def _extract_observation(res: dict) -> dict[str, Any] | None:
    category = res.get("category") or []
    # Only labs (category=laboratory)
    is_lab = False
    for cat in category:
        for c in (cat.get("coding") or []):
            if (c.get("code") or "").lower() == "laboratory":
                is_lab = True
                break
    if not is_lab:
        return None

    code_block = res.get("code") or {}
    test_name = code_block.get("text") or next(
        (c.get("display") for c in (code_block.get("coding") or []) if c.get("display")),
        None,
    )
    if not test_name:
        return None

    value = res.get("valueQuantity") or {}
    return {
        "test_name": test_name,
        "value":     str(value.get("value")) if value.get("value") is not None else "",
        "unit":      value.get("unit") or "",
    }


def extract_fhir(content: bytes, filename: str = "uploaded.json") -> dict[str, Any]:
    """Parse a FHIR Bundle (or single resource) into a TestPatientPayload shape."""
    if len(content) > MAX_FHIR_BYTES:
        raise ValueError(f"FHIR file exceeds {MAX_FHIR_BYTES} bytes")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid JSON: {e}")

    # JSON-depth cap — defends against deeply nested JSON DoS.
    assert_json_depth(data)

    # Normalise to a list of resources
    if isinstance(data, dict) and data.get("resourceType") == "Bundle":
        resources = [(e.get("resource") or {}) for e in (data.get("entry") or [])]
    elif isinstance(data, dict) and data.get("resourceType"):
        resources = [data]
    elif isinstance(data, list):
        resources = data
    else:
        raise ValueError("not a recognised FHIR shape (need Bundle, resource, or list)")

    if len(resources) > MAX_FHIR_RESOURCES:
        raise ValueError(
            f"FHIR bundle has {len(resources)} resources (max {MAX_FHIR_RESOURCES})"
        )

    extracted: dict[str, Any] = {
        "label":         f"FHIR import — {filename}",
        "demographics":  {},
        "conditions":    {"active": []},
        "medications":   {"active": []},
        "labs":          {"latest_labs": []},
    }
    warnings: list[str] = []

    saw_patient = False
    for res in resources:
        if not isinstance(res, dict):
            continue
        rtype = res.get("resourceType")
        try:
            if rtype == "Patient":
                d = _extract_patient(res)
                if d.get("age") is not None or d.get("gender"):
                    extracted["demographics"].update({k: v for k, v in d.items() if v is not None})
                    saw_patient = True
            elif rtype == "Condition":
                row = _extract_condition(res)
                if row:
                    extracted["conditions"]["active"].append(row)
            elif rtype == "MedicationRequest":
                row = _extract_medication(res)
                if row:
                    extracted["medications"]["active"].append(row)
            elif rtype == "Observation":
                row = _extract_observation(res)
                if row:
                    extracted["labs"]["latest_labs"].append(row)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"skipped a {rtype}: {e}")

    if not saw_patient:
        warnings.append("no Patient resource — demographics not extracted")

    n_extracted = (
        len(extracted["conditions"]["active"])
        + len(extracted["medications"]["active"])
        + len(extracted["labs"]["latest_labs"])
        + (1 if saw_patient else 0)
    )
    if n_extracted == 0:
        raise ValueError("no usable FHIR resources found in the file")

    # Apply output guardrails: row caps + length caps + sanitization.
    extracted["demographics"] = (
        sanitize_demographics(extracted["demographics"]) or extracted["demographics"]
    )
    extracted["conditions"]["active"]  = validate_conditions(extracted["conditions"]["active"])
    extracted["medications"]["active"] = validate_medications(extracted["medications"]["active"])
    extracted["labs"]["latest_labs"]   = validate_labs(extracted["labs"]["latest_labs"])

    return {
        "extracted":         extracted,
        "warnings":          warnings,
        "snap_suggestions":  {"conditions": [], "medications": [], "labs": []},
        "confidences":       {},
        "model_used":        "deterministic-fhir-parser",
        "duration_ms":       0,
        "source":            {"kind": "fhir", "filename": filename,
                              "resource_count": len(resources)},
    }
