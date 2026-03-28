"""Offline tests — run without API keys or external services.

Tests schema validation, JSON repair, judge parsing, config loading,
and agent prompt building using mock data only.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.agents.base import _extract_json_from_response
from src.evaluation.judge_common import (
    format_differential, strip_think_tags, parse_judge_response,
)
from src.schemas.ehr_analyst import EHRAnalystOutput
from src.schemas.lab_interpreter import LabInterpreterOutput, LabFinding, LabPanel
from src.schemas.diagnostic import DiagnosticOutput, Diagnosis, SupportingEvidence
from src.schemas.reviewer import ReviewerOutput, DiagnosisVerification, ConsistencyCheck
from src.schemas.treatment import TreatmentOutput, PrescribedMedication
from src.config import Config


# ── JSON Repair Tests ────────────────────────────────────────────────

class TestJsonRepair:
    def test_clean_json(self):
        result = _extract_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_block(self):
        text = 'Here is the output:\n```json\n{"key": "value"}\n```\n'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_trailing_comma(self):
        result = _extract_json_from_response('{"key": "value",}')
        assert result == {"key": "value"}

    def test_single_quotes(self):
        result = _extract_json_from_response("{'key': 'value'}")
        assert result == {"key": "value"}

    def test_think_tags_stripped(self):
        text = '<think>Let me think...</think>{"key": "value"}'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_unclosed_think_tag(self):
        text = '<think>Thinking forever and never closing'
        # After stripping unclosed think tag, no JSON remains — should raise
        with pytest.raises(Exception):
            _extract_json_from_response(text)

    def test_nested_json(self):
        text = '{"findings": [{"name": "Creatinine", "value": "2.0"}]}'
        result = _extract_json_from_response(text)
        assert result["findings"][0]["name"] == "Creatinine"

    def test_text_around_json(self):
        text = 'The analysis shows:\n{"key": "value"}\nEnd of output.'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}


# ── Judge Parsing Tests ──────────────────────────────────────────────

class TestJudgeParsing:
    def test_format_differential(self):
        diff = [
            {"rank": 1, "name": "Diabetes", "probability": 0.5},
            {"rank": 2, "name": "CKD", "probability": 0.3},
        ]
        text = format_differential(diff)
        assert "#1 Diabetes" in text
        assert "#2 CKD" in text

    def test_format_empty_differential(self):
        assert format_differential([]) == ""

    def test_strip_think_tags_closed(self):
        text = "<think>reasoning</think>FOUND: YES"
        assert strip_think_tags(text) == "FOUND: YES"

    def test_strip_think_tags_unclosed(self):
        text = "<think>reasoning that never ends..."
        assert strip_think_tags(text) == ""

    def test_parse_direct_match(self):
        text = "FOUND: YES\nMATCH_TYPE: DIRECT\nRANK: 1\nMATCHED_DIAGNOSIS: Diabetes\nREASON: Exact match"
        result = parse_judge_response(text)
        assert result["found"] == "YES"
        assert result["match_type"] == "DIRECT"
        assert result["rank"] == 1
        assert result["matched_diagnosis"] == "Diabetes"

    def test_parse_indirect_match(self):
        text = "FOUND: YES\nMATCH_TYPE: INDIRECT\nRANK: 3\nMATCHED_DIAGNOSIS: CKD Stage 4\nREASON: Precursor"
        result = parse_judge_response(text)
        assert result["match_type"] == "INDIRECT"
        assert result["rank"] == 3

    def test_parse_miss(self):
        text = "FOUND: NO\nMATCH_TYPE: MISS\nRANK: 0\nMATCHED_DIAGNOSIS: NONE\nREASON: No match"
        result = parse_judge_response(text)
        assert result["found"] == "NO"
        assert result["match_type"] == "MISS"
        assert result["rank"] == 0

    def test_fix_found_inconsistency(self):
        """If match_type is DIRECT but FOUND says NO, fix it to YES."""
        text = "FOUND: NO\nMATCH_TYPE: DIRECT\nRANK: 1\nMATCHED_DIAGNOSIS: HTN\nREASON: Match"
        result = parse_judge_response(text)
        assert result["found"] == "YES"

    def test_parse_with_extra_whitespace(self):
        text = "  FOUND:  YES  \n  MATCH_TYPE:  DIRECT  \n  RANK:  2  \n  MATCHED_DIAGNOSIS:  ESRD  \n  REASON:  Same disease  "
        result = parse_judge_response(text)
        assert result["match_type"] == "DIRECT"
        assert result["rank"] == 2


# ── Schema Validation Tests ──────────────────────────────────────────

class TestSchemas:
    def test_ehr_analyst_empty(self):
        """All fields have defaults — empty dict should validate."""
        output = EHRAnalystOutput.model_validate({})
        assert output.chief_complaint == ""
        assert output.active_problems == []

    def test_lab_interpreter_empty(self):
        output = LabInterpreterOutput.model_validate({})
        assert output.findings == []
        assert output.overall_assessment == ""

    def test_lab_finding_defaults(self):
        finding = LabFinding.model_validate({})
        assert finding.test_name == ""
        assert finding.severity == 1
        assert finding.classification == "abnormal"

    def test_lab_panel_defaults(self):
        panel = LabPanel.model_validate({})
        assert panel.panel_name == ""
        assert panel.contributing_tests == []

    def test_diagnostic_output_empty(self):
        output = DiagnosticOutput.model_validate({})
        assert output.differential == []
        assert output.primary_diagnosis == ""

    def test_diagnosis_defaults(self):
        dx = Diagnosis.model_validate({})
        assert dx.name == ""
        assert dx.rank == 0
        assert dx.probability == 0.0

    def test_supporting_evidence_defaults(self):
        ev = SupportingEvidence.model_validate({})
        assert ev.source == ""
        assert ev.finding == ""
        assert ev.strength == "moderate"

    def test_reviewer_output_empty(self):
        output = ReviewerOutput.model_validate({})
        assert output.diagnosis_verifications == []
        assert output.overall_confidence == 0
        assert output.recommended_primary == ""

    def test_diagnosis_verification_defaults(self):
        dv = DiagnosisVerification.model_validate({})
        assert dv.diagnosis == ""
        assert dv.confidence_score == 0
        assert dv.verdict == "plausible"

    def test_consistency_check_defaults(self):
        cc = ConsistencyCheck.model_validate({})
        assert cc.area == ""
        assert cc.status == "consistent"

    def test_treatment_output_empty(self):
        output = TreatmentOutput.model_validate({})
        assert output.medications == []
        assert output.treatment_summary == ""

    def test_prescribed_medication_defaults(self):
        med = PrescribedMedication.model_validate({})
        assert med.medication == ""
        assert med.line == "first_line"

    def test_diagnostic_output_with_data(self):
        data = {
            "differential": [
                {"rank": 1, "name": "ESRD", "probability": 0.4},
                {"rank": 2, "name": "CKD", "probability": 0.3},
                {"rank": 3, "name": "HTN", "probability": 0.2},
            ],
            "primary_diagnosis": "ESRD",
            "primary_probability": 0.4,
        }
        output = DiagnosticOutput.model_validate(data)
        assert len(output.differential) == 3
        assert output.differential[0].name == "ESRD"


# ── Config Tests ─────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.LLM_PROVIDER == "groq"
        assert config.DIAGNOSTIC_MAX_ROUNDS == 3
        assert config.DIAGNOSTIC_CONFIDENCE_THRESHOLD == 75
        assert config.EMBEDDING_MODEL == "FremyCompany/BioLORD-2023"

    def test_paths_are_path_objects(self):
        config = Config()
        from pathlib import Path
        assert isinstance(config.GOLD_DIR, Path)
        assert isinstance(config.MAS_RESULTS_DIR, Path)

    @patch.dict("os.environ", {"DIAGNOSTIC_MAX_ROUNDS": "5"})
    def test_env_override(self):
        config = Config()
        assert config.DIAGNOSTIC_MAX_ROUNDS == 5

    @patch.dict("os.environ", {"LLM_PROVIDER": "openai"})
    def test_provider_override(self):
        config = Config()
        assert config.LLM_PROVIDER == "openai"


# ── Agent Prompt Building Tests ──────────────────────────────────────

class TestAgentPrompts:
    def test_ehr_analyst_build_prompt(self):
        from src.agents.ehr_analyst import EHRAnalystAgent
        agent = EHRAnalystAgent()
        state = {
            "patient_context": {
                "ehr_case": {
                    "demographics": {"age": 65, "gender": "M"},
                    "conditions": {"active": [
                        {"condition": "Hypertension", "code": "59621000", "start_date": "2010-01-01"}
                    ], "resolved": []},
                    "medications": {"active": [
                        {"medication": "Lisinopril", "condition_treated": "Hypertension"}
                    ]},
                }
            }
        }
        prompt = agent.build_user_prompt(state)
        assert "Hypertension" in prompt
        assert "Lisinopril" in prompt
        assert "65" in prompt

    def test_diagnostic_build_prompt(self):
        from src.agents.diagnostic import DiagnosticReasoningAgent
        agent = DiagnosticReasoningAgent()
        state = {
            "agent_outputs": {
                "ehr_analyst": {
                    "chief_complaint": "Chest pain",
                    "active_problems": [{"name": "HTN", "clinical_significance": "high"}],
                    "active_medications": [{"name": "Aspirin", "purpose": "Cardioprotection"}],
                    "risk_factor_summary": "High CV risk",
                    "clinical_impression": "Possible ACS",
                },
                "lab_interpreter": {
                    "findings": [{"test_name": "Troponin", "value": "0.5", "severity": 5,
                                  "classification": "abnormal", "trend": "rising",
                                  "clinical_note": "Elevated"}],
                    "overall_assessment": "Cardiac markers elevated",
                },
            }
        }
        prompt = agent.build_user_prompt(state)
        assert "Chest pain" in prompt
        assert "Troponin" in prompt
        assert "Aspirin" in prompt

    def test_ehr_analyst_handles_missing_data(self):
        from src.agents.ehr_analyst import EHRAnalystAgent
        agent = EHRAnalystAgent()
        state = {"patient_context": {"ehr_case": {}}}
        prompt = agent.build_user_prompt(state)
        assert "Patient EHR Data" in prompt

    def test_diagnostic_handles_failed_agents(self):
        from src.agents.diagnostic import DiagnosticReasoningAgent
        agent = DiagnosticReasoningAgent()
        state = {"agent_outputs": {}}
        prompt = agent.build_user_prompt(state)
        assert "not available" in prompt


# ── LLM Adapter Tests ────────────────────────────────────────────────

class TestLLMAdapter:
    @patch.dict("os.environ", {"LLM_PROVIDER": "groq", "GROQ_API_KEY": ""}, clear=False)
    def test_missing_api_key_raises(self):
        from src.llm.adapter import get_llm
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            get_llm()

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
    def test_missing_openai_key_raises(self):
        from src.llm.adapter import get_llm
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            get_llm(provider="openai")

    def test_unknown_provider_raises(self):
        from src.llm.adapter import get_llm
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm(provider="invalid_provider")

    def test_provider_registry_has_all(self):
        from src.llm.adapter import PROVIDERS
        assert "groq" in PROVIDERS
        assert "openai" in PROVIDERS
        assert "anthropic" in PROVIDERS
        assert "gemini" in PROVIDERS
        assert "ollama" in PROVIDERS
