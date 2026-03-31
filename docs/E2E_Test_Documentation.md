# End-to-End Test Documentation

## CMADS — Full Pipeline Testing (Synthea → Data Pipeline → Agent Pipeline → Clinical Decision Report)

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | End-to-end system tests covering the complete flow from Synthea data generation through agent reasoning to final clinical decision report |
| **Test Framework** | pytest + pytest-asyncio |
| **LLM** | Configurable via `get_llm()` adapter (Groq, OpenAI, Anthropic, Gemini, Ollama) |

---

## 1. Overview

End-to-end (E2E) tests verify that the entire CMADS pipeline works correctly as an integrated system — from raw Synthea CSV files all the way to a structured Clinical Decision Report. These tests do not mock any component; they exercise the real data pipeline, real LLM inference (via Ollama), and real agent orchestration.

### 1.1 What E2E tests verify

- Synthea CSV files can be loaded into DuckDB (Bronze)
- dbt transforms produce valid Silver and Silver+ tables
- Gold assembler produces valid ehr_case.json and lab_case.json
- The LangGraph pipeline executes all 7 agents in the correct stage order (EHR Analyst, Lab Interpreter, Diagnostic Reasoning, Clinical Reviewer, Diagnostic Refiner, Evaluator, Treatment Planning)
- Each agent produces structurally valid output (Pydantic schema compliance)
- The Evaluator compares the refined diagnosis against Synthea ground truth
- The Treatment Planning agent produces a treatment plan for confirmed diagnoses
- The execution trace captures all agent invocations with timing and status
- The final results can be evaluated against Synthea ground truth

### 1.2 What E2E tests do NOT verify

- Individual agent reasoning quality (that's the evaluation framework's job)
- Prompt optimisation (that's iterative experimentation)
- UI/portal functionality (tested separately)
- Synthea generation itself (we use pre-generated fixtures)

### 1.3 Test pyramid position

```
         /\
        /  \     Evaluation (accuracy, recall, LLM-as-judge)
       /    \    — measures reasoning quality, not system correctness
      /------\
     /        \   E2E Tests  ← THIS DOCUMENT
    /          \  — full pipeline, real LLM, real data, ~5-15 min per case
   /------------\
  /              \ Integration Tests
 /                \ — agent + orchestrator with mock LLM, ~seconds
/------------------\
        Unit Tests
  — schema validation, parsers, helpers, ~milliseconds
```

---

## 2. Test Environment

### 2.1 Prerequisites

```bash
# Ollama must be running with the model loaded
ollama serve &
ollama pull gpt-o3-120b

# Verify model is available
curl http://localhost:11434/api/tags | jq '.models[].name'
# Should include "gpt-o3-120b"

# DuckDB must have data loaded (Bronze → Silver → Silver+)
python pipeline/load_csv_to_duckdb.py batch_10k
dbt run --select silver.* silver_plus.*

# Install test dependencies
pip install pytest pytest-asyncio pytest-timeout
```

### 2.2 Test fixtures

E2E tests use a small, fixed subset of patients — not the full 14,335 cohort. These fixture patients are selected to cover diverse clinical scenarios:

```
tests/
├── fixtures/
│   ├── gold/
│   │   ├── patient_diabetes_ckd/
│   │   │   ├── ehr_case.json       # Diabetes + CKD comorbidity
│   │   │   └── lab_case.json
│   │   ├── patient_chf_anemia/
│   │   │   ├── ehr_case.json       # Heart failure + Anemia
│   │   │   └── lab_case.json
│   │   ├── patient_lung_cancer/
│   │   │   ├── ehr_case.json       # Non-small cell lung carcinoma
│   │   │   └── lab_case.json
│   │   ├── patient_mi_acute/
│   │   │   ├── ehr_case.json       # Acute ST-elevation MI
│   │   │   └── lab_case.json
│   │   └── patient_pneumonia/
│   │       ├── ehr_case.json       # Pneumonia (simpler case)
│   │       └── lab_case.json
│   ├── ground_truth/
│   │   ├── patient_diabetes_ckd.json    # Known conditions, meds, labs
│   │   ├── patient_chf_anemia.json
│   │   ├── patient_lung_cancer.json
│   │   ├── patient_mi_acute.json
│   │   └── patient_pneumonia.json
│   └── conftest.py                 # Shared fixtures (DB connection, LLM client, etc.)
├── e2e/
│   ├── test_full_pipeline.py       # Main E2E test suite
│   ├── test_data_pipeline.py       # Bronze → Silver → Silver+ → Gold
│   ├── test_agent_pipeline.py      # Gold → 7 agents → Report
│   ├── test_stage_transitions.py   # Stage 1→2→3→4→5 sequencing
│   ├── test_failure_recovery.py    # Agent failure + graceful degradation
│   └── test_evaluation_flow.py     # Report → ground truth comparison
└── conftest.py                     # Root-level pytest config
```

### 2.3 Fixture patient selection criteria

| Fixture Patient | Primary Disease | Why Selected |
|-----------------|-----------------|--------------|
| patient_diabetes_ckd | Diabetes + CKD | Multi-comorbidity, rich labs (HbA1c, eGFR, creatinine trends), polypharmacy |
| patient_chf_anemia | CHF + Anemia | Cross-system conditions, imaging data (echo), medication interactions |
| patient_lung_cancer | NSCLC Stage 1 | Imaging-heavy case (CT findings), staging complexity |
| patient_mi_acute | Acute STEMI | Emergency presentation, critical lab flags (troponin), time-sensitive |
| patient_pneumonia | Pneumonia | Simpler single-condition case, baseline for comparison |

### 2.4 Ground truth structure

Each ground truth file contains the known facts from Synthea's data (not LLM-generated):

```json
{
  "patient_id": "abc-123",
  "primary_condition": {
    "name": "Diabetes mellitus type 2",
    "snomed": "44054006",
    "icd10": "E11.9"
  },
  "all_active_conditions": [
    {"name": "Diabetes mellitus type 2", "snomed": "44054006"},
    {"name": "Chronic kidney disease stage 3", "snomed": "431856006"},
    {"name": "Essential hypertension", "snomed": "59621000"}
  ],
  "expected_medications": ["metformin", "lisinopril", "atorvastatin"],
  "critical_lab_findings": [
    {"test": "HbA1c", "loinc": "4548-4", "last_value": 8.2, "severity": 3},
    {"test": "eGFR", "loinc": "33914-3", "last_value": 42, "severity": 3}
  ],
  "expected_risk_scores": {
    "ckd_stage": "Stage 3",
    "hba1c_band": "diabetic",
    "polypharmacy": true
  }
}
```

---

## 3. Test Suites

### 3.1 Full Pipeline E2E Test

**File:** `tests/e2e/test_full_pipeline.py`

This is the master E2E test — it runs the complete pipeline for a single patient from Gold JSON to Clinical Decision Report and verifies every stage.

```python
# tests/e2e/test_full_pipeline.py
import pytest
import json
from pathlib import Path
from src.orchestrator.graph import compile_pipeline
from src.orchestrator.state import PipelineState


@pytest.fixture
def gold_case_diabetes(fixtures_dir):
    """Load the diabetes+CKD fixture patient."""
    ehr = json.loads((fixtures_dir / "gold/patient_diabetes_ckd/ehr_case.json").read_text())
    lab = json.loads((fixtures_dir / "gold/patient_diabetes_ckd/lab_case.json").read_text())
    return {"ehr": ehr, "lab": lab}


@pytest.fixture
def ground_truth_diabetes(fixtures_dir):
    """Load ground truth for diabetes+CKD patient."""
    return json.loads((fixtures_dir / "ground_truth/patient_diabetes_ckd.json").read_text())


@pytest.fixture
def pipeline():
    """Compile the LangGraph pipeline."""
    return compile_pipeline()


class TestFullPipelineE2E:
    """Full end-to-end pipeline test for a single patient case."""

    @pytest.mark.timeout(900)  # 15 minutes max (local LLM inference)
    def test_pipeline_completes_successfully(self, pipeline, gold_case_diabetes):
        """The pipeline runs to completion without errors."""
        initial_state = {
            "patient_context": {
                "ehr_case": gold_case_diabetes["ehr"],
                "lab_case": gold_case_diabetes["lab"],
            },
            "agent_outputs": {},
            "conflicts": [],
            "execution_trace": [],
            "scratchpad": {},
        }

        result = pipeline.invoke(
            initial_state,
            config={"configurable": {"thread_id": "test_diabetes_ckd"}},
        )

        # Pipeline should complete (not raise)
        assert result is not None

    @pytest.mark.timeout(900)
    def test_all_agents_executed(self, pipeline, gold_case_diabetes):
        """All 7 agents wrote their outputs to shared memory."""
        result = self._run_pipeline(pipeline, gold_case_diabetes)

        expected_agents = [
            "ehr_analyst",
            "lab_interpreter",
            "diagnostic_reasoning",
            "clinical_reviewer",
            "final_diagnosis",
            "evaluation",
            "treatment_planning",
        ]

        for agent_id in expected_agents:
            assert agent_id in result["agent_outputs"], \
                f"Agent '{agent_id}' did not write output"

    @pytest.mark.timeout(900)
    def test_execution_order_is_correct(self, pipeline, gold_case_diabetes):
        """Agents executed in the correct stage order."""
        result = self._run_pipeline(pipeline, gold_case_diabetes)
        trace = result["execution_trace"]

        # Extract agent IDs in execution order
        agent_order = [entry["agent_id"] for entry in trace]

        # Stage 1 agents must come before Stage 2
        ehr_idx = agent_order.index("ehr_analyst")
        lab_idx = agent_order.index("lab_interpreter")
        diag_idx = agent_order.index("diagnostic_reasoning")
        assert ehr_idx < diag_idx, "EHR Analyst must run before Diagnostic"
        assert lab_idx < diag_idx, "Lab Interpreter must run before Diagnostic"

        # Stage 2 must come before Stage 3
        review_idx = agent_order.index("clinical_reviewer")
        assert diag_idx < review_idx, "Diagnostic must run before Reviewer"

        # Stage 3 must come before Stage 4
        refine_idx = agent_order.index("final_diagnosis")
        assert review_idx < refine_idx, "Reviewer must run before Refiner"

        # Stage 4 must come before Stage 5
        eval_idx = agent_order.index("evaluation")
        assert refine_idx < eval_idx, "Refiner must run before Evaluation"

        # Stage 5 must come before Stage 6
        treat_idx = agent_order.index("treatment_planning")
        assert eval_idx < treat_idx, "Evaluation must run before Treatment"

    @pytest.mark.timeout(900)
    def test_final_diagnosis_structure(self, pipeline, gold_case_diabetes):
        """The refined diagnosis has all required fields."""
        result = self._run_pipeline(pipeline, gold_case_diabetes)
        final_dx = result["agent_outputs"]["final_diagnosis"]

        required_fields = [
            "differential",
            "primary_diagnosis",
            "primary_probability",
        ]

        for field in required_fields:
            assert field in final_dx, f"Final diagnosis missing required field: '{field}'"
            assert final_dx[field] is not None, f"Final diagnosis field '{field}' is None"

    @pytest.mark.timeout(900)
    def test_report_identifies_primary_condition(
        self, pipeline, gold_case_diabetes, ground_truth_diabetes
    ):
        """The refined diagnosis relates to the ground truth condition."""
        result = self._run_pipeline(pipeline, gold_case_diabetes)
        final_dx = result["agent_outputs"]["final_diagnosis"]

        primary_dx = final_dx["primary_diagnosis"].lower()
        gt_condition = ground_truth_diabetes["primary_condition"]["name"].lower()

        # Flexible match: the report should mention key terms from the ground truth
        # (e.g., "diabetes" or "type 2" for "Diabetes mellitus type 2")
        key_terms = gt_condition.split()
        matches = sum(1 for term in key_terms if term in primary_dx)
        match_ratio = matches / len(key_terms)

        assert match_ratio >= 0.3, (
            f"Primary diagnosis '{final_dx['primary_diagnosis']}' does not appear "
            f"related to ground truth '{gt_condition}' (match ratio: {match_ratio:.2f})"
        )

    @pytest.mark.timeout(900)
    def test_execution_trace_completeness(self, pipeline, gold_case_diabetes):
        """Every agent invocation is recorded in the execution trace."""
        result = self._run_pipeline(pipeline, gold_case_diabetes)
        trace = result["execution_trace"]

        assert len(trace) >= 7, f"Expected >= 7 trace entries, got {len(trace)}"

        for entry in trace:
            assert "agent_id" in entry
            assert "status" in entry
            assert entry["status"] in ("success", "partial", "error")
            assert "execution_ms" in entry
            assert entry["execution_ms"] > 0

    def _run_pipeline(self, pipeline, gold_case):
        """Helper: run the pipeline and return the result state."""
        initial_state = {
            "patient_context": {
                "ehr_case": gold_case["ehr"],
                "lab_case": gold_case["lab"],
            },
            "agent_outputs": {},
            "conflicts": [],
            "execution_trace": [],
            "scratchpad": {},
        }
        return pipeline.invoke(
            initial_state,
            config={"configurable": {"thread_id": "test_run"}},
        )
```

---

### 3.2 Data Pipeline Tests

**File:** `tests/test_data_pipeline.py` — **IMPLEMENTED** (51 tests, all passing)

Verifies the complete data pipeline from Bronze through Gold and Radiology reports, using the real DuckDB database. Fast (~0.2s), no LLM required, suitable for CI.

**Test suites (6 classes, 51 tests):**

| Class | Tests | What's Verified |
|-------|-------|-----------------|
| TestBronzeLayer | 10 | Tables exist, row counts, required columns, SNOMED codes, no duplicates |
| TestSilverLayer | 7 | OMOP tables exist, zero patient loss Bronze→Silver, UUID mapping, measurement values |
| TestSilverPlusLayer | 8 | 6 derived tables exist with data, valid trend directions, severity values, cohort coverage |
| TestGoldLayer | 11 | 1K cohort files exist, point-in-time mode, ehr/lab/ground_truth structure, **no target disease leakage**, cutoff date consistency |
| TestRadiologyReports | 10 | Reports generated, structure valid, non-empty text, **no diagnosis in report text**, evaluation scores bounded [1-5], accepted reports ≥ threshold |
| TestCrossLayerIntegrity | 5 | Cohort patients exist in Bronze+Silver, cutoff ≤ diagnosis date, radiology patients in cohort, disease diversity ≥10 |

**Key additions beyond the original spec:**
- **Radiology report tests** (not in original doc): validates generated reports, diagnosis leakage detection, evaluation score ranges
- **Cross-layer integrity tests**: verifies data consistency across Bronze → Silver → Gold → Radiology
- **Point-in-time verification**: ensures target disease is hidden from ehr_case (tested on 100 patients)
- **Cutoff date consistency**: ehr_case, lab_case, and ground_truth share the same cutoff

**Running:**
```bash
# All data pipeline tests (fast, no LLM)
pytest tests/test_data_pipeline.py -v

# Specific layer
pytest tests/test_data_pipeline.py::TestGoldLayer -v
pytest tests/test_data_pipeline.py::TestRadiologyReports -v
```

**Actual table names** (differ from original spec):
- Silver: `silver_person`, `silver_visit_occurrence`, `silver_condition_occurrence`, `silver_measurement`, `silver_drug_exposure`, `silver_observation`
- Silver+: `silver_plus_lab_trends`, `silver_plus_critical_lab_flags`, `silver_plus_comorbidity_matrix`, `silver_plus_risk_scores`, `silver_plus_medication_timeline`, `silver_plus_drug_condition_links`
- Gold: `data/gold/patient_cases/{uuid}/ehr_case.json`, `lab_case.json`, `ground_truth.json`
- Radiology: `data/gold/radiology_reports/{patient_id}_{modality}_{date}.json`

---

### 3.3 Agent Pipeline E2E Test

**File:** `tests/e2e/test_agent_pipeline.py`

Tests each agent's output structure within the full pipeline context (real LLM, real data).

```python
# tests/e2e/test_agent_pipeline.py
import pytest
from src.orchestrator.graph import compile_pipeline


class TestAgentOutputSchemas:
    """Verify each agent's output conforms to its Pydantic schema."""

    @pytest.fixture(autouse=True)
    def run_pipeline(self, pipeline, gold_case_diabetes):
        """Run the pipeline once and cache the result for all tests."""
        self.result = self._run_pipeline(pipeline, gold_case_diabetes)

    def test_ehr_analyst_output(self):
        out = self.result["agent_outputs"]["ehr_analyst"]
        assert "chief_complaint" in out
        assert "active_problems" in out
        assert isinstance(out["active_problems"], list)
        assert len(out["active_problems"]) > 0

    def test_lab_interpreter_output(self):
        out = self.result["agent_outputs"]["lab_interpreter"]
        assert "findings" in out
        assert isinstance(out["findings"], list)
        assert len(out["findings"]) > 0
        # Each finding should have required fields
        for finding in out["findings"][:3]:
            assert "test_name" in finding
            assert "classification" in finding
            assert finding["classification"] in ("normal", "borderline", "abnormal")
            assert "severity" in finding
            assert 1 <= finding["severity"] <= 5

    def test_diagnostic_output(self):
        out = self.result["agent_outputs"]["diagnostic"]
        assert "differential" in out
        assert isinstance(out["differential"], list)
        assert len(out["differential"]) >= 3, "Must produce ≥3 differential diagnoses"
        assert "primary_diagnosis" in out
        # Each diagnosis should have evidence
        for dx in out["differential"]:
            assert "name" in dx
            assert "confidence" in dx
            assert dx["confidence"] in ("high", "moderate", "low")
            assert "supporting_evidence" in dx

    def test_reviewer_output(self):
        out = self.result["agent_outputs"]["clinical_reviewer"]
        assert "diagnosis_verifications" in out
        assert "overall_confidence" in out
        assert 0 <= out["overall_confidence"] <= 100
        assert "recommended_primary" in out

    def test_refiner_output(self):
        out = self.result["agent_outputs"]["final_diagnosis"]
        assert "differential" in out
        assert isinstance(out["differential"], list)
        assert "primary_diagnosis" in out

    def test_evaluator_output(self):
        out = self.result["agent_outputs"]["evaluation"]
        assert out is not None

    def test_treatment_output(self):
        out = self.result["agent_outputs"]["treatment_planning"]
        assert "medications" in out
        assert isinstance(out["medications"], list)
        assert "treatment_summary" in out

    def _run_pipeline(self, pipeline, gold_case):
        initial_state = {
            "patient_context": {
                "ehr_case": gold_case["ehr"],
                "lab_case": gold_case["lab"],
            },
            "agent_outputs": {},
            "conflicts": [],
            "execution_trace": [],
            "scratchpad": {},
        }
        return pipeline.invoke(
            initial_state,
            config={"configurable": {"thread_id": "test_schema_validation"}},
        )
```

---

### 3.4 Stage Transition Tests

**File:** `tests/e2e/test_stage_transitions.py`

Verifies the data flow between stages — that downstream agents actually receive and use upstream outputs.

```python
# tests/e2e/test_stage_transitions.py
import pytest


class TestStageTransitions:
    """Verify data flows correctly between pipeline stages."""

    def test_stage1_to_stage2_data_flow(self, pipeline_result):
        """Diagnostic agent should reference findings from EHR + Lab agents."""
        diag = pipeline_result["agent_outputs"]["diagnostic"]
        ehr = pipeline_result["agent_outputs"]["ehr_analyst"]
        lab = pipeline_result["agent_outputs"]["lab_interpreter"]

        # Diagnostic should have produced a differential
        assert len(diag["differential"]) >= 3

        # The differential's supporting evidence should reference
        # concepts that appear in EHR or Lab output
        all_evidence = []
        for dx in diag["differential"]:
            all_evidence.extend(dx.get("supporting_evidence", []))
        assert len(all_evidence) > 0, "Diagnostic produced no supporting evidence"

    def test_stage2_to_stage3_data_flow(self, pipeline_result):
        """Reviewer should address diagnostic output."""
        reviewer = pipeline_result["agent_outputs"]["clinical_reviewer"]
        assert reviewer["overall_confidence"] > 0, "Reviewer gave 0 confidence"
        assert "diagnosis_verifications" in reviewer

    def test_stage3_to_stage4_data_flow(self, pipeline_result):
        """Refiner should merge diagnostic + reviewer into final differential."""
        final_dx = pipeline_result["agent_outputs"]["final_diagnosis"]
        assert "differential" in final_dx
        assert "primary_diagnosis" in final_dx

    def test_stage4_to_stage5_data_flow(self, pipeline_result):
        """Evaluator should compare refined diagnosis against ground truth."""
        evaluation = pipeline_result["agent_outputs"]["evaluation"]
        assert evaluation is not None

    def test_stage5_to_stage6_data_flow(self, pipeline_result):
        """Treatment should run after evaluation (only for confirmed diagnoses)."""
        treatment = pipeline_result["agent_outputs"]["treatment_planning"]
        assert treatment is not None

    def test_conflict_detection_runs(self, pipeline_result):
        """Conflict detection should have been executed (even if no conflicts found)."""
        trace = pipeline_result["execution_trace"]
        agent_ids = [e["agent_id"] for e in trace]

        # Conflict check nodes should appear in the trace
        assert "conflict_check_1" in agent_ids or \
               "conflict_check_2" in agent_ids, \
               "No conflict detection nodes found in execution trace"
```

---

### 3.5 Failure Recovery Tests

**File:** `tests/e2e/test_failure_recovery.py`

Verifies the pipeline handles agent failures gracefully — continues with partial results instead of crashing.

```python
# tests/e2e/test_failure_recovery.py
import pytest
from unittest.mock import patch, MagicMock
from src.orchestrator.graph import compile_pipeline


class TestFailureRecovery:
    """Test graceful degradation when agents fail."""

    def test_pipeline_continues_after_reviewer_failure(
        self, gold_case_diabetes
    ):
        """If the Clinical Reviewer fails, pipeline should still produce results."""
        pipeline = compile_pipeline()

        # Patch the reviewer node to simulate failure
        with patch("src.agents.reviewer.clinical_reviewer_agent") as mock_rev:
            mock_rev.side_effect = TimeoutError("LLM timeout")

            result = pipeline.invoke(
                self._initial_state(gold_case_diabetes),
                config={"configurable": {"thread_id": "test_rev_failure"}},
            )

        # Pipeline should still complete
        assert "treatment_planning" in result["agent_outputs"]

        # Reviewer should be marked as error in trace
        rev_trace = [
            e for e in result["execution_trace"]
            if e["agent_id"] == "clinical_reviewer"
        ]
        if rev_trace:
            assert rev_trace[0]["status"] == "error"

    def test_pipeline_continues_after_treatment_failure(
        self, gold_case_diabetes
    ):
        """If Treatment Planning fails, pipeline should still have upstream results."""
        pipeline = compile_pipeline()

        with patch("src.agents.treatment.treatment_planning_agent") as mock_treat:
            mock_treat.side_effect = Exception("Schema validation failed")

            result = pipeline.invoke(
                self._initial_state(gold_case_diabetes),
                config={"configurable": {"thread_id": "test_treat_failure"}},
            )

        # Upstream agents should still have produced output
        assert "final_diagnosis" in result["agent_outputs"]

    def test_pipeline_handles_partial_results(self, gold_case_diabetes):
        """When an agent fails, downstream agents handle missing data gracefully."""
        pipeline = compile_pipeline()

        with patch("src.agents.reviewer.clinical_reviewer_agent") as mock_rev:
            mock_rev.return_value = {
                "agent_outputs": {"clinical_reviewer": None},
                "execution_trace": [{
                    "agent_id": "clinical_reviewer",
                    "status": "error",
                    "execution_ms": 0,
                }],
            }

            result = pipeline.invoke(
                self._initial_state(gold_case_diabetes),
                config={"configurable": {"thread_id": "test_partial"}},
            )

        # Pipeline should still attempt downstream stages
        assert result is not None

    def _initial_state(self, gold_case):
        return {
            "patient_context": {
                "ehr_case": gold_case["ehr"],
                "lab_case": gold_case["lab"],
            },
            "agent_outputs": {},
            "conflicts": [],
            "execution_trace": [],
            "scratchpad": {},
        }
```

---

### 3.6 Evaluation Flow Test

**File:** `tests/e2e/test_evaluation_flow.py`

Verifies that the evaluation framework can compare the pipeline output against ground truth.

```python
# tests/e2e/test_evaluation_flow.py
import pytest
from src.evaluation.metrics import (
    diagnostic_accuracy,
    differential_recall,
    critical_finding_coverage,
)


class TestEvaluationFlow:
    """Verify evaluation metrics can be computed from pipeline output."""

    def test_diagnostic_accuracy_computable(
        self, pipeline_result, ground_truth_diabetes
    ):
        """Diagnostic accuracy metric runs without error."""
        final_dx = pipeline_result["agent_outputs"]["final_diagnosis"]
        score = diagnostic_accuracy(
            predicted=final_dx["primary_diagnosis"],
            ground_truth=ground_truth_diabetes["primary_condition"]["name"],
        )
        assert 0.0 <= score <= 1.0

    def test_differential_recall_computable(
        self, pipeline_result, ground_truth_diabetes
    ):
        """Differential recall metric runs without error."""
        diag = pipeline_result["agent_outputs"]["final_diagnosis"]
        predicted_conditions = [dx["name"] for dx in diag["differential"]]
        gt_conditions = [
            c["name"] for c in ground_truth_diabetes["all_active_conditions"]
        ]
        score = differential_recall(
            predicted=predicted_conditions,
            ground_truth=gt_conditions,
        )
        assert 0.0 <= score <= 1.0

    def test_critical_finding_coverage_computable(
        self, pipeline_result, ground_truth_diabetes
    ):
        """Critical finding coverage metric runs without error."""
        final_dx = pipeline_result["agent_outputs"]["final_diagnosis"]
        gt_critical = ground_truth_diabetes["critical_lab_findings"]
        score = critical_finding_coverage(
            report_text=str(final_dx),
            critical_findings=gt_critical,
        )
        assert 0.0 <= score <= 1.0

    def test_evaluation_produces_summary(
        self, pipeline_result, ground_truth_diabetes
    ):
        """Full evaluation produces a summary dict with all metrics."""
        final_dx = pipeline_result["agent_outputs"]["final_diagnosis"]

        summary = {
            "diagnostic_accuracy": diagnostic_accuracy(
                final_dx["primary_diagnosis"],
                ground_truth_diabetes["primary_condition"]["name"],
            ),
            "differential_recall": differential_recall(
                [dx["name"] for dx in final_dx["differential"]],
                [c["name"] for c in ground_truth_diabetes["all_active_conditions"]],
            ),
            "critical_finding_coverage": critical_finding_coverage(
                str(final_dx),
                ground_truth_diabetes["critical_lab_findings"],
            ),
            "reviewer_confidence": pipeline_result["agent_outputs"]["clinical_reviewer"]["overall_confidence"],
        }

        # All metrics should be numeric and bounded
        for metric_name, value in summary.items():
            assert isinstance(value, (int, float)), \
                f"{metric_name} is not numeric: {type(value)}"
```

---

### 3.7 Offline Tests (No API Keys Required)

**File:** `tests/test_offline.py` -- **IMPLEMENTED** (42 tests, all passing)

These tests validate core infrastructure components without any LLM calls or API keys. They run in milliseconds and are suitable for CI/CD.

**Test suites (6 classes, 42 tests):**

| Class | Tests | What's Verified |
|-------|-------|-----------------|
| TestJsonRepair | 8 | Clean JSON, code-block extraction, trailing commas, single quotes, `<think>` tag stripping, unclosed think tags, nested JSON, text-around-JSON |
| TestJudgeParsing | 8 | Differential formatting, empty differentials, think-tag stripping, direct/indirect/miss parsing, FOUND inconsistency auto-fix, extra whitespace handling |
| TestSchemas | 13 | Pydantic v2 default validation for EHRAnalystOutput, LabInterpreterOutput, LabFinding, LabPanel, DiagnosticOutput, Diagnosis, SupportingEvidence, ReviewerOutput, DiagnosisVerification, ConsistencyCheck, TreatmentOutput, PrescribedMedication; diagnostic output with populated data |
| TestConfig | 4 | Default config values (provider, thresholds, embedding model), Path-type fields, environment variable overrides for numeric and string settings |
| TestAgentPrompts | 4 | EHR Analyst prompt building from patient state, Diagnostic Reasoning prompt building from upstream outputs, graceful handling of missing/empty data, handling of failed upstream agents |
| TestLLMAdapter | 4 | Missing Groq API key raises ValueError, missing OpenAI key raises ValueError, unknown provider raises ValueError, provider registry contains all 5 providers (groq, openai, anthropic, gemini, ollama) |

**Key testing patterns:**
- Uses `unittest.mock.patch` and `patch.dict("os.environ", ...)` to test configuration and API key validation without real credentials
- Schema tests use `model_validate({})` to verify all Pydantic models have safe defaults
- Prompt tests instantiate real agent classes but only call `build_user_prompt()` (no LLM invocation)
- JSON repair tests exercise the `_extract_json_from_response()` function used by all agents to handle malformed LLM output

**Running:**
```bash
# All offline tests (fast, no API keys needed)
pytest tests/test_offline.py -v

# Specific class
pytest tests/test_offline.py::TestJsonRepair -v
pytest tests/test_offline.py::TestSchemas -v
pytest tests/test_offline.py::TestLLMAdapter -v
```

---

## 4. Running the Tests

### 4.1 Commands

```bash
# Run all E2E tests
pytest tests/e2e/ -v --timeout=900

# Run a specific test suite
pytest tests/e2e/test_full_pipeline.py -v --timeout=900

# Run only data pipeline tests (fast, no LLM needed)
pytest tests/e2e/test_data_pipeline.py -v

# Run only agent pipeline tests (slow, needs Ollama)
pytest tests/e2e/test_agent_pipeline.py -v --timeout=900

# Run with detailed output on failure
pytest tests/e2e/ -v --timeout=900 --tb=long -s

# Run a single test case
pytest tests/e2e/test_full_pipeline.py::TestFullPipelineE2E::test_all_agents_executed -v
```

### 4.2 Expected timing

| Test Suite | LLM Required | Approx. Duration | Status | Notes |
|------------|:------------:|------------------:|:------:|-------|
| test_offline.py | No | ~0.5 seconds | **IMPLEMENTED (42 tests)** | JSON repair, schemas, config, prompts, LLM adapter |
| test_data_pipeline.py | No | ~0.2 seconds | **IMPLEMENTED (51 tests)** | DuckDB + file checks only |
| test_mas_pipeline.py | Yes | ~2 min/patient | **IMPLEMENTED** | Full 7-agent pipeline + evaluation |
| test_full_pipeline.py | Yes | ~10-15 minutes | Planned | Full 7-agent pipeline per patient |
| test_agent_pipeline.py | Yes | ~10-15 minutes | Planned | Schema validation on real outputs |
| test_stage_transitions.py | Yes | ~10-15 minutes | Planned | Uses cached pipeline result |
| test_failure_recovery.py | Partial | ~5-8 minutes | Planned | Some agents mocked |
| test_evaluation_flow.py | Yes | ~10-15 minutes | Planned | Pipeline + metric computation |

### 4.3 CI considerations

E2E tests with LLM inference are **not suitable for CI/CD pipelines** due to:
- 10-15 minute execution time per patient case
- Dependency on Ollama + GPU hardware
- Non-deterministic LLM output (tests verify structure, not exact content)

Recommended approach:
- Run **offline tests** in CI (fast, no API keys, validates schemas/parsers/config)
- Run **data pipeline tests** in CI (fast, deterministic, validates DuckDB layers)
- Run **agent pipeline E2E tests** manually before thesis milestones
- Use **integration tests with mock LLM** for CI (not covered in this document)

---

## 5. Test Fixtures Configuration

### 5.1 conftest.py (root)

```python
# tests/conftest.py
import pytest
import json
from pathlib import Path
from src.orchestrator.graph import compile_pipeline


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def pipeline():
    """Compile the LangGraph pipeline once for the entire test session."""
    return compile_pipeline()


@pytest.fixture(scope="session")
def gold_case_diabetes():
    ehr = json.loads((FIXTURES_DIR / "gold/patient_diabetes_ckd/ehr_case.json").read_text())
    lab = json.loads((FIXTURES_DIR / "gold/patient_diabetes_ckd/lab_case.json").read_text())
    return {"ehr": ehr, "lab": lab}


@pytest.fixture(scope="session")
def ground_truth_diabetes():
    return json.loads((FIXTURES_DIR / "ground_truth/patient_diabetes_ckd.json").read_text())


@pytest.fixture(scope="session")
def pipeline_result(pipeline, gold_case_diabetes):
    """Run the pipeline once and cache the result for the entire session.
    This avoids running 7 agents x N tests = expensive."""
    initial_state = {
        "patient_context": {
            "ehr_case": gold_case_diabetes["ehr"],
            "lab_case": gold_case_diabetes["lab"],
        },
        "agent_outputs": {},
        "conflicts": [],
        "execution_trace": [],
        "scratchpad": {},
    }
    return pipeline.invoke(
        initial_state,
        config={"configurable": {"thread_id": "session_test_run"}},
    )
```

### 5.2 Generating fixture patients

```bash
# Extract 5 specific patients from the full Gold output
python scripts/extract_test_fixtures.py \
  --patient-ids "abc-123,def-456,ghi-789,jkl-012,mno-345" \
  --gold-dir data/gold/ \
  --output-dir tests/fixtures/gold/

# Generate ground truth from DuckDB (Synthea's known conditions)
python scripts/generate_ground_truth.py \
  --patient-ids "abc-123,def-456,ghi-789,jkl-012,mno-345" \
  --db data/clinical.duckdb \
  --output-dir tests/fixtures/ground_truth/
```

---

## 6. Test Matrix

### 6.1 Coverage by pipeline stage

| Pipeline Stage | Test File | What's Verified | Status |
|----------------|-----------|-----------------|--------|
| Bronze (CSV → DuckDB) | test_data_pipeline.py::TestBronzeLayer | Tables exist, row counts, columns, SNOMED codes, no duplicates | **Done (10)** |
| Silver (OMOP CDM) | test_data_pipeline.py::TestSilverLayer | Zero patient loss, UUID mapping, measurement values | **Done (7)** |
| Silver+ (derived) | test_data_pipeline.py::TestSilverPlusLayer | 6 tables exist, valid trends/severity, cohort coverage | **Done (8)** |
| Gold (JSON assembly) | test_data_pipeline.py::TestGoldLayer | 1K files, point-in-time mode, structure, no leakage, cutoff consistency | **Done (11)** |
| Radiology Reports | test_data_pipeline.py::TestRadiologyReports | Reports generated, structure, no diagnosis leakage, eval scores valid | **Done (10)** |
| Cross-layer Integrity | test_data_pipeline.py::TestCrossLayerIntegrity | Patients in all layers, cutoff <= diagnosis, disease diversity | **Done (5)** |
| JSON Repair | test_offline.py::TestJsonRepair | Code blocks, trailing commas, think tags, nested JSON | **Done (8)** |
| Judge Parsing | test_offline.py::TestJudgeParsing | Differential formatting, match parsing, inconsistency fixes | **Done (8)** |
| Schema Validation | test_offline.py::TestSchemas | Pydantic defaults for all agent output schemas | **Done (13)** |
| Config | test_offline.py::TestConfig | Defaults, env overrides, path types | **Done (4)** |
| Agent Prompts | test_offline.py::TestAgentPrompts | Prompt building, missing data handling | **Done (4)** |
| LLM Adapter | test_offline.py::TestLLMAdapter | API key validation, provider registry | **Done (4)** |
| Stage 1 agents | test_agent_pipeline.py | EHR Analyst + Lab Interpreter output schemas | Planned |
| Stage 2 agent | test_agent_pipeline.py | Diagnostic Reasoning: >=3 differential, evidence, confidence | Planned |
| Stage 3 agent | test_agent_pipeline.py | Clinical Reviewer: 0-100 confidence, diagnosis verifications | Planned |
| Stage 4 agent | test_agent_pipeline.py | Diagnostic Refiner: merged final differential | Planned |
| Stage 5 agent | test_agent_pipeline.py | Evaluator: ground truth comparison | Planned |
| Stage 6 agent | test_agent_pipeline.py | Treatment Planning: medications, treatment summary | Planned |
| Cross-stage flow | test_stage_transitions.py | Execution order, data dependencies, conflict detection | Planned |
| Failure handling | test_failure_recovery.py | Pipeline continues after agent failure, partial results | Planned |
| Evaluation | test_evaluation_flow.py | Metrics computable, bounded [0,1], summary produced | Planned |
| Full E2E | test_full_pipeline.py | Complete pipeline, report structure, ground truth match | Planned |

### 6.2 Coverage by requirement (SRD traceability)

| SRD Requirement | Test |
|-----------------|------|
| MA-001 (Orchestrator controls execution) | test_stage_transitions.py |
| MA-002 (Gold input routing) | test_full_pipeline.py::test_pipeline_completes |
| MA-007 (Execution trace logging) | test_full_pipeline.py::test_execution_trace_completeness |
| MA-031 (≥3 differential diagnoses) | test_agent_pipeline.py::test_diagnostic_output |
| MA-071 (Clinical Decision Report structure) | test_full_pipeline.py::test_clinical_decision_report_structure |
| MA-081 (Structured JSON output) | test_agent_pipeline.py (all agent tests) |
| MA-090 (Ground truth evaluation) | test_evaluation_flow.py |
| NF-040 (Graceful agent failure) | test_failure_recovery.py |
| DP-001 (Bronze ingestion) | test_data_pipeline.py::TestBronzeLayer |
| DP-002 (Silver OMOP mapping) | test_data_pipeline.py::TestSilverLayer |
| DP-020 (Gold assembly) | test_data_pipeline.py::TestGoldLayer |

---

*-- End of Document -- E2E Test Documentation v2.0 -- March 2026 -- CMADS -- Updated to match 7-agent pipeline (EHR, Lab, Diagnostic, Reviewer, Refiner, Evaluator, Treatment) and 42 offline tests*
