"""Tier 3 — Semantic Memory.

Cross-session distilled insights. Persists to disk between runs (a JSON file
keyed by disease) so the pipeline accumulates statistics over time:
  - how often each disease ends up DIRECT / INDIRECT / MISS
  - how often it lands at rank-1 when found
  - common evidence patterns observed in DIRECT-matching runs

Diagnostic Reasoning consults this for Bayesian priors ("in past runs, when
this evidence pattern appeared, the disease was X N% of the time").

NO PHI is stored — only disease names, evidence pattern strings extracted by
the Diagnostic agent, and aggregate statistics. Each consolidation is
idempotent: running the same patient twice updates statistics correctly.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from src.memory.types import SemanticInsight


_LOCK = threading.Lock()


class SemanticMemory:
    """Disk-backed cross-session insight store.

    File format: { disease_name: SemanticInsight.model_dump() }

    Reads are cheap (JSON load + dict lookup). Writes go through `consolidate()`
    which holds a process-wide lock to avoid corrupting the file during
    parallel cohort runs (e.g. when running run_cohort with concurrent threads).
    """

    def __init__(self, store_path: Path):
        self.store_path = Path(store_path)
        self._cache: dict[str, SemanticInsight] | None = None

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self) -> dict[str, SemanticInsight]:
        if self._cache is not None:
            return self._cache
        if not self.store_path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = json.loads(self.store_path.read_text())
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable — start fresh rather than crash.
            self._cache = {}
            return self._cache
        self._cache = {
            disease: SemanticInsight.model_validate(payload)
            for disease, payload in raw.items()
        }
        return self._cache

    def _save(self) -> None:
        if self._cache is None:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        out = {d: insight.model_dump() for d, insight in self._cache.items()}
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(out, indent=2, sort_keys=True))
        tmp.replace(self.store_path)

    # ── Reads ───────────────────────────────────────────────────────────

    def recall(self, disease: str) -> SemanticInsight | None:
        """Look up an insight by disease name (exact match, case-insensitive)."""
        store = self._load()
        key = self._normalize(disease)
        for stored_disease, insight in store.items():
            if self._normalize(stored_disease) == key:
                return insight
        return None

    def recall_for_diseases(self, diseases: list[str]) -> dict[str, SemanticInsight]:
        """Look up insights for a list of differential disease names.

        Returns a dict keyed by the queried disease name (only found ones).
        """
        results: dict[str, SemanticInsight] = {}
        for d in diseases:
            insight = self.recall(d)
            if insight is not None:
                results[d] = insight
        return results

    def all(self) -> dict[str, SemanticInsight]:
        return dict(self._load())

    # ── Writes ──────────────────────────────────────────────────────────

    def consolidate(
        self,
        disease: str,
        match_type: str,  # "DIRECT" | "INDIRECT" | "MISS"
        rank_when_found: int | None = None,
        primary_confidence: float | None = None,
        evidence_patterns: list[str] | None = None,
        max_evidence_patterns: int = 12,
    ) -> SemanticInsight:
        """Merge one run's outcome into the disease's insight record.

        Re-running the same patient is idempotent in spirit (it adds another
        observation, which is correct: each run is one episode).
        """
        from src.config import cfg
        if cfg.USE_MONGO:
            from src.db.mongo import semantic_inc_sync
            try:
                semantic_inc_sync(
                    disease,
                    match_type=match_type,
                    at_rank_1=(rank_when_found == 1),
                )
            except Exception:  # noqa: BLE001
                pass
            return self._load().get(disease) or SemanticInsight(disease=disease, runs_observed=0)

        with _LOCK:
            store = self._load()
            existing = store.get(disease)
            if existing is None:
                insight = SemanticInsight(disease=disease, runs_observed=0)
            else:
                insight = existing

            insight.runs_observed += 1
            if match_type == "DIRECT":
                insight.direct_matches += 1
                if rank_when_found == 1:
                    insight.rank1_when_found += 1
            elif match_type == "INDIRECT":
                insight.indirect_matches += 1
            else:  # MISS
                insight.misses += 1

            if primary_confidence is not None:
                # Running mean (avoids floating-point drift better than sum/N).
                n = insight.runs_observed
                insight.avg_primary_confidence = (
                    insight.avg_primary_confidence * (n - 1) + float(primary_confidence)
                ) / n

            if evidence_patterns:
                seen = set(insight.common_evidence_patterns)
                for p in evidence_patterns:
                    if p not in seen:
                        insight.common_evidence_patterns.append(p)
                        seen.add(p)
                # Cap to avoid unbounded growth (older patterns drop off).
                if len(insight.common_evidence_patterns) > max_evidence_patterns:
                    insight.common_evidence_patterns = (
                        insight.common_evidence_patterns[-max_evidence_patterns:]
                    )

            from src.memory.types import _now_iso
            insight.last_updated = _now_iso()
            store[disease] = insight
            self._save()
            return insight

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(s: str) -> str:
        return " ".join(s.lower().strip().split())

    def summarize_for_diseases(self, diseases: list[str]) -> str:
        """Compact summary of insights matching the given diseases, for prompts."""
        recalled = self.recall_for_diseases(diseases)
        if not recalled:
            return "(no prior cross-session insights for these diagnoses)"
        lines = ["Prior cross-session insights:"]
        for disease, insight in recalled.items():
            lines.append(
                f"  - {disease}: {insight.runs_observed} prior runs, "
                f"DIRECT {insight.direct_rate:.0%}, "
                f"found-rate {insight.found_rate:.0%}, "
                f"rank-1-when-found {insight.rank1_when_found}/{insight.direct_matches}"
            )
        return "\n".join(lines)
