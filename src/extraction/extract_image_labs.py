"""Phase 3: lab-slip image → Gemini 2.5 Flash → labs only.

Narrower than text/PDF extraction by design: the clinician snaps a photo
of a lab printout, and we extract ONLY the lab rows (test_name, value,
unit). Demographics / conditions / medications are NOT extracted from
images — those belong in the editor's fields, not on a lab slip. The
output schema matches TestPatientPayload but only the labs.latest_labs
array is populated.

The model used is Gemini 2.5 Flash via the existing LLM adapter
(provider='gemini'). Gemini handles printed lab tables well and is
significantly cheaper than the heavier vision models.
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.adapter import get_llm, invoke_with_retry
from src.extraction.guards import (
    assert_image_signature,
    assert_image_dimensions,
    validate_labs,
)

logger = structlog.get_logger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

# Gemini 2.5 Flash. If the user later wants Pro or a different tier, swap here.
GEMINI_VISION_MODEL = "gemini-2.5-flash"

# Prompt — narrower than the all-fields extractor. Asks Gemini to read the
# lab slip and emit ONLY the labs array.
SYSTEM_PROMPT = """You are a clinical lab-report parser. The user will
attach an image of a printed lab slip. Read it carefully and emit a JSON
object with the following exact shape:

{
  "labs": [
    { "test_name": "<analyte name as printed>",
      "value":     "<numeric value as printed>",
      "unit":      "<unit as printed>" }
  ]
}

Rules:
- Extract every lab row you can read. One JSON entry per row.
- Use the analyte name as printed on the slip (do not translate or paraphrase).
- Value is a string (do not coerce numbers — keep "8.2" or "<0.1" or ">2000" verbatim).
- Unit is the unit shown next to the value (mg/dL, g/dL, %, etc.). Empty string if no unit.
- Do NOT extract demographics, dates, doctor names, or anything other than lab rows.
- If you cannot read any labs (e.g. the image is unclear, not a lab slip, or empty),
  respond with {"labs": [], "_reason": "<short reason>"}.
- Respond with ONLY the JSON object — no markdown fences, no commentary."""

USER_INSTRUCTION = "Extract the lab rows from this image."


def _extract_json(raw: str) -> dict[str, Any]:
    """Robust JSON extraction — strips markdown fences and finds the
    first balanced {...} block. Gemini sometimes wraps in ```json … ```
    despite instructions."""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    start = s.find("{")
    if start < 0:
        raise ValueError("no JSON object found in model output")
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(s[start:i + 1])
    raise ValueError("unterminated JSON object in model output")


def extract_image_labs(content: bytes, filename: str = "uploaded.png",
                       mime: str = "image/png") -> dict[str, Any]:
    """Phase 3 entry point — image → labs only.

    Returns the canonical extractor dict; the `extracted` field always
    has the full TestPatientPayload shape but only `labs.latest_labs`
    is ever populated."""
    if not content:
        raise ValueError("image content is empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} bytes ({len(content)})")
    # Magic-byte sniff: reject if the file content doesn't match the claimed
    # MIME (defeats Content-Type spoofing — a .exe with mime=image/png).
    assert_image_signature(content, mime)
    # Decompression-bomb defence: header-only Pillow read.
    assert_image_dimensions(content)

    # Encode the image as a data URL.  LangChain Google GenAI accepts
    # `image_url` content parts via the OpenAI-compatible message shape.
    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": USER_INSTRUCTION},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    system_msg = SystemMessage(content=SYSTEM_PROMPT)
    user_msg = HumanMessage(content=user_content)

    # Get a Gemini 2.5 Flash LLM regardless of the default provider.
    try:
        llm = get_llm(
            temperature=0.1,
            max_tokens=2048,
            json_mode=True,
            provider="gemini",
            model=GEMINI_VISION_MODEL,
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"Gemini not available for image extraction: {e}. "
            f"Set GOOGLE_API_KEY in .env to enable image upload."
        )

    started = time.time()
    parsed: dict[str, Any] = {}
    for attempt in (1, 2):
        try:
            response = invoke_with_retry(
                llm, [system_msg, user_msg],
                agent_id="extract_image_labs",
            )
            raw: str = getattr(response, "content", None) or str(response)
            try:
                parsed = _extract_json(raw)
                break
            except Exception:
                if attempt == 2:
                    raise
        except Exception:
            if attempt == 2:
                raise

    duration_ms = int((time.time() - started) * 1000)
    labs_in = parsed.get("labs") or []
    reason = parsed.get("_reason") or ""

    # Reshape into the canonical TestPatientPayload-style envelope:
    # everything empty except labs.latest_labs. Each row passes through
    # Pydantic validation; malformed rows are dropped, not raised.
    latest_labs = validate_labs(labs_in)

    warnings: list[str] = []
    if not latest_labs:
        warnings.append(
            f"No labs detected{f' — {reason}' if reason else ''}. "
            f"Try a clearer image or use the Paste text tab."
        )

    extracted = {
        "label":         f"Lab-slip import — {filename}",
        "demographics":  {},
        "conditions":    {"active": []},
        "medications":   {"active": []},
        "labs":          {"latest_labs": latest_labs},
    }

    return {
        "extracted":         extracted,
        "warnings":          warnings,
        "snap_suggestions":  {"conditions": [], "medications": [], "labs": []},
        "confidences":       {},
        "model_used":        f"gemini · {GEMINI_VISION_MODEL}",
        "duration_ms":       duration_ms,
        "source":            {"kind": "image", "filename": filename, "mime": mime, "bytes": len(content)},
    }
