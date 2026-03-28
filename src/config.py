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


class Config:
    """All configurable settings, read from environment variables."""

    # ── LLM Provider ────────────────────────────────────────
    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "groq")
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
    LLM_EVALUATOR_MODEL: str = os.environ.get("LLM_EVALUATOR_MODEL", "qwen/qwen3-32b")
    LLM_EVALUATOR_PROVIDER: str = os.environ.get("LLM_EVALUATOR_PROVIDER", "")

    # ── Ollama (local) ──────────────────────────────────────
    OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_CONTEXT_WINDOW: int = int(os.environ.get("OLLAMA_CONTEXT_WINDOW", "16384"))

    # ── Embedding Model (Qdrant / Treatment Planning) ───────
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "FremyCompany/BioLORD-2023")
    QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "nice_guidelines")

    # ── Agent Tuning ────────────────────────────────────────
    DIAGNOSTIC_MAX_ROUNDS: int = int(os.environ.get("DIAGNOSTIC_MAX_ROUNDS", "3"))
    DIAGNOSTIC_CONFIDENCE_THRESHOLD: int = int(os.environ.get("DIAGNOSTIC_CONFIDENCE_THRESHOLD", "75"))

    # ── Data Paths ──────────────────────────────────────────
    GOLD_DIR: Path = Path(os.environ.get("GOLD_DIR", "data/gold/patient_cases"))
    MAS_RESULTS_DIR: Path = Path(os.environ.get("MAS_RESULTS_DIR", "data/gold/mas_results"))
    GUIDELINES_DIR: Path = Path(os.environ.get("GUIDELINES_DIR", "config/guidelines"))
    DUCKDB_PATH: Path = Path(os.environ.get("DUCKDB_PATH", "data/clinical.duckdb"))


cfg = Config()
