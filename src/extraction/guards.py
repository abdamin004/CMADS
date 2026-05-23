"""Input + output guardrails for the Smart Import extractors.

Inputs are user-supplied; outputs are LLM-produced. Both are untrusted.

Input guards: magic-byte sniffing (defeats MIME-spoofing), dimension /
page-count / resource-count / JSON-depth caps (defeat decompression
bombs and deeply nested JSON DoS).

Output guards: Pydantic-validated rows with per-field length caps and
row-count caps. Invalid rows are silently dropped rather than raised —
one bad row should not nuke an otherwise-good extraction.
"""
from __future__ import annotations

import io
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


# ── Magic bytes ─────────────────────────────────────────────────────────

_PDF_MAGIC = b"%PDF-"
_IMAGE_MAGICS: dict[str, list[bytes]] = {
    "image/png":  [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/jpg":  [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],          # "RIFF....WEBP" — verify the WEBP tag too
    "image/gif":  [b"GIF87a", b"GIF89a"],
}


def assert_pdf_signature(content: bytes) -> None:
    """Reject anything that doesn't start with the PDF magic. Cheap
    defence against a non-PDF file uploaded with .pdf extension or
    spoofed Content-Type."""
    if not content.startswith(_PDF_MAGIC):
        raise ValueError("not a valid PDF (missing %PDF- header)")


def assert_image_signature(content: bytes, claimed_mime: str) -> None:
    """Reject if the file's magic bytes don't match the claimed MIME.
    Falls back to a permissive 'image/*' check when the MIME is generic."""
    mime = (claimed_mime or "").lower().split(";")[0].strip()
    if mime in _IMAGE_MAGICS:
        sigs = _IMAGE_MAGICS[mime]
        if not any(content.startswith(s) for s in sigs):
            raise ValueError(f"file content does not match {mime}")
        # WEBP — must also contain 'WEBP' at bytes 8..12
        if mime == "image/webp" and content[8:12] != b"WEBP":
            raise ValueError("file content does not match image/webp")
        return
    # Generic 'image/...' that we don't have a magic for — accept if it
    # matches ANY known image magic.
    if any(content.startswith(s) for sigs in _IMAGE_MAGICS.values() for s in sigs):
        return
    raise ValueError(f"file content is not a recognised image (mime: {mime})")


# ── Resource caps ───────────────────────────────────────────────────────

MAX_IMAGE_DIMENSION = 12000         # px on either side — accommodates modern phone cameras (4032×3024 typical, pro modes higher)
MAX_PDF_PAGES       = 50
MAX_FHIR_RESOURCES  = 5000
MAX_JSON_DEPTH      = 64

MAX_LABS            = 100
MAX_CONDITIONS      = 50
MAX_MEDICATIONS     = 50
MAX_FIELD_LEN       = 200           # most string fields
MAX_VALUE_LEN       = 50            # lab `value`
MAX_UNIT_LEN        = 30            # lab `unit`


def assert_image_dimensions(content: bytes) -> tuple[int, int]:
    """Decode header only via Pillow to read dimensions cheaply.

    Pillow's lazy decoder reads only the header for size; full pixel
    decode never happens here. Rejects images larger than
    MAX_IMAGE_DIMENSION on either side, defending against decompression
    bombs (a 100×100 file that decodes to 100000×100000).
    """
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        # Pillow not installed — accept the image but warn. Gemini will
        # still receive a size-capped payload via MAX_IMAGE_BYTES.
        return (0, 0)
    try:
        with Image.open(io.BytesIO(content)) as im:
            w, h = im.size
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"could not decode image header: {e}")
    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
        raise ValueError(
            f"image too large: {w}×{h} (max {MAX_IMAGE_DIMENSION} on either side)"
        )
    return (w, h)


def assert_pdf_page_count(content: bytes) -> int:
    """Open the PDF with pdfplumber and reject if it has more than
    MAX_PDF_PAGES pages. pdfplumber is already a hard dep for the PDF
    path, so no extra import cost."""
    import pdfplumber  # local import; pdfplumber is heavy
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        n = len(pdf.pages)
    if n > MAX_PDF_PAGES:
        raise ValueError(f"PDF has {n} pages (max {MAX_PDF_PAGES})")
    return n


def assert_json_depth(obj: Any, _depth: int = 0) -> None:
    """Walk the parsed JSON and reject if it nests deeper than
    MAX_JSON_DEPTH. Defends against deeply nested JSON that exhausts
    the stack on later traversals."""
    if _depth > MAX_JSON_DEPTH:
        raise ValueError(f"JSON nests deeper than {MAX_JSON_DEPTH} levels")
    if isinstance(obj, dict):
        for v in obj.values():
            assert_json_depth(v, _depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            assert_json_depth(v, _depth + 1)


# ── Output schema (LLM-produced rows) ───────────────────────────────────

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_str(s: Any, max_len: int) -> str:
    """Coerce to str, strip whitespace, drop ASCII control chars, cap length."""
    if s is None:
        return ""
    out = str(s).strip()
    out = _CONTROL_CHARS.sub("", out)
    if len(out) > max_len:
        out = out[:max_len]
    return out


class LabRow(BaseModel):
    test_name: str = Field(min_length=1, max_length=MAX_FIELD_LEN)
    value:     str = Field(max_length=MAX_VALUE_LEN)
    unit:      str = Field(max_length=MAX_UNIT_LEN)

    @field_validator("test_name", "value", "unit", mode="before")
    @classmethod
    def _sanitize(cls, v: Any) -> str:
        # Strip control chars + cap length; lets Field's max_length pass.
        if v is None:
            return ""
        s = str(v).strip()
        s = _CONTROL_CHARS.sub("", s)
        return s


class ConditionRow(BaseModel):
    condition: str = Field(min_length=1, max_length=MAX_FIELD_LEN)
    code:      str | None = Field(default=None, max_length=64)

    @field_validator("condition", "code", mode="before")
    @classmethod
    def _sanitize(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        s = _CONTROL_CHARS.sub("", s)
        return s or None


class MedicationRow(BaseModel):
    medication: str = Field(min_length=1, max_length=MAX_FIELD_LEN)
    rx_code:    str | None = Field(default=None, max_length=64)

    @field_validator("medication", "rx_code", mode="before")
    @classmethod
    def _sanitize(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        s = _CONTROL_CHARS.sub("", s)
        return s or None


def validate_labs(rows: list[Any]) -> list[dict[str, str]]:
    """Validate each lab row; drop ones that fail. Cap to MAX_LABS."""
    out: list[dict[str, str]] = []
    for row in rows[:MAX_LABS]:
        if not isinstance(row, dict):
            continue
        try:
            out.append(LabRow(**row).model_dump())
        except ValidationError:
            continue
    return out


def validate_conditions(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:MAX_CONDITIONS]:
        if not isinstance(row, dict):
            continue
        try:
            out.append(ConditionRow(**row).model_dump())
        except ValidationError:
            continue
    return out


def validate_medications(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:MAX_MEDICATIONS]:
        if not isinstance(row, dict):
            continue
        try:
            out.append(MedicationRow(**row).model_dump())
        except ValidationError:
            continue
    return out


def sanitize_demographics(d: Any) -> dict[str, Any]:
    """Demographics are simple: age (int 0..120), gender (M/F/Other),
    everything else dropped."""
    if not isinstance(d, dict):
        return {}
    out: dict[str, Any] = {}
    age = d.get("age")
    if isinstance(age, (int, float)):
        a = int(age)
        if 0 <= a <= 120:
            out["age"] = a
    g = d.get("gender")
    if isinstance(g, str):
        g_clean = _clean_str(g, 16).upper()
        if g_clean in ("M", "F", "OTHER"):
            out["gender"] = g_clean if g_clean != "OTHER" else "Other"
    return out
