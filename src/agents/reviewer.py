"""Clinical Reviewer Agent — Stage 3 (verifies Stage 2 diagnostic output).

Reads: agent_outputs.ehr_analyst, agent_outputs.lab_interpreter,
       agent_outputs.diagnostic_reasoning, patient_context
Writes: agent_outputs.clinical_reviewer

Acts as a second opinion — independently verifies each diagnosis against
the raw evidence, adjusts probabilities, and gives per-disease confidence.

Implements: SDD §5.6, MA-050–054
"""

import json
import structlog
from src.agents.base import BaseAgent
from src.schemas.reviewer import ReviewerOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()


class ClinicalReviewerAgent(BaseAgent):
    agent_id = "clinical_reviewer"
    output_schema = ReviewerOutput
    temperature = 0.2
    max_tokens = 8192

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Multi-call review:
        Call 1: Independent evidence analysis — what does the raw data actually say?
        Call 2: Per-diagnosis verification against raw evidence
        Call 3: Produce structured JSON
        """
        patient_data = self.build_user_prompt(state)

        # ── Call 1: Independent Evidence Re-analysis ──
        logger.info("agent_step", agent_id=self.agent_id, step="evidence_reanalysis")
        analysis = self._call_llm(llm,
            system=self._get_call_prompt("evidence_reanalysis", "system",
                fallback="You are a senior attending physician independently reviewing patient evidence."),
            user=self._get_call_prompt("evidence_reanalysis", "user",
                fallback=patient_data, patient_data=patient_data),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="evidence_reanalysis",
                     length=len(analysis))

        # ── Call 2: Per-Diagnosis Verification ──
        logger.info("agent_step", agent_id=self.agent_id, step="verification")
        verification = self._call_llm(llm,
            system=self._get_call_prompt("verification", "system",
                fallback="You are a senior attending reviewing a junior diagnostician's differential."),
            user=self._get_call_prompt("verification", "user",
                fallback=f"{analysis}\n{patient_data}",
                analysis=analysis, patient_data=patient_data),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="verification",
                     length=len(verification))

        # ── Call 3: Structured JSON Output (use json_llm) ──
        logger.info("agent_step", agent_id=self.agent_id, step="structure")
        jllm = json_llm or llm
        output_schema = json.dumps(ReviewerOutput.model_json_schema(), indent=2)
        raw_json = self._call_llm(jllm,
            system=self._get_call_prompt("structure", "system",
                fallback=self.system_prompt),
            user=self._get_call_prompt("structure", "user",
                fallback=f"{analysis}\n{verification}",
                analysis=analysis, verification=verification,
                output_schema=output_schema),
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Produce review JSON"),
        ])
        logger.info("agent_step_done", agent_id=self.agent_id, step="structure")

        return output.model_dump()

    def build_user_prompt(self, state: dict) -> str:
        ctx = state.get("patient_context", {})
        agent_outputs = state.get("agent_outputs", {})
        ehr_out = agent_outputs.get("ehr_analyst", {})
        lab_out = agent_outputs.get("lab_interpreter", {})
        diag_out = agent_outputs.get("diagnostic_reasoning", {})
        ehr_case = ctx.get("ehr_case", {})

        sections = []

        # ── Diagnostic Agent's Output (what we're reviewing) ──
        sections.append("## DIAGNOSTIC AGENT OUTPUT (to be reviewed)\n")
        if diag_out:
            sections.append(f"**Primary Diagnosis:** {diag_out.get('primary_diagnosis', '?')} "
                            f"(P={diag_out.get('primary_probability', '?')})\n")

            diff = diag_out.get("differential", [])
            if diff:
                sections.append(f"**Differential ({len(diff)} diagnoses):**")
                for d in diff:
                    if isinstance(d, dict):
                        sections.append(f"  #{d.get('rank','?')} {d.get('name','?')} — "
                                        f"P={d.get('probability','?')} ({d.get('confidence','?')})")
                        for e in d.get('supporting_evidence', []):
                            if isinstance(e, dict):
                                sections.append(f"    [{e.get('source','?')}] {e.get('finding','?')[:80]}")
                        sections.append(f"    Reasoning: {d.get('reasoning','?')[:120]}")
                sections.append("")

            if diag_out.get('unresolved_findings'):
                sections.append("**Unresolved Findings:**")
                for f in diag_out['unresolved_findings']:
                    sections.append(f"  ? {f[:80]}")
                sections.append("")

            sections.append(f"**Reasoning Summary:**\n{diag_out.get('clinical_reasoning_summary', '?')[:300]}\n")
        else:
            sections.append("*Diagnostic output not available*\n")

        # ── Raw Evidence (EHR Analyst) ──
        sections.append("## RAW EVIDENCE: EHR Analyst Output\n")
        if ehr_out:
            sections.append(f"**Chief Complaint:** {ehr_out.get('chief_complaint', '?')}\n")
            problems = ehr_out.get("active_problems", [])
            if problems:
                sections.append(f"**Active Problems ({len(problems)}):**")
                for p in problems:
                    if isinstance(p, dict):
                        sections.append(f"  [{p.get('clinical_significance','?')}] {p.get('name','?')}")
                sections.append("")
            sections.append(f"**Risk Factors:** {ehr_out.get('risk_factor_summary', '?')[:200]}\n")
            sections.append(f"**Clinical Impression:** {ehr_out.get('clinical_impression', '?')[:200]}\n")
        else:
            sections.append("*EHR output not available*\n")

        # ── Raw Evidence (Lab Interpreter) ──
        sections.append("## RAW EVIDENCE: Lab Interpreter Output\n")
        if lab_out:
            findings = lab_out.get("findings", [])
            if findings:
                sections.append(f"**Lab Findings ({len(findings)}):**")
                for f in findings:
                    if isinstance(f, dict):
                        marker = "!!" if f.get('severity', 0) >= 3 else "  "
                        sections.append(f"  {marker}[sev {f.get('severity','?')}] {f.get('test_name','?')}: "
                                        f"{f.get('value','?')} ({f.get('classification','?')}, {f.get('trend','?')})")
                sections.append("")
            sections.append(f"**Overall Assessment:** {lab_out.get('overall_assessment', '?')[:200]}\n")
        else:
            sections.append("*Lab output not available*\n")

        # ── Risk Scores from Gold Layer ──
        risk = ehr_case.get("risk_scores", {})
        comorbidity = ehr_case.get("comorbidity", {})
        if risk or comorbidity:
            sections.append("## RISK SCORES & COMORBIDITY\n")
            if risk:
                sections.append(f"{json.dumps(risk, indent=2, default=str)}\n")
            if comorbidity:
                sections.append(f"{json.dumps(comorbidity, indent=2, default=str)}\n")

        return "\n".join(sections)


# LangGraph node function
clinical_reviewer_agent = ClinicalReviewerAgent()
