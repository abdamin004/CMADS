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
from src.memory import EpisodicMemory
from src.schemas.diagnostic import DiagnosticOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()


class DiagnosticReasoningAgent(BaseAgent):
    agent_id = "diagnostic_reasoning"
    output_schema = DiagnosticOutput
    temperature = 0.3
    max_tokens = 8192

    @property
    def MAX_REASONING_ROUNDS(self):
        from src.config import cfg
        return cfg.DIAGNOSTIC_MAX_ROUNDS

    @property
    def CONFIDENCE_THRESHOLD(self):
        from src.config import cfg
        return cfg.DIAGNOSTIC_CONFIDENCE_THRESHOLD

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

        Multi-level memory hooks:
          - Working memory: confidence trajectory + critique trail across rounds
            (lets later rounds and downstream agents see what changed when)
          - Episodic memory: a SessionEvent per critique/confidence-check/refine
            so Reviewer + Refiner can read the reasoning chain, not just the
            final differential
          - Semantic memory: read-only — pulled into the prompt during the
            initial-ranking call as a Bayesian prior across past runs
        """
        evidence = self.build_user_prompt(state)
        mm = self.memory(state) if self._memory_enabled() else None

        # ── Call 1: Evidence Synthesis (always) ──
        logger.info("agent_step", agent_id=self.agent_id, step="evidence_synthesis")
        synthesis = self._call_llm(llm,
            system=self._get_call_prompt("evidence_synthesis", "system",
                fallback="You are a senior diagnostician synthesising clinical evidence. Do NOT diagnose yet."),
            user=self._get_call_prompt("evidence_synthesis", "user",
                fallback=evidence, patient_data=evidence),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="evidence_synthesis",
                     length=len(synthesis))

        # ── Call 2: Broad Hypothesis Generation (always) ──
        logger.info("agent_step", agent_id=self.agent_id, step="hypothesis_generation")
        hypotheses = self._call_llm(llm,
            system=self._get_call_prompt("hypothesis_generation", "system",
                fallback="You are a diagnostician generating hypotheses. Think broadly."),
            user=self._get_call_prompt("hypothesis_generation", "user",
                fallback=synthesis, synthesis=synthesis),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="hypothesis_generation",
                     length=len(hypotheses))

        # ── Call 3: Initial Differential Ranking (always) ──
        logger.info("agent_step", agent_id=self.agent_id, step="initial_ranking")
        current_differential = self._call_llm(llm,
            system=self._get_call_prompt("initial_ranking", "system",
                fallback="You are a diagnostician ranking a differential diagnosis."),
            user=self._get_call_prompt("initial_ranking", "user",
                fallback=f"{synthesis}\n{hypotheses}",
                synthesis=synthesis, hypotheses=hypotheses),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="initial_ranking",
                     length=len(current_differential))

        # ── Adaptive Loop: Self-Critique → Confidence Check → Refine ──
        round_num = 0
        confidence_trajectory: list[int] = []
        while round_num < self.MAX_REASONING_ROUNDS:
            round_num += 1

            # Critique current differential
            logger.info("agent_step", agent_id=self.agent_id,
                        step=f"critique_round_{round_num}")
            critique = self._call_llm(llm,
                system=self._get_call_prompt("critique", "system",
                    fallback="You are a senior attending physician reviewing a differential diagnosis."),
                user=self._get_call_prompt("critique", "user",
                    fallback=f"{synthesis}\n{current_differential}",
                    synthesis=synthesis, current_differential=current_differential,
                    round_num=str(round_num)),
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

            confidence_trajectory.append(confidence)
            if mm is not None:
                mm.working.put("confidence_trajectory", confidence_trajectory)
                mm.working.append_to("critique_trail", {
                    "round": round_num,
                    "confidence": confidence,
                    "adequate": is_adequate,
                    "snippet": critique[:240],
                })
                self._pending_memory_events.append(EpisodicMemory.write(
                    event_type="critique",
                    agent_id=self.agent_id,
                    summary=(
                        f"Round {round_num} critique: confidence={confidence}, "
                        f"adequate={is_adequate}"
                    ),
                    payload={
                        "round": round_num,
                        "confidence": confidence,
                        "adequate": is_adequate,
                    },
                    tags=["diagnostic", "critique"],
                ))
                self._pending_memory_events.append(EpisodicMemory.write(
                    event_type="confidence_check",
                    agent_id=self.agent_id,
                    summary=f"Round {round_num} confidence={confidence}/100",
                    payload={"round": round_num, "confidence": confidence},
                    tags=["diagnostic", "confidence"],
                ))

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
                system=self._get_call_prompt("refine", "system",
                    fallback="You are a diagnostician refining your differential after receiving feedback."),
                user=self._get_call_prompt("refine", "user",
                    fallback=f"{synthesis}\n{critique}",
                    synthesis=synthesis, critique=critique),
            )
            logger.info("agent_step_done", agent_id=self.agent_id,
                        step=f"refine_round_{round_num}", length=len(refined))
            current_differential = refined

        # ── Final Call: Structured JSON Output (always, use json_llm) ──
        logger.info("agent_step", agent_id=self.agent_id, step="final_output")
        jllm = json_llm or llm
        output_schema = json.dumps(DiagnosticOutput.model_json_schema(), indent=2)
        raw_json = self._call_llm(jllm,
            system=self._get_call_prompt("final_output", "system",
                fallback=self.system_prompt),
            user=self._get_call_prompt("final_output", "user",
                fallback=f"{synthesis}\n{current_differential}",
                synthesis=synthesis, current_differential=current_differential,
                round_num=str(round_num), output_schema=output_schema),
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Produce final JSON"),
        ])
        result = output.model_dump()
        self._autofill_primary_diagnosis(result)

        logger.info("agent_step_done", agent_id=self.agent_id, step="final_output",
                     total_rounds=round_num)

        if mm is not None:
            mm.working.put("rounds_completed", round_num)
            mm.working.put("final_primary", result.get("primary_diagnosis"))
            self._pending_memory_events.append(EpisodicMemory.write(
                event_type="decision",
                agent_id=self.agent_id,
                summary=(
                    f"Final differential ({len(result.get('differential') or [])} dx, "
                    f"primary={result.get('primary_diagnosis', '?')[:60]}, "
                    f"rounds={round_num})"
                ),
                payload={
                    "rounds": round_num,
                    "primary_diagnosis": result.get("primary_diagnosis"),
                    "primary_probability": result.get("primary_probability"),
                    "confidence_trajectory": confidence_trajectory,
                },
                tags=["diagnostic", "final"],
            ))

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
