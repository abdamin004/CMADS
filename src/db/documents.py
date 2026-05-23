"""Beanie Document classes for the MongoDB storage layer.

Schema mirrors docs/superpowers/specs/2026-05-22-mongodb-migration-design.md §5.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class PatientCase(Document):
    id: str = Field(alias="_id")          # patient_uuid
    person_id: int
    cutoff_date: datetime
    case_type: str
    demographics: dict[str, Any]
    conditions: dict[str, Any]
    medications: dict[str, Any]
    visits: dict[str, Any] | list[dict[str, Any]]
    comorbidity: dict[str, Any]
    risk_scores: dict[str, Any]
    labs: dict[str, Any]
    ground_truth: dict[str, Any]
    case_stats: dict[str, Any]
    assembled_at: datetime
    pipeline_version: str

    class Settings:
        name = "patient_cases"
        indexes = ["ground_truth.target_condition.name"]


class AgentRun(Document):
    """Per-(result_set, patient_uuid) aggregate document. One row =
    one full patient run with every agent's output embedded under
    `agents.<agent_id>`. Schema §5.2 of the design spec.

    Note: the spec's compound `_id = {result_set, patient_uuid}` is
    implemented here as a UNIQUE compound index on two separate fields,
    because Beanie ergonomics prefer a single-value `_id` (auto-assigned
    ObjectId) over a compound document. The uniqueness guarantee is the
    same; the field-level access just reads more naturally as
    `doc.result_set` than `doc.id.result_set`."""
    result_set: str
    patient_uuid: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_s: float | None = None
    pipeline_version: str = ""
    model_config_dict: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    execution_trace: list[dict[str, Any]] = Field(default_factory=list)
    session_memory: list[dict[str, Any]] = Field(default_factory=list)
    canonicalizer_fired: bool = False

    class Settings:
        name = "agent_runs"
        indexes = [
            IndexModel([("result_set", 1), ("patient_uuid", 1)], unique=True),
            [("result_set", 1), ("agents.evaluation.output.match_type", 1)],
            [("patient_uuid", 1)],
            [("agents.final_diagnosis.output.primary_diagnosis", 1)],
        ]


class SemanticMemoryEntry(Document):
    """One document per disease. Per-disease counts updated by the
    Stage-7 memory consolidator. Schema §5.3."""
    id: str = Field(alias="_id")          # disease name (verbatim Synthea label)
    counts: dict[str, int] = Field(default_factory=dict)
    rank1_when_found: int = 0
    evidence_patterns: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime

    class Settings:
        name = "semantic_memory"


class DerivedArtefact(Document):
    """Catch-all for derived JSON (paired_160_mcnemar, sensitivity
    summaries, cohort_summary:<result_set>, ...). Schema §5.4."""
    id: str = Field(alias="_id")
    payload: dict[str, Any] | list[Any]
    produced_by: str
    produced_at: datetime
    source_cohort: str | None = None

    class Settings:
        name = "derived_artefacts"


class TestPatient(Document):
    """Custom patient built (or cloned) by the clinician in the Tester
    journey. Schema mirrors PatientCase plus authorship + lifecycle
    metadata. Lives in its own collection so research aggregations
    never see it.

    See docs/superpowers/specs/2026-05-23-tester-patient-builder-design.md
    """
    id: str = Field(alias="_id")          # test_uuid (uuid4 hex, "ttest-" prefix)
    label: str
    source_uuid: str | None = None        # cohort uuid if cloned; None for scratch
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    run_count: int = 0

    # PatientCase mirror — same field names + shapes so load_patient_case
    # can consume a TestPatient with one extra branch and no schema xlate.
    person_id: int = 0
    cutoff_date: datetime
    case_type: str = "ehr+lab"
    demographics: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    medications: dict[str, Any] = Field(default_factory=dict)
    visits: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    comorbidity: dict[str, Any] = Field(default_factory=dict)
    risk_scores: dict[str, Any] = Field(default_factory=dict)
    labs: dict[str, Any] = Field(default_factory=dict)
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    case_stats: dict[str, Any] = Field(default_factory=dict)
    assembled_at: datetime
    pipeline_version: str = "tester-1.0"

    class Settings:
        name = "test_patients"
        indexes = ["created_at", "last_run_at"]
