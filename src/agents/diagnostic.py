"""Diagnostic Reasoning Agent — Stage 2.

Reads: agent_outputs.ehr_analyst, agent_outputs.lab_interpreter,
       patient_context (risk_scores, comorbidity_matrix)
Writes: agent_outputs.diagnostic_reasoning

Synthesises clinical picture with lab evidence to generate a ranked
differential diagnosis with ≥3 diagnoses, evidence mapping, and
probability estimates.

Implements: SDD §5.4, MA-030–034
"""

import json
import re
import structlog
from src.agents.base import BaseAgent
from src.schemas.diagnostic import DiagnosticOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Diagnostic Reasoning Agent in a multi-agent clinical decision pipeline.

You receive a structured clinical summary from the EHR Analyst and prioritised lab findings from the Lab Interpreter. Your job is to synthesise ALL available evidence and produce a ranked differential diagnosis.

## Your Task
1. Analyse the clinical summary (conditions, medications, demographics, visit patterns)
2. Analyse the lab findings (abnormal values, trends, panel patterns, critical alerts)
3. Cross-reference with risk scores and comorbidity flags
4. Generate a RANKED differential diagnosis with ≥3 diagnoses
5. For each diagnosis, map specific evidence from the upstream agents
6. Assign probability estimates that sum to approximately 1.0 across all diagnoses
7. Flag unexplained findings that don't fit any diagnosis
8. Recommend additional workup to confirm/rule out diagnoses

## Reasoning Guidelines
- Consider the FULL clinical picture — don't anchor on one finding
- Look for patterns: multiple findings pointing to the same diagnosis
- Consider age, gender, and demographics as risk modifiers
- Comorbidities can mask or mimic other conditions — account for this
- Rising trends in labs are more concerning than isolated abnormal values
- Missing data (data gaps flagged by upstream agents) should factor into confidence
- Consider common diseases first (Bayesian reasoning), then rare conditions
- Each diagnosis must have at least one piece of supporting evidence
- Be specific with diagnosis names — use proper medical terminology

## Important Rules
- You are DIAGNOSING, not just summarising — commit to ranked diagnoses with probabilities
- Every diagnosis needs evidence from the upstream agent outputs
- The primary diagnosis should have the highest probability
- Include at least 3 differential diagnoses, ideally 4-6
- Probabilities should reflect genuine clinical judgement, not arbitrary numbers
- Flag any findings that no diagnosis explains (unresolved_findings)

## Output Format
Respond ONLY with valid JSON matching the required schema. No preamble or explanation."""


class DiagnosticReasoningAgent(BaseAgent):
    agent_id = "diagnostic_reasoning"
    system_prompt = SYSTEM_PROMPT
    output_schema = DiagnosticOutput
    temperature = 0.3
    max_tokens = 8192

    MAX_REASONING_ROUNDS = 3
    CONFIDENCE_THRESHOLD = 75

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Adaptive multi-call diagnostic reasoning.

        Fixed calls:
          1. Evidence synthesis — organize findings into clinical patterns
          2. Hypothesis generation — broad list of possible diagnoses
          3. Initial differential ranking with probabilities

        Adaptive loop (repeats until confident or max rounds):
          4. Self-critique — check for anchoring bias, missed diagnoses
          5. Confidence check — is the primary diagnosis confident enough?
             → Yes: stop
             → No: investigate gaps, refine differential, loop back to step 4

        Final call:
          N. Produce structured JSON output
        """
        evidence = self.build_user_prompt(state)

        # ── Call 1: Evidence Synthesis (always) ──
        logger.info("agent_step", agent_id=self.agent_id, step="evidence_synthesis")
        synthesis = self._call_llm(llm,
            system="You are a senior diagnostician synthesising clinical evidence. "
                   "Do NOT diagnose yet. Organise the evidence into clinical patterns.",
            user=f"{evidence}\n\n"
                 "Organise ALL the evidence into clinical patterns:\n"
                 "1. Identify ALL abnormal findings and group them by organ system\n"
                 "2. Look for patterns: multiple findings pointing to the same organ or disease\n"
                 "3. Note the patient's demographics and how they affect disease probability\n"
                 "4. Identify medication clues — what conditions do the prescribed drugs treat?\n"
                 "5. Note risk factors from the EHR analyst's summary\n"
                 "6. Identify findings that don't fit any obvious pattern\n\n"
                 "For each pattern, list the specific evidence supporting it.\n"
                 "Be exhaustive — do not skip any finding."
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="evidence_synthesis",
                     length=len(synthesis))

        # ── Call 2: Broad Hypothesis Generation (always) ──
        logger.info("agent_step", agent_id=self.agent_id, step="hypothesis_generation")
        hypotheses = self._call_llm(llm,
            system="You are a diagnostician generating hypotheses. "
                   "Think broadly — common diseases first, then less common ones.",
            user=f"# Clinical Patterns Identified\n{synthesis}\n\n"
                 "Generate a BROAD list of possible diagnoses.\n"
                 "Think about:\n"
                 "- What common diseases explain multiple patterns at once?\n"
                 "- Given the demographics, what are the most prevalent conditions?\n"
                 "- What do the medications suggest about undiagnosed conditions?\n"
                 "- What do the risk factors predispose to?\n"
                 "- Are there conditions DEVELOPING but not yet clinically obvious?\n\n"
                 "List at least 8-10 candidate diagnoses with brief reasoning.\n"
                 "Include both obvious and less obvious possibilities."
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="hypothesis_generation",
                     length=len(hypotheses))

        # ── Call 3: Initial Differential Ranking (always) ──
        logger.info("agent_step", agent_id=self.agent_id, step="initial_ranking")
        current_differential = self._call_llm(llm,
            system="You are a diagnostician ranking a differential diagnosis. "
                   "Use Bayesian reasoning: prior probability × evidence strength.",
            user=f"# Clinical Patterns\n{synthesis}\n\n"
                 f"# Candidate Diagnoses\n{hypotheses}\n\n"
                 "RANK these diagnoses:\n"
                 "1. Map specific evidence from EHR analyst or lab interpreter to each\n"
                 "2. Assign probability estimates (sum to ~1.0)\n"
                 "3. Consider base rates for this demographic\n"
                 "4. Weigh TRENDS more heavily than single values\n"
                 "5. Keep the top 5-8 diagnoses\n\n"
                 "CRITICAL RANKING RULE — Root Cause vs Consequence:\n"
                 "- When an organ is damaged, ask: what CAUSED the damage?\n"
                 "- The underlying cause should rank HIGHER than the organ damage itself\n"
                 "- Medications are strong clues to the root cause — each drug was prescribed for a reason\n"
                 "- Multiple conditions affecting the same organ suggest a systemic disease as the driver\n\n"
                 "For each ranked diagnosis provide:\n"
                 "- Name, probability, confidence (high/moderate/low)\n"
                 "- Supporting evidence with source\n"
                 "- Clinical reasoning chain\n\n"
                 "Also state: what is your confidence in your #1 diagnosis? "
                 "(0-100%, where 80%+ means you are quite sure)"
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="initial_ranking",
                     length=len(current_differential))

        # ── Adaptive Loop: Self-Critique → Confidence Check → Refine ──
        round_num = 0
        while round_num < self.MAX_REASONING_ROUNDS:
            round_num += 1

            # Critique current differential
            logger.info("agent_step", agent_id=self.agent_id,
                        step=f"critique_round_{round_num}")
            critique = self._call_llm(llm,
                system="You are a senior attending physician reviewing a differential diagnosis. "
                       "Look for ANCHORING BIAS, MISSED DIAGNOSES, and PROBABILITY ERRORS.",
                user=f"# Evidence Patterns\n{synthesis}\n\n"
                     f"# Current Differential (round {round_num})\n{current_differential}\n\n"
                     "Critically review:\n"
                     "1. ANCHORING BIAS: Is the diagnostician fixating on the most obvious finding "
                     "while ignoring the ROOT CAUSE?\n"
                     "   - If organ damage is #1, ask: what CAUSED the damage? Rank the cause higher.\n"
                     "   - Check medications: what diseases do they treat? Those diseases should be in the differential.\n"
                     "2. MISSED DIAGNOSES: Given the patient's risk factors (age, gender, comorbidities, "
                     "medications), are common conditions for this demographic MISSING?\n"
                     "   Think broadly — don't limit to obvious organ-specific diagnoses.\n"
                     "3. PROBABILITY CALIBRATION: Are probabilities reasonable for this demographic?\n"
                     "4. EVIDENCE GAPS: What tests would change the ranking?\n\n"
                     "Then answer these two questions:\n"
                     "CONFIDENCE: On a scale of 0-100, how confident are you in this differential? "
                     "(80+ = good enough to stop, <80 = needs more work)\n"
                     "GAPS: What specific clinical questions remain unanswered?\n\n"
                     "If the differential needs changes, provide the CORRECTED ranking.\n"
                     "If it's good enough, say 'DIFFERENTIAL IS ADEQUATE' and state your confidence."
            )
            logger.info("agent_step_done", agent_id=self.agent_id,
                        step=f"critique_round_{round_num}", length=len(critique))

            # Check if confident enough to stop
            critique_lower = critique.lower()
            is_adequate = any(phrase in critique_lower for phrase in [
                "differential is adequate",
                "adequate differential",
                "no further changes",
                "satisfied with",
                "comprehensive enough",
                "well-constructed",
                "no major omissions",
            ])
            # Extract confidence number — handle many formats:
            # "confidence: 85", "Confidence 85%", "85/100", "confidence score of 85"
            confidence = 0
            for pattern in [
                r'confidence[:\s]+(\d+)',
                r'confidence\s+(?:score\s+)?(?:of\s+)?(\d+)',
                r'(\d+)\s*[/%]\s*(?:100|confident)',
                r'(\d+)\s*/\s*100',
                r'confidence.*?(\d{2,3})',
            ]:
                conf_match = re.search(pattern, critique_lower)
                if conf_match:
                    val = int(conf_match.group(1))
                    if 0 <= val <= 100:
                        confidence = val
                        break

            logger.info("agent_confidence_check", agent_id=self.agent_id,
                        round=round_num, confidence=confidence,
                        adequate=is_adequate)

            if is_adequate or confidence >= self.CONFIDENCE_THRESHOLD:
                logger.info("agent_reasoning_complete", agent_id=self.agent_id,
                            rounds=round_num, confidence=confidence,
                            reason="confident_enough")
                current_differential = critique
                break

            if round_num >= self.MAX_REASONING_ROUNDS:
                logger.info("agent_reasoning_complete", agent_id=self.agent_id,
                            rounds=round_num, confidence=confidence,
                            reason="max_rounds_reached")
                current_differential = critique
                break

            # Not confident enough — investigate gaps and refine
            logger.info("agent_step", agent_id=self.agent_id,
                        step=f"refine_round_{round_num}")
            refined = self._call_llm(llm,
                system="You are a diagnostician refining your differential after receiving feedback. "
                       "Address every gap and concern raised.",
                user=f"# Evidence Patterns\n{synthesis}\n\n"
                     f"# Critique and Gaps Identified\n{critique}\n\n"
                     "Address the critique:\n"
                     "1. Add any missing diagnoses that were flagged\n"
                     "2. Recalibrate probabilities based on the feedback\n"
                     "3. Investigate the unanswered clinical questions using the available evidence\n"
                     "4. Provide the UPDATED differential ranking\n\n"
                     "State your updated confidence (0-100) in the revised differential."
            )
            logger.info("agent_step_done", agent_id=self.agent_id,
                        step=f"refine_round_{round_num}", length=len(refined))
            current_differential = refined

        # ── Final Call: Structured JSON Output (always, use json_llm) ──
        logger.info("agent_step", agent_id=self.agent_id, step="final_output")
        jllm = json_llm or llm
        output_schema = DiagnosticOutput.model_json_schema()
        raw_json = self._call_llm(jllm,
            system=self.system_prompt,
            user=f"# Evidence Patterns\n{synthesis}\n\n"
                 f"# Final Differential (after {round_num} critique rounds)\n"
                 f"{current_differential}\n\n"
                 f"Produce the final structured JSON output.\n"
                 f"Include all corrections from the critique rounds.\n"
                 f"Ensure ≥3 diagnoses in the differential.\n"
                 f"Probabilities should approximately sum to 1.0.\n\n"
                 f"## Required Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```\n\n"
                 f"Respond ONLY with valid JSON."
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Produce final JSON"),
        ])
        result = output.model_dump()

        # Auto-fill primary_diagnosis from differential if LLM left it empty
        if not result.get("primary_diagnosis") and result.get("differential"):
            top = result["differential"][0]
            result["primary_diagnosis"] = top.get("name", "")
            result["primary_probability"] = top.get("probability", 0.0)

        logger.info("agent_step_done", agent_id=self.agent_id, step="final_output",
                     total_rounds=round_num)

        return result

    def build_user_prompt(self, state: dict) -> str:
        agent_outputs = state.get("agent_outputs", {})
        ehr_out = agent_outputs.get("ehr_analyst", {})
        lab_out = agent_outputs.get("lab_interpreter", {})

        sections = []
        sections.append("# Clinical Evidence for Diagnostic Reasoning\n")

        # ── EHR Analyst Output ──
        sections.append("## 1. EHR Analyst Summary\n")
        if ehr_out:
            sections.append(f"**Chief Complaint:** {ehr_out.get('chief_complaint', 'Not available')}\n")
            sections.append(f"**History of Present Illness:**\n{ehr_out.get('history_of_present_illness', 'Not available')}\n")

            problems = ehr_out.get("active_problems", [])
            if problems:
                sections.append(f"**Active Problems ({len(problems)}):**")
                for p in problems:
                    if isinstance(p, dict):
                        sections.append(
                            f"- [{p.get('clinical_significance', '?')}] "
                            f"{p.get('name', '?')} "
                            f"(SNOMED: {p.get('snomed_code', '?')}, onset: {p.get('onset_date', '?')})"
                        )
                sections.append("")

            sections.append(f"**Past Medical History:**\n{ehr_out.get('past_medical_history', 'Not available')}\n")

            meds = ehr_out.get("active_medications", [])
            if meds:
                sections.append(f"**Active Medications ({len(meds)}):**")
                for m in meds:
                    if isinstance(m, dict):
                        sections.append(f"- {m.get('name', '?')} — {m.get('purpose', '?')} ({m.get('relevance', '?')})")
                sections.append("")

            sections.append(f"**Risk Factor Summary:**\n{ehr_out.get('risk_factor_summary', 'Not available')}\n")
            sections.append(f"**Clinical Impression:**\n{ehr_out.get('clinical_impression', 'Not available')}\n")

            dq_flags = ehr_out.get("data_quality_flags", [])
            if dq_flags:
                sections.append("**Data Quality Flags:**")
                for f in dq_flags:
                    if isinstance(f, dict):
                        sections.append(f"- {f.get('field', '?')}: {f.get('issue', '?')}")
                sections.append("")
        else:
            sections.append("*EHR Analyst output not available (agent failed)*\n")

        # ── Lab Interpreter Output ──
        sections.append("## 2. Lab Interpreter Findings\n")
        if lab_out:
            findings = lab_out.get("findings", [])
            if findings:
                sections.append(f"**Lab Findings ({len(findings)}, ranked by severity):**")
                for f in findings:
                    if isinstance(f, dict):
                        sections.append(
                            f"- [severity {f.get('severity', '?')}] "
                            f"{f.get('test_name', '?')}: {f.get('value', '?')} "
                            f"({f.get('classification', '?')}, trend: {f.get('trend', '?')})"
                        )
                        sections.append(f"  Note: {f.get('clinical_note', '')}"[:120])
                        if f.get("panel_context"):
                            sections.append(f"  Panel: {f.get('panel_context', '')}"[:120])
                sections.append("")

            alerts = lab_out.get("critical_alerts", [])
            if alerts:
                sections.append("**CRITICAL ALERTS:**")
                for a in alerts:
                    sections.append(f"  !! {a}")
                sections.append("")

            panels = lab_out.get("panel_patterns", [])
            if panels:
                sections.append(f"**Panel Patterns ({len(panels)}):**")
                for p in panels:
                    if isinstance(p, dict):
                        sections.append(f"- {p.get('panel_name', '?')}: {p.get('interpretation', '?')}"[:150])
                sections.append("")

            trending = lab_out.get("trending_concerns", [])
            if trending:
                sections.append("**Trending Concerns:**")
                for t in trending:
                    sections.append(f"  ↗ {t}"[:100])
                sections.append("")

            sections.append(f"**Overall Lab Assessment:**\n{lab_out.get('overall_assessment', 'Not available')}\n")

            gaps = lab_out.get("data_gaps", [])
            if gaps:
                sections.append("**Missing Labs:**")
                for g in gaps:
                    sections.append(f"- {g}"[:80])
                sections.append("")
        else:
            sections.append("*Lab Interpreter output not available (agent failed)*\n")

        # ── Risk Scores and Comorbidity from EHR Analyst output ──
        sections.append("## 3. Risk Factors and Clinical Context\n")
        if ehr_out:
            if ehr_out.get("risk_factor_summary"):
                sections.append(f"**Risk Factors:** {ehr_out['risk_factor_summary']}\n")
            if ehr_out.get("clinical_impression"):
                sections.append(f"**Clinical Impression:** {ehr_out['clinical_impression']}\n")
            if ehr_out.get("data_quality_flags"):
                sections.append("**Data Quality Issues:**")
                for f in ehr_out["data_quality_flags"]:
                    if isinstance(f, dict):
                        sections.append(f"- {f.get('field','?')}: {f.get('issue','?')}")
                sections.append("")

        # Output schema
        output_schema = DiagnosticOutput.model_json_schema()
        sections.append(f"## Required Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```")

        return "\n".join(sections)


# LangGraph node function
diagnostic_reasoning_agent = DiagnosticReasoningAgent()
