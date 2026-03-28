"""Diagnostic Refiner Agent — Post-Reviewer refinement step.

Reads: agent_outputs.diagnostic_reasoning, agent_outputs.clinical_reviewer,
       agent_outputs.ehr_analyst, agent_outputs.lab_interpreter
Writes: agent_outputs.final_diagnosis

Takes the Reviewer's concerns and adjusts the differential accordingly.
This is the FINAL diagnostic output that downstream agents use.
"""

import json
import structlog
from src.agents.base import BaseAgent
from src.schemas.diagnostic import DiagnosticOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()


class DiagnosticRefinerAgent(BaseAgent):
    agent_id = "final_diagnosis"
    output_schema = DiagnosticOutput
    temperature = 0.2
    max_tokens = 8192

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Single focused call — merge Diagnostic + Reviewer into final differential."""
        agent_outputs = state.get("agent_outputs", {})
        diag_out = agent_outputs.get("diagnostic_reasoning", {})
        rev_out = agent_outputs.get("clinical_reviewer", {})
        ehr_out = agent_outputs.get("ehr_analyst", {})
        lab_out = agent_outputs.get("lab_interpreter", {})

        sections = []

        # Diagnostic Agent's differential
        sections.append("## DIAGNOSTIC AGENT OUTPUT\n")
        if diag_out:
            sections.append(f"Primary: {diag_out.get('primary_diagnosis', '?')} "
                            f"(P={diag_out.get('primary_probability', '?')})")
            for d in diag_out.get('differential', []):
                if isinstance(d, dict):
                    sections.append(f"  #{d.get('rank','?')} {d.get('name','?')} P={d.get('probability','?')}")
            if diag_out.get('unresolved_findings'):
                sections.append(f"\nUnresolved: {diag_out['unresolved_findings']}")
        sections.append("")

        # Reviewer's verification
        sections.append("## REVIEWER VERIFICATION\n")
        if rev_out:
            sections.append(f"Overall confidence: {rev_out.get('overall_confidence', '?')}/100")
            sections.append(f"Reviewer recommends: {rev_out.get('recommended_primary', '?')} "
                            f"(confidence: {rev_out.get('recommended_primary_confidence', '?')})")

            for v in rev_out.get('diagnosis_verifications', []):
                if isinstance(v, dict):
                    sections.append(f"\n  {v.get('diagnosis', '?')}")
                    sections.append(f"    Original P={v.get('original_probability','?')} → "
                                    f"Adjusted P={v.get('verified_probability','?')}")
                    sections.append(f"    Confidence: {v.get('confidence_score','?')}/100 | "
                                    f"Verdict: {v.get('verdict','?')} ({v.get('evidence_strength','?')})")
                    if v.get('concerns'):
                        for c in v['concerns']:
                            sections.append(f"    ⚠ {c[:100]}")

            if rev_out.get('critical_findings_missed'):
                sections.append(f"\nCritical findings MISSED:")
                for f in rev_out['critical_findings_missed']:
                    sections.append(f"  !! {f}")

            if rev_out.get('top_concerns'):
                sections.append(f"\nTop concerns:")
                for c in rev_out['top_concerns']:
                    sections.append(f"  → {c[:100]}")
        sections.append("")

        # Key evidence summary
        sections.append("## KEY EVIDENCE SUMMARY\n")
        if ehr_out:
            sections.append(f"EHR impression: {ehr_out.get('clinical_impression', '?')[:200]}")
            sections.append(f"Risk factors: {ehr_out.get('risk_factor_summary', '?')[:200]}")
        if lab_out:
            sections.append(f"Lab assessment: {lab_out.get('overall_assessment', '?')[:200]}")
        sections.append("")

        prompt_data = "\n".join(sections)

        # Single focused call with json_llm
        jllm = json_llm or llm
        output_schema = json.dumps(DiagnosticOutput.model_json_schema(), indent=2)

        logger.info("agent_step", agent_id=self.agent_id, step="refine")
        raw_json = self._call_llm(jllm,
            system=self._get_call_prompt("refine", "system",
                fallback=self.system_prompt),
            user=self._get_call_prompt("refine", "user",
                fallback=f"{prompt_data}\n{output_schema}",
                prompt_data=prompt_data, output_schema=output_schema),
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Produce final JSON"),
        ])
        result = output.model_dump()
        self._autofill_primary_diagnosis(result)

        logger.info("agent_step_done", agent_id=self.agent_id, step="refine")
        return result


# LangGraph node function
diagnostic_refiner_agent = DiagnosticRefinerAgent()
