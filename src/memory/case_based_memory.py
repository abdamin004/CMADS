"""Tier 4 — Case-Based Memory.

Past patient cases stored in Qdrant as vector embeddings. After each run,
the memory_consolidation_node indexes the patient: a short clinical-feature
text is embedded with BioLORD and stored alongside the run's outcome
(matched diagnosis, match type, rank, key evidence). On a new run, the
Diagnostic agent queries by the new patient's features and gets the top-K
most similar past patients to use as a Bayesian-style prior.

This is what makes a vector DB useful for memory: case-similarity recall.
NICE guidelines stay where they were (the `nice_guidelines` collection
used by the Treatment agent) — they are reference knowledge, not memory.

Graceful degradation: if Qdrant is unreachable or the embedding model
isn't installed, every public method returns an empty result instead of
raising — the pipeline must keep running.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

import structlog

from src.config import cfg

logger = structlog.get_logger()


# Collection name kept distinct from the NICE guidelines collection.
PATIENT_COLLECTION = "patient_cases"


# ── Lazy globals ───────────────────────────────────────────
_lock = threading.Lock()
_client = None  # qdrant_client.QdrantClient
_model = None   # sentence_transformers.SentenceTransformer
_collection_ready = False


def _get_client():
    """Lazy QdrantClient. Returns None if Qdrant isn't configured/reachable."""
    global _client
    if _client is not None:
        return _client
    if not cfg.QDRANT_URL:
        return None
    with _lock:
        if _client is None:
            try:
                from qdrant_client import QdrantClient
                _client = QdrantClient(
                    url=cfg.QDRANT_URL, api_key=cfg.QDRANT_API_KEY
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "case_based_memory_client_init_failed",
                    error=str(e)[:120],
                )
                return None
    return _client


def _get_model():
    """Lazy SentenceTransformer. Returns None if it can't be loaded."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            try:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(cfg.EMBEDDING_MODEL)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "case_based_memory_model_load_failed",
                    error=str(e)[:120],
                )
                return None
    return _model


def _ensure_collection(client) -> bool:
    """Create the patient_cases collection on demand. Idempotent."""
    global _collection_ready
    if _collection_ready:
        return True
    try:
        from qdrant_client.models import Distance, VectorParams
        existing = {c.name for c in client.get_collections().collections}
        if PATIENT_COLLECTION not in existing:
            model = _get_model()
            if model is None:
                return False
            dim = model.get_sentence_embedding_dimension()
            client.create_collection(
                collection_name=PATIENT_COLLECTION,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(
                "case_based_collection_created",
                collection=PATIENT_COLLECTION, dim=dim,
            )
        _collection_ready = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "case_based_ensure_collection_failed",
            error=str(e)[:120],
        )
        return False


# ── Feature extraction (no LLM — deterministic) ────────────

def build_case_text(ehr_case: dict, lab_case: dict,
                    ehr_summary: dict | None = None,
                    lab_summary: dict | None = None) -> str:
    """Compact clinical-feature text used both at index-time and recall-time.

    Uses the upstream agent summaries when available (they are already
    cleaned + ranked); falls back to the raw Gold-layer case otherwise.
    """
    parts: list[str] = []

    # Demographics
    demo = (ehr_case or {}).get("demographics") or {}
    age = demo.get("age")
    sex = demo.get("sex") or demo.get("gender")
    race = demo.get("race")
    if age or sex or race:
        bits = []
        if age is not None: bits.append(f"age {age}")
        if sex: bits.append(str(sex))
        if race: bits.append(str(race))
        parts.append("Demographics: " + ", ".join(bits))

    # Active conditions — prefer the EHR analyst's curated list.
    conditions = []
    if ehr_summary:
        for p in (ehr_summary.get("active_problems") or []):
            if isinstance(p, dict) and p.get("name"):
                conditions.append(p["name"])
    if not conditions:
        for c in (ehr_case.get("conditions") or [])[:12]:
            if isinstance(c, dict) and c.get("description"):
                conditions.append(c["description"])
    if conditions:
        parts.append("Active conditions: " + "; ".join(conditions[:10]))

    # Active medications
    meds = []
    if ehr_summary:
        for m in (ehr_summary.get("active_medications") or []):
            if isinstance(m, dict) and m.get("name"):
                meds.append(m["name"])
    if not meds:
        for m in (ehr_case.get("medications") or [])[:12]:
            if isinstance(m, dict) and m.get("description"):
                meds.append(m["description"])
    if meds:
        parts.append("Active medications: " + "; ".join(meds[:10]))

    # Key lab abnormalities — prefer the lab interpreter's ranked findings.
    labs: list[str] = []
    if lab_summary:
        for f in (lab_summary.get("findings") or [])[:8]:
            if isinstance(f, dict) and f.get("test_name"):
                labs.append(
                    f"{f['test_name']} = {f.get('value', '?')} "
                    f"({f.get('classification', '?')})"
                )
    if not labs:
        for ob in (lab_case.get("latest_labs") or [])[:8]:
            if isinstance(ob, dict) and ob.get("test_name"):
                val = ob.get("value", "?")
                unit = ob.get("unit", "")
                labs.append(f"{ob['test_name']} = {val} {unit}".strip())
    if labs:
        parts.append("Key labs: " + "; ".join(labs))

    # Risk factor summary if EHR analyst gave one.
    if ehr_summary and ehr_summary.get("risk_factor_summary"):
        rf = str(ehr_summary["risk_factor_summary"])[:200]
        parts.append("Risk factors: " + rf)

    return ". ".join(parts) if parts else "(no patient features available)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Public API ─────────────────────────────────────────────


class CaseBasedMemory:
    """Tier 4 — past-patient case store backed by Qdrant.

    Two operations matter:
      - index_patient(...)  — called by the memory_consolidation_node after
        a run completes; embeds a feature text and stores it with the
        run's outcome.
      - recall(...)         — called by upstream agents (or the prompt
        builder) at the start of a new run to retrieve the top-K most
        similar past cases as priors.
    """

    def __init__(self, collection: str = PATIENT_COLLECTION):
        self.collection = collection

    # ── Reads ──────────────────────────────────────────────

    def recall(
        self,
        patient_context: dict,
        ehr_summary: dict | None = None,
        lab_summary: dict | None = None,
        top_k: int = 5,
        exclude_uuid: str | None = None,
    ) -> list[dict]:
        """Return the top-K most similar past patient cases.

        Each result dict contains: patient_uuid, score, matched_diagnosis,
        match_type, rank_when_found, primary_confidence, case_text,
        evidence_patterns (short list of strings).
        """
        client = _get_client()
        model = _get_model()
        if client is None or model is None:
            return []
        if not _ensure_collection(client):
            return []

        ehr_case = (patient_context or {}).get("ehr_case") or {}
        lab_case = (patient_context or {}).get("lab_case") or {}
        text = build_case_text(ehr_case, lab_case, ehr_summary, lab_summary)
        try:
            embedding = _to_list(model.encode(text))
            results = client.query_points(
                collection_name=self.collection,
                query=embedding,
                limit=top_k + (1 if exclude_uuid else 0),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("case_based_recall_failed", error=str(e)[:120])
            return []

        out: list[dict] = []
        for r in results.points:
            payload = r.payload or {}
            uuid = payload.get("patient_uuid")
            if exclude_uuid and uuid == exclude_uuid:
                continue
            out.append({
                "patient_uuid": uuid,
                "score": round(float(r.score), 3),
                "matched_diagnosis": payload.get("matched_diagnosis"),
                "match_type": payload.get("match_type"),
                "rank_when_found": payload.get("rank_when_found"),
                "primary_confidence": payload.get("primary_confidence"),
                "case_text": payload.get("case_text", "")[:240],
                "evidence_patterns": payload.get("evidence_patterns") or [],
                "indexed_at": payload.get("indexed_at"),
            })
            if len(out) >= top_k:
                break
        return out

    # ── Writes ─────────────────────────────────────────────

    def index_patient(
        self,
        patient_uuid: str,
        ehr_case: dict,
        lab_case: dict,
        matched_diagnosis: str,
        match_type: str,
        rank_when_found: int | None = None,
        primary_confidence: float | None = None,
        evidence_patterns: list[str] | None = None,
        ehr_summary: dict | None = None,
        lab_summary: dict | None = None,
    ) -> bool:
        """Embed and upsert a single patient case. Returns True on success."""
        client = _get_client()
        model = _get_model()
        if client is None or model is None:
            return False
        if not _ensure_collection(client):
            return False

        text = build_case_text(ehr_case, lab_case, ehr_summary, lab_summary)
        try:
            embedding = _to_list(model.encode(text))
            from qdrant_client.models import PointStruct
            point_id = _stable_id_from_uuid(patient_uuid)
            client.upsert(
                collection_name=self.collection,
                points=[PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "patient_uuid": patient_uuid,
                        "case_text": text,
                        "matched_diagnosis": matched_diagnosis,
                        "match_type": match_type,
                        "rank_when_found": rank_when_found,
                        "primary_confidence": primary_confidence,
                        "evidence_patterns": (evidence_patterns or [])[:6],
                        "indexed_at": _now_iso(),
                    },
                )],
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("case_based_index_failed",
                           uuid=patient_uuid[:12], error=str(e)[:120])
            return False

    # ── Helpers used by agents to format priors for prompts ─

    @staticmethod
    def summarize_for_prompt(cases: list[dict], max_lines: int = 5) -> str:
        """Human-readable digest of recall() output for prompt injection."""
        if not cases:
            return "(no similar past patient cases found)"
        lines = [
            "Top similar past patients (case-based prior):",
        ]
        for c in cases[:max_lines]:
            label = c.get("matched_diagnosis") or "Unknown"
            mt = c.get("match_type") or "?"
            sc = c.get("score")
            rank = c.get("rank_when_found")
            rank_str = f", rank-{rank}" if rank else ""
            lines.append(
                f"  - score={sc} → {label} ({mt}{rank_str})"
            )
        return "\n".join(lines)


def _to_list(emb) -> list[float]:
    """Convert a SentenceTransformer encode() result (numpy ndarray) to a
    plain Python list. Tolerates plain lists too (used in tests)."""
    if hasattr(emb, "tolist"):
        return emb.tolist()
    return list(emb)


def _stable_id_from_uuid(uuid: str) -> int:
    """Qdrant point IDs must be int or UUID. We hash the patient UUID into an
    unsigned 63-bit integer so re-indexing the same patient is idempotent."""
    import hashlib
    h = hashlib.sha256(uuid.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") >> 1  # 63-bit, fits in int64


# Module-level singleton (stateless — safe to share)
_singleton: CaseBasedMemory | None = None


def get_case_based_memory() -> CaseBasedMemory:
    global _singleton
    if _singleton is None:
        _singleton = CaseBasedMemory()
    return _singleton
