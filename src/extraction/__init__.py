"""Smart Import extractors.

Each extractor function returns the canonical dict shape:
  {
    "extracted":        dict   # TestPatientPayload-shaped (label, demographics, ...)
    "warnings":         list[str]
    "snap_suggestions": dict[kind, list[{from, to, score}]]
  }

Phase 1 ships extract_text only. Phase 2 adds extract_pdf / extract_fhir;
Phase 3 adds extract_image. They all return the same dict shape so the
backend endpoint stays a single function with a dispatch on `kind`.
"""
from src.extraction.extract_text import extract_text

__all__ = ["extract_text"]
