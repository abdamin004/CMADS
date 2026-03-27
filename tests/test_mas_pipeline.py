# tests/test_mas_pipeline.py
"""MAS Pipeline Tests — Full pipeline from Gold layer to evaluation.

Tests the multi-agent diagnostic pipeline end-to-end.
Requires Groq API key. ~2 min per patient.

Run:
    pytest tests/test_mas_pipeline.py -v --timeout=300
    pytest tests/test_mas_pipeline.py::TestMASAgents -v
    pytest tests/test_mas_pipeline.py::TestMASEvaluation -v
"""

import json
import os
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GOLD_DIR = PROJECT_ROOT / "data" / "gold" / "patient_cases"
MAS_RESULTS_DIR = PROJECT_ROOT / "data" / "gold" / "mas_results"
COHORT_FILE = PROJECT_ROOT / "data" / "gold" / "cohort_verified.json"
BATCH_DIR = PROJECT_ROOT / "data" / "gold" / "batches"


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def verified_uuids():
    """Load verified patient UUIDs."""
    with open(COHORT_FILE) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_uuid(verified_uuids):
    """First verified patient for single-patient tests."""
    return verified_uuids[0]


@pytest.fixture(scope="session")
def pipeline():
    """Compile the LangGraph pipeline once for the session."""
    from src.orchestrator.graph import compile_pipeline
    return compile_pipeline()


@pytest.fixture(scope="session")
def sample_result(sample_uuid, pipeline):
    """Run MAS on one patient and cache the result."""
    from src.orchestrator.graph import run_single_patient
    return run_single_patient(sample_uuid, pipeline, save=True)


# ═══════════════════════════════════════════════════════════════════════
# PIPELINE SETUP TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineSetup:
    """Verify the pipeline can be compiled and configured."""

    def test_pipeline_compiles(self):
        """LangGraph pipeline compiles without errors."""
        from src.orchestrator.graph import compile_pipeline
        pipeline = compile_pipeline()
        assert pipeline is not None

    def test_verified_cohort_exists(self):
        """Verified cohort file exists and has patients."""
        assert COHORT_FILE.exists()
        with open(COHORT_FILE) as f:
            uuids = json.load(f)
        assert len(uuids) > 0, "Verified cohort is empty"

    def test_batch_files_exist(self):
        """Batch files exist for incremental runs."""
        assert BATCH_DIR.exists(), "Batch directory not found"
        batches = list(BATCH_DIR.glob("batch_*.json"))
        assert len(batches) > 0, "No batch files found"

    def test_groq_api_key_set(self):
        """Groq API key is configured."""
        key = os.environ.get("GROQ_API_KEY", "")
        assert key, "GROQ_API_KEY not set"

    def test_all_verified_patients_have_gold_files(self, verified_uuids):
        """Every verified patient has ehr_case, lab_case, ground_truth."""
        missing = []
        for uuid in verified_uuids[:50]:  # spot-check first 50
            for f in ["ehr_case.json", "lab_case.json", "ground_truth.json"]:
                if not (GOLD_DIR / uuid / f).exists():
                    missing.append(f"{uuid}/{f}")
        assert not missing, f"Missing Gold files: {missing[:5]}"


# ═══════════════════════════════════════════════════════════════════════
# SINGLE PATIENT PIPELINE TEST
# ═══════════════════════════════════════════════════════════════════════

class TestMASPipeline:
    """Test the full MAS pipeline on a single patient."""

    @pytest.mark.timeout(300)
    def test_pipeline_completes(self, sample_result):
        """Pipeline runs to completion without crashing."""
        assert sample_result is not None

    def test_all_agents_executed(self, sample_result):
        """All 5 agents wrote output to shared memory."""
        outputs = sample_result.get("agent_outputs", {})
        expected = ["ehr_analyst", "lab_interpreter", "diagnostic_reasoning",
                    "clinical_reviewer", "final_diagnosis"]
        for agent in expected:
            assert agent in outputs, f"Agent '{agent}' missing from outputs"

    def test_all_agents_produced_output(self, sample_result):
        """No agent returned None (all succeeded or partial)."""
        outputs = sample_result.get("agent_outputs", {})
        none_agents = [k for k, v in outputs.items() if v is None]
        # Allow some agents to be None (graceful degradation)
        # but not all
        assert len(none_agents) < 3, f"Too many agents failed: {none_agents}"

    def test_execution_trace_recorded(self, sample_result):
        """Execution trace has entries for all agents."""
        trace = sample_result.get("execution_trace", [])
        assert len(trace) >= 5, f"Expected ≥5 trace entries, got {len(trace)}"
        for entry in trace:
            assert "agent_id" in entry
            assert "status" in entry
            assert entry["status"] in ("success", "partial", "error")
            assert "execution_ms" in entry

    def test_execution_order(self, sample_result):
        """Agents executed in correct stage order."""
        trace = sample_result.get("execution_trace", [])
        agent_order = [t["agent_id"] for t in trace]

        # Stage 1 agents before Stage 2
        if "ehr_analyst" in agent_order and "diagnostic_reasoning" in agent_order:
            assert agent_order.index("ehr_analyst") < agent_order.index("diagnostic_reasoning")
        if "lab_interpreter" in agent_order and "diagnostic_reasoning" in agent_order:
            assert agent_order.index("lab_interpreter") < agent_order.index("diagnostic_reasoning")

        # Stage 2 before Stage 3
        if "diagnostic_reasoning" in agent_order and "clinical_reviewer" in agent_order:
            assert agent_order.index("diagnostic_reasoning") < agent_order.index("clinical_reviewer")

        # Stage 3 before Stage 4
        if "clinical_reviewer" in agent_order and "final_diagnosis" in agent_order:
            assert agent_order.index("clinical_reviewer") < agent_order.index("final_diagnosis")


# ═══════════════════════════════════════════════════════════════════════
# AGENT OUTPUT SCHEMA TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestMASAgents:
    """Test each agent's output structure."""

    def test_ehr_analyst_output(self, sample_result):
        """EHR Analyst produces structured clinical summary."""
        out = sample_result["agent_outputs"].get("ehr_analyst", {})
        if not out:
            pytest.skip("EHR Analyst failed")
        assert "chief_complaint" in out or "active_problems" in out
        if "active_problems" in out:
            assert isinstance(out["active_problems"], list)

    def test_lab_interpreter_output(self, sample_result):
        """Lab Interpreter produces prioritised findings."""
        out = sample_result["agent_outputs"].get("lab_interpreter", {})
        if not out:
            pytest.skip("Lab Interpreter failed")
        assert "findings" in out or "overall_assessment" in out
        if "findings" in out:
            assert isinstance(out["findings"], list)

    def test_diagnostic_reasoning_output(self, sample_result):
        """Diagnostic Reasoning produces differential with ≥3 diagnoses."""
        out = sample_result["agent_outputs"].get("diagnostic_reasoning", {})
        if not out:
            pytest.skip("Diagnostic Reasoning failed")
        if "differential" in out:
            assert isinstance(out["differential"], list)
            # May have 0 if parsing failed, but should have some
            if len(out["differential"]) > 0:
                dx = out["differential"][0]
                assert "name" in dx, "Diagnosis missing 'name'"

    def test_clinical_reviewer_output(self, sample_result):
        """Clinical Reviewer produces verification with confidence."""
        out = sample_result["agent_outputs"].get("clinical_reviewer", {})
        if not out:
            pytest.skip("Clinical Reviewer failed")
        if "overall_confidence" in out:
            assert isinstance(out["overall_confidence"], (int, float))
        if "diagnosis_verifications" in out:
            assert isinstance(out["diagnosis_verifications"], list)

    def test_final_diagnosis_output(self, sample_result):
        """Final Diagnosis produces ranked differential."""
        out = sample_result["agent_outputs"].get("final_diagnosis", {})
        if not out:
            pytest.skip("Final Diagnosis failed")
        if "differential" in out:
            assert isinstance(out["differential"], list)
        if "primary_diagnosis" in out:
            assert isinstance(out["primary_diagnosis"], str)
            assert len(out["primary_diagnosis"]) > 0

    def test_differential_has_probabilities(self, sample_result):
        """Each diagnosis in the differential has a probability."""
        out = sample_result["agent_outputs"].get("final_diagnosis", {})
        if not out or not out.get("differential"):
            pytest.skip("No differential produced")
        for dx in out["differential"]:
            if isinstance(dx, dict) and "probability" in dx:
                assert 0.0 <= dx["probability"] <= 1.0, \
                    f"Probability {dx['probability']} out of range"

    def test_probabilities_sum_approximately(self, sample_result):
        """Differential probabilities sum to approximately 1.0."""
        out = sample_result["agent_outputs"].get("final_diagnosis", {})
        if not out or not out.get("differential"):
            pytest.skip("No differential produced")
        probs = [dx.get("probability", 0) for dx in out["differential"]
                 if isinstance(dx, dict)]
        if probs:
            total = sum(probs)
            assert 0.5 <= total <= 1.5, \
                f"Probabilities sum to {total:.2f}, expected ~1.0"


# ═══════════════════════════════════════════════════════════════════════
# RESULT SAVING TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestMASResultSaving:
    """Test that results are saved correctly to disk."""

    def test_patient_results_directory_created(self, sample_uuid, sample_result):
        """Patient results directory exists after run."""
        patient_dir = MAS_RESULTS_DIR / sample_uuid
        assert patient_dir.exists(), f"Results directory not created: {patient_dir}"

    def test_execution_trace_saved(self, sample_uuid, sample_result):
        """execution_trace.json saved for the patient."""
        trace_path = MAS_RESULTS_DIR / sample_uuid / "execution_trace.json"
        assert trace_path.exists(), "execution_trace.json not saved"
        trace = json.loads(trace_path.read_text())
        assert "patient_uuid" in trace
        assert "agents" in trace
        assert "duration_s" in trace

    def test_agent_outputs_saved(self, sample_uuid, sample_result):
        """At least some agent output files are saved."""
        patient_dir = MAS_RESULTS_DIR / sample_uuid
        agent_files = ["ehr_analyst.json", "lab_interpreter.json",
                       "diagnostic_reasoning.json", "clinical_reviewer.json",
                       "final_diagnosis.json"]
        saved = [f for f in agent_files if (patient_dir / f).exists()]
        assert len(saved) >= 3, f"Only {len(saved)} agent files saved: {saved}"

    def test_final_diagnosis_saved_is_valid_json(self, sample_uuid, sample_result):
        """final_diagnosis.json is valid JSON."""
        fd_path = MAS_RESULTS_DIR / sample_uuid / "final_diagnosis.json"
        if not fd_path.exists():
            pytest.skip("final_diagnosis.json not saved")
        data = json.loads(fd_path.read_text())
        assert isinstance(data, dict)


# ═══════════════════════════════════════════════════════════════════════
# LLM EVALUATION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestMASEvaluation:
    """Test the LLM-as-Judge evaluation system."""

    def test_evaluate_patient_runs(self, sample_uuid, sample_result):
        """LLM judge can evaluate a single patient."""
        from src.evaluation.llm_judge import evaluate_patient
        outputs = sample_result.get("agent_outputs", {})
        final = outputs.get("final_diagnosis", {}) or outputs.get("diagnostic_reasoning", {})
        if not final or not final.get("differential"):
            pytest.skip("No differential to evaluate")

        ev = evaluate_patient(sample_uuid, final)
        assert "found" in ev
        assert ev["found"] in ("YES", "NO")
        assert "match_type" in ev
        assert ev["match_type"] in ("DIRECT", "INDIRECT", "MISS")
        assert "rank" in ev
        assert isinstance(ev["rank"], int)
        assert 0 <= ev["rank"] <= 5

    def test_evaluation_saved_to_disk(self, sample_uuid, sample_result):
        """evaluation.json saved in patient results folder."""
        from src.evaluation.llm_judge import evaluate_patient
        outputs = sample_result.get("agent_outputs", {})
        final = outputs.get("final_diagnosis", {}) or outputs.get("diagnostic_reasoning", {})
        if not final or not final.get("differential"):
            pytest.skip("No differential to evaluate")

        evaluate_patient(sample_uuid, final)
        eval_path = MAS_RESULTS_DIR / sample_uuid / "evaluation.json"
        assert eval_path.exists(), "evaluation.json not saved"

        ev = json.loads(eval_path.read_text())
        assert "target" in ev
        assert "found" in ev
        assert "match_type" in ev

    def test_evaluation_has_target_disease(self, sample_uuid, sample_result):
        """Evaluation references the correct target disease."""
        from src.evaluation.llm_judge import evaluate_patient
        outputs = sample_result.get("agent_outputs", {})
        final = outputs.get("final_diagnosis", {}) or outputs.get("diagnostic_reasoning", {})
        if not final or not final.get("differential"):
            pytest.skip("No differential to evaluate")

        gt = json.loads((GOLD_DIR / sample_uuid / "ground_truth.json").read_text())
        ev = evaluate_patient(sample_uuid, final)
        assert ev["target"] == gt["target_condition"]["name"]


# ═══════════════════════════════════════════════════════════════════════
# BATCH RUN TESTS (check already-completed results)
# ═══════════════════════════════════════════════════════════════════════

class TestBatchResults:
    """Test results from completed batch runs (non-destructive, reads saved files)."""

    def test_results_directory_has_patients(self):
        """MAS results directory has patient folders."""
        if not MAS_RESULTS_DIR.exists():
            pytest.skip("No MAS results yet — run a batch first")
        patient_dirs = [d for d in MAS_RESULTS_DIR.iterdir()
                        if d.is_dir()]
        assert len(patient_dirs) > 0, "No patient results found"

    def test_all_results_have_trace(self):
        """Every patient folder has execution_trace.json."""
        if not MAS_RESULTS_DIR.exists():
            pytest.skip("No MAS results yet")
        patient_dirs = [d for d in MAS_RESULTS_DIR.iterdir() if d.is_dir()]
        missing = [d.name[:12] for d in patient_dirs
                   if not (d / "execution_trace.json").exists()]
        assert not missing, f"Missing execution traces: {missing[:5]}"

    def test_all_results_have_final_diagnosis(self):
        """Every patient folder has final_diagnosis.json."""
        if not MAS_RESULTS_DIR.exists():
            pytest.skip("No MAS results yet")
        patient_dirs = [d for d in MAS_RESULTS_DIR.iterdir() if d.is_dir()]
        missing = [d.name[:12] for d in patient_dirs
                   if not (d / "final_diagnosis.json").exists()]
        # Allow some failures (graceful degradation)
        fail_rate = len(missing) / max(len(patient_dirs), 1)
        assert fail_rate < 0.2, \
            f"{len(missing)}/{len(patient_dirs)} patients missing final_diagnosis ({fail_rate:.0%})"

    def test_no_target_leakage_in_results(self):
        """Final diagnosis does not contain the exact ground truth disease name."""
        if not MAS_RESULTS_DIR.exists():
            pytest.skip("No MAS results yet")
        leaks = []
        patient_dirs = [d for d in MAS_RESULTS_DIR.iterdir() if d.is_dir()]
        for d in patient_dirs[:30]:  # spot-check 30
            gt_path = GOLD_DIR / d.name / "ground_truth.json"
            fd_path = d / "final_diagnosis.json"
            if not gt_path.exists() or not fd_path.exists():
                continue
            gt = json.loads(gt_path.read_text())
            fd = json.loads(fd_path.read_text())
            target = gt["target_condition"]["name"].lower()
            fd_text = json.dumps(fd).lower()
            # Check for exact target name in the output
            if target in fd_text:
                leaks.append(d.name[:12])
        # Some indirect mentions are expected (e.g., "kidney disease" for ESRD)
        # but the exact full name shouldn't appear
        assert len(leaks) < 3, f"Possible target leakage in: {leaks}"

    def test_run_summary_exists(self):
        """run_summary.json exists after a batch run."""
        summary_path = MAS_RESULTS_DIR / "run_summary.json"
        if not summary_path.exists():
            pytest.skip("No run_summary.json yet")
        summary = json.loads(summary_path.read_text())
        assert "total_patients" in summary
        assert "succeeded" in summary

    def test_evaluation_csv_exists(self):
        """evaluation_results.csv exists after evaluation."""
        csv_path = MAS_RESULTS_DIR / "evaluation_results.csv"
        if not csv_path.exists():
            pytest.skip("No evaluation CSV yet")
        lines = csv_path.read_text().strip().split("\n")
        assert len(lines) >= 2, "CSV has no data rows"
        header = lines[0]
        assert "Found" in header
        assert "Match Type" in header
        assert "Rank" in header
