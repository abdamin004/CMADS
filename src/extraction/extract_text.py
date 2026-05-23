"""Phase 1: LLM-driven extraction from free-text clinical content."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import cfg
from src.llm.adapter import get_llm, invoke_with_retry
from src.extraction.guards import (
    validate_labs,
    validate_conditions,
    validate_medications,
    sanitize_demographics,
)

logger = structlog.get_logger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "extract_patient.yaml"

# Cap text at 32 kB to keep prompts bounded.
MAX_TEXT_BYTES = 32 * 1024


def _load_prompt() -> dict[str, str]:
    return yaml.safe_load(PROMPT_PATH.read_text())


def _extract_json(raw: str) -> dict[str, Any]:
    """Best-effort JSON parse — LLM may wrap in markdown fences, prepend
    chatter, etc. Strip whatever's around the first {...} block."""
    s = raw.strip()
    # Strip markdown fences
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # Find first {...} that brace-balances
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
                return json.loads(s[start : i + 1])
    raise ValueError("unterminated JSON object in model output")


def _snap_to_vocabulary(extracted: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """For each extracted condition / medication / lab term, find the
    closest cohort vocabulary entry via difflib. Suggestions returned
    separately so the UI can show them as 'snap to <X>' chips."""
    from difflib import SequenceMatcher
    from src.db.mongo import _coll, build_vocabularies

    # Build vocab once per call (cheap on the cached cohort)
    cursor = _coll("patient_cases").find(
        {}, {"conditions": 1, "medications": 1, "labs": 1}
    )
    vocab = build_vocabularies(list(cursor))

    THRESHOLD = 0.7

    def closest(term: str, candidates: list[dict]) -> tuple[str, float] | None:
        best: tuple[str | None, float] = (None, 0.0)
        tl = term.lower()
        for c in candidates:
            label = c.get("label") or ""
            score = SequenceMatcher(None, tl, label.lower()).ratio()
            if score > best[1]:
                best = (label, score)
        if best[0] and best[1] >= THRESHOLD and best[0].lower() != tl:
            return (best[0], best[1])  # type: ignore[return-value]
        return None

    out: dict[str, list[dict[str, Any]]] = {
        "conditions": [],
        "medications": [],
        "labs": [],
    }
    for cond in extracted.get("conditions", {}).get("active") or []:
        term = cond.get("condition") or ""
        if not term:
            continue
        hit = closest(term, vocab.get("condition", []))
        if hit:
            out["conditions"].append(
                {"from": term, "to": hit[0], "score": round(hit[1], 2)}
            )
    for med in extracted.get("medications", {}).get("active") or []:
        term = med.get("medication") or ""
        if not term:
            continue
        hit = closest(term, vocab.get("medication", []))
        if hit:
            out["medications"].append(
                {"from": term, "to": hit[0], "score": round(hit[1], 2)}
            )
    for lab in extracted.get("labs", {}).get("latest_labs") or []:
        term = lab.get("test_name") or ""
        if not term:
            continue
        hit = closest(term, vocab.get("lab", []))
        if hit:
            out["labs"].append(
                {"from": term, "to": hit[0], "score": round(hit[1], 2)}
            )
    return out


def extract_text(text: str) -> dict[str, Any]:
    """Phase-1 entry point. Returns the standard extractor dict."""
    if not text or not text.strip():
        raise ValueError("text input is empty")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError(f"text exceeds {MAX_TEXT_BYTES} bytes")

    prompt = _load_prompt()
    system_msg = SystemMessage(content=prompt["system"])
    user_msg = HumanMessage(content=prompt["user"].format(source_text=text))

    llm = get_llm(temperature=0.1, max_tokens=2048, json_mode=True)
    started = time.time()

    extracted: dict[str, Any] = {}
    for attempt in (1, 2):
        try:
            response = invoke_with_retry(
                llm,
                [system_msg, user_msg],
                agent_id="extract_patient",
            )
            raw: str = getattr(response, "content", None) or str(response)
            try:
                extracted = _extract_json(raw)
                break
            except (ValueError, json.JSONDecodeError):
                if attempt == 2:
                    raise
                # On second attempt strengthen the system message
                system_msg = SystemMessage(
                    content=prompt["system"]
                    + "\n\nIMPORTANT: Your previous response was not parseable JSON. "
                    "Respond with ONLY a JSON object, no surrounding text."
                )
        except Exception:
            if attempt == 2:
                raise

    duration_ms = int((time.time() - started) * 1000)

    warnings: list[str] = []
    if extracted.get("_rejected"):
        return {
            "extracted": {},
            "warnings": [
                f"rejected: {extracted.get('_reason') or 'not clinical content'}"
            ],
            "snap_suggestions": {"conditions": [], "medications": [], "labs": []},
            "model_used": getattr(llm, "model_name", "unknown"),
            "duration_ms": duration_ms,
        }

    # Strip _confidence fields out of the saved payload but keep them in a
    # parallel structure for the UI to read
    confidences: dict[str, Any] = {}

    def _strip_confidence(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            if "_confidence" in obj:
                confidences[path] = obj.pop("_confidence")
            for k, v in list(obj.items()):
                _strip_confidence(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _strip_confidence(item, f"{path}[{i}]")

    _strip_confidence(extracted)

    # Output guardrails: validate + cap each section before handing off.
    # Invalid rows are silently dropped (LLM occasionally emits garbage; one
    # bad row should not nuke the whole extraction).
    if isinstance(extracted.get("demographics"), dict):
        clean_demo = sanitize_demographics(extracted["demographics"])
        if clean_demo:
            extracted["demographics"] = clean_demo
    if isinstance(extracted.get("conditions"), dict):
        rows = extracted["conditions"].get("active") or []
        extracted["conditions"]["active"] = validate_conditions(rows)
    if isinstance(extracted.get("medications"), dict):
        rows = extracted["medications"].get("active") or []
        extracted["medications"]["active"] = validate_medications(rows)
    if isinstance(extracted.get("labs"), dict):
        rows = extracted["labs"].get("latest_labs") or []
        extracted["labs"]["latest_labs"] = validate_labs(rows)

    try:
        snap_suggestions = _snap_to_vocabulary(extracted)
    except Exception as e:  # noqa: BLE001
        logger.warning("snap_to_vocab_failed", error=str(e)[:200])
        snap_suggestions = {"conditions": [], "medications": [], "labs": []}

    return {
        "extracted": extracted,
        "warnings": warnings,
        "snap_suggestions": snap_suggestions,
        "confidences": confidences,
        "model_used": getattr(llm, "model_name", "unknown"),
        "duration_ms": duration_ms,
    }
