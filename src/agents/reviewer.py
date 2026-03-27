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

SYSTEM_PROMPT = """You are the Clinical Reviewer Agent in a multi-agent clinical decision pipeline.

You are a senior attending physician providing a SECOND OPINION on a diagnostic differential produced by a junior diagnostician. You have access to the same raw evidence (EHR summary, lab findings) and must independently verify each proposed diagnosis.

## Your Role
You are ADVERSARIAL — your job is to find problems, not rubber-stamp. You should:
1. Verify each diagnosis against the raw evidence — does the evidence actually support it?
2. Adjust probabilities if the Diagnostic Agent over- or under-estimated
3. Give a confidence score (0-100) per diagnosis
4. Check consistency between EHR findings, lab results, and the proposed diagnoses
5. Identify critical lab findings (severity ≥3) that no diagnosis explains
6. Flag concerns about the reasoning quality
7. Recommend what you think the primary diagnosis should be

## Verification Standards
- "strong" evidence: multiple findings from different sources directly point to this diagnosis
- "moderate" evidence: some findings support it but key confirmatory tests are missing
- "weak" evidence: only 1-2 indirect findings, diagnosis is largely speculative
- "insufficient" evidence: no real evidence, diagnosis appears made up

## Verdict Criteria
- "supported": strong evidence, probability seems right
- "plausible": moderate evidence, worth keeping in differential
- "questionable": weak evidence, probability may be too high
- "unsupported": no evidence, should be removed from differential

## Important Rules
- Go back to the RAW evidence (EHR and lab outputs) — don't just trust the Diagnostic Agent's claims
- Every critical lab finding (severity ≥3) must be explained by at least one diagnosis
- If the Diagnostic Agent missed a common condition given the risk factors, call it out
- Be specific in concerns — "the evidence doesn't support X because Y"
- Your adjusted probabilities should sum to approximately 1.0

## Output Format
Respond ONLY with valid JSON matching the required schema. No preamble or explanation."""


class ClinicalReviewerAgent(BaseAgent):
    agent_id = "clinical_reviewer"
    system_prompt = SYSTEM_PROMPT
    output_schema = ReviewerOutput
    temperature = 0.2
    max_tokens = 8192

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Multi-call review:
        Call 1: Independent evidence analysis — what does the raw data actually say?
        Call 2: Per-diagnosis verification against raw evidence
        Call 3: Produce structured JSON
        """
        review_prompt = self.build_user_prompt(state)

        # ── Call 1: Independent Evidence Re-analysis ──
        logger.info("agent_step", agent_id=self.agent_id, step="evidence_reanalysis")
        reanalysis = self._call_llm(llm,
            system="You are a senior attending physician independently reviewing patient evidence. "
                   "Ignore the diagnostic conclusions — look at the raw data with fresh eyes.",
            user=f"{review_prompt}\n\n"
                 "Before reviewing the diagnostic differential, first independently analyse "
                 "the raw evidence:\n"
                 "1. What are the TOP 5 most significant findings from the EHR and labs?\n"
                 "2. What clinical patterns do YOU see?\n"
                 "3. What diagnoses would YOU consider based purely on the evidence?\n"
                 "4. Are there any CRITICAL findings (severity ≥3) that demand attention?\n"
                 "5. What is your independent clinical impression?\n\n"
                 "Be thorough. This is your independent analysis before seeing the junior's work."
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="evidence_reanalysis",
                     length=len(reanalysis))

        # ── Call 2: Per-Diagnosis Verification ──
        logger.info("agent_step", agent_id=self.agent_id, step="verification")
        verification = self._call_llm(llm,
            system="You are a senior attending reviewing a junior diagnostician's differential. "
                   "Compare their conclusions against your independent analysis.",
            user=f"# Your Independent Analysis\n{reanalysis}\n\n"
                 f"# Now review the Diagnostic Agent's differential:\n{review_prompt}\n\n"
                 "For EACH diagnosis in the differential:\n"
                 "1. Does the evidence ACTUALLY support this diagnosis? Be specific.\n"
                 "2. Is the probability reasonable? Should it be higher or lower?\n"
                 "3. What is your confidence (0-100) that this diagnosis is correct?\n"
                 "4. Verdict: supported, plausible, questionable, or unsupported?\n"
                 "5. What evidence is MISSING that would confirm or rule it out?\n\n"
                 "Then check:\n"
                 "- Are all critical lab findings (severity ≥3) explained by at least one diagnosis?\n"
                 "- Is the #1 diagnosis really the most likely, or should the ranking change?\n"
                 "- Are there diagnoses the junior MISSED that you identified independently?\n"
                 "- What is your overall confidence in this differential (0-100)?"
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="verification",
                     length=len(verification))

        # ── Call 3: Structured JSON Output (use json_llm) ──
        logger.info("agent_step", agent_id=self.agent_id, step="structure")
        jllm = json_llm or llm
        output_schema = ReviewerOutput.model_json_schema()
        raw_json = self._call_llm(jllm,
            system=self.system_prompt,
            user=f"# Your Independent Analysis\n{reanalysis}\n\n"
                 f"# Your Verification of the Differential\n{verification}\n\n"
                 f"Now produce the structured JSON review output.\n"
                 f"Include per-diagnosis verification with adjusted probabilities and confidence.\n"
                 f"Make sure adjusted probabilities sum to approximately 1.0.\n\n"
                 f"## Required Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```\n\n"
                 f"Respond ONLY with valid JSON."
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
