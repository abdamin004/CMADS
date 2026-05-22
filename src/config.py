"""Central configuration — all tuneable settings in one place.

Reads from environment variables with sensible defaults.
Users configure via .env file — no code changes needed.

Usage:
    from src.config import cfg
    print(cfg.LLM_PROVIDER)           # "groq"
    print(cfg.DIAGNOSTIC_MAX_ROUNDS)  # 3
    print(cfg.GOLD_DIR)               # Path("data/gold/patient_cases")
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env(key: str, default: str) -> str:
    """Read env var at access time (not import time) for testability."""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


class Config:
    """All configurable settings, read from environment variables on access."""

    # ── LLM Provider ────────────────────────────────────────
    @property
    def LLM_PROVIDER(self) -> str:
        return _env("LLM_PROVIDER", "groq")

    @property
    def LLM_MODEL(self) -> str:
        return _env("LLM_MODEL", "openai/gpt-oss-120b")

    @property
    def LLM_EVALUATOR_MODEL(self) -> str:
        return _env("LLM_EVALUATOR_MODEL", "qwen/qwen3-32b")

    @property
    def LLM_EVALUATOR_PROVIDER(self) -> str:
        return _env("LLM_EVALUATOR_PROVIDER", "")

    # ── Ollama (local) ──────────────────────────────────────
    @property
    def OLLAMA_URL(self) -> str:
        return _env("OLLAMA_URL", "http://localhost:11434")

    @property
    def OLLAMA_CONTEXT_WINDOW(self) -> int:
        return _env_int("OLLAMA_CONTEXT_WINDOW", 16384)

    # ── Qdrant / Vector DB ─────────────────────────────────
    @property
    def QDRANT_URL(self) -> str:
        return _env("QDRANT_URL", "")

    @property
    def QDRANT_API_KEY(self) -> str:
        return _env("QDRANT_API_KEY", "")

    @property
    def EMBEDDING_MODEL(self) -> str:
        return _env("EMBEDDING_MODEL", "FremyCompany/BioLORD-2023")

    @property
    def QDRANT_COLLECTION(self) -> str:
        return _env("QDRANT_COLLECTION", "nice_guidelines")

    # ── Agent Tuning ────────────────────────────────────────
    @property
    def DIAGNOSTIC_MAX_ROUNDS(self) -> int:
        return _env_int("DIAGNOSTIC_MAX_ROUNDS", 3)

    @property
    def DIAGNOSTIC_CONFIDENCE_THRESHOLD(self) -> int:
        return _env_int("DIAGNOSTIC_CONFIDENCE_THRESHOLD", 75)

    # ── Data Paths ──────────────────────────────────────────
    @property
    def GOLD_DIR(self) -> Path:
        return Path(_env("GOLD_DIR", "data/gold/patient_cases"))

    @property
    def MAS_RESULTS_DIR(self) -> Path:
        return Path(_env("MAS_RESULTS_DIR", "data/gold/mas_results"))

    @property
    def GUIDELINES_DIR(self) -> Path:
        return Path(_env("GUIDELINES_DIR", "config/guidelines"))

    @property
    def DUCKDB_PATH(self) -> Path:
        return Path(_env("DUCKDB_PATH", "data/clinical.duckdb"))

    # ── Multi-Level Memory ──────────────────────────────────
    @property
    def MEMORY_ENABLED(self) -> bool:
        """Master switch for the multi-level memory subsystem.

        When false, agents skip reading/writing memory and the pipeline
        behaves exactly as it did before the feature was added. Used for
        before/after experiments.
        """
        return _env("MEMORY_ENABLED", "true").lower() in ("1", "true", "yes", "on")

    @property
    def SEMANTIC_MEMORY_PATH(self) -> Path:
        return Path(_env(
            "SEMANTIC_MEMORY_PATH",
            "data/gold/memory/semantic_memory.json",
        ))

    @property
    def EPISODIC_MEMORY_MAX_EVENTS(self) -> int:
        """Max events injected into a downstream agent's prompt."""
        return _env_int("EPISODIC_MEMORY_MAX_EVENTS", 30)

    # ── Tier-4 case-based memory knobs (thesis-safe defaults) ──
    @property
    def MEMORY_CASE_TOP_K(self) -> int:
        """Number of similar past patients the Diagnostic agent recalls."""
        return _env_int("MEMORY_CASE_TOP_K", 3)

    # ── MongoDB storage ─────────────────────────────────────
    @property
    def MONGO_URI(self) -> str:
        return _env("MONGO_URI", "mongodb://localhost:27017")

    @property
    def MONGO_DB(self) -> str:
        return _env("MONGO_DB", "cmads")

    @property
    def USE_MONGO(self) -> bool:
        """Master flag for the filesystem→Mongo migration. When false,
        the runtime reads and writes the on-disk JSON tree as before.
        See docs/superpowers/specs/2026-05-22-mongodb-migration-design.md."""
        return _env("USE_MONGO", "false").lower() in ("1", "true", "yes", "on")

    @property
    def MEMORY_CASE_MIN_SCORE(self) -> float:
        """Minimum cosine similarity for a past case to be used as a prior.

        0.5 = loose (more priors, more noise).  0.75 = strict (fewer
        priors, all clearly similar). Default 0.75 for thesis-safe mode.
        """
        try:
            return float(_env("MEMORY_CASE_MIN_SCORE", "0.75"))
        except ValueError:
            return 0.75

    @property
    def MEMORY_CASE_MATCH_TYPES(self) -> set[str]:
        """Comma-separated whitelist of judge match types eligible for recall.

        Default DIRECT only — INDIRECT/MISS cases as priors create
        echo-chamber risk. Set to "DIRECT,INDIRECT" for looser recall.
        """
        raw = _env("MEMORY_CASE_MATCH_TYPES", "DIRECT")
        return {t.strip().upper() for t in raw.split(",") if t.strip()}

    @property
    def MEMORY_WRITE_CASE_MATCH_TYPES(self) -> set[str]:
        """Match types that get written to Qdrant `patient_cases` at all.

        Default DIRECT only — keeps the case-based store itself free of
        MISS/INDIRECT pollution. Tier-3 semantic stats still record all
        match types regardless.
        """
        raw = _env("MEMORY_WRITE_CASE_MATCH_TYPES", "DIRECT")
        return {t.strip().upper() for t in raw.split(",") if t.strip()}


cfg = Config()
