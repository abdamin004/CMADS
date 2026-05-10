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

    # When True, build_user_prompt skips the legacy "## 0. SIMILAR PAST
    # PATIENTS" block — the 3-phase reasoning in run_reasoning() injects
    # the prior at a controlled point, so we don't want it duplicated
    # inside the evidence prompt itself. Toggled per invocation.
    _suppress_prior_in_prompt: bool = False

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
        # Decide whether to use 3-phase reasoning. We do so when
        # memory is on AND we have at least one high-quality prior
        # (DIRECT-match past case above the similarity threshold).
        # Otherwise we fall back to the original adaptive critique loop.
        agent_outputs = state.get("agent_outputs", {}) or {}
        ehr_out_pre = agent_outputs.get("ehr_analyst", {})
        lab_out_pre = agent_outputs.get("lab_interpreter", {})
        quality_priors: list[dict] = []
        if self._memory_enabled():
            quality_priors = self._get_quality_priors(
                state, ehr_out_pre, lab_out_pre,
            )
        use_3phase = bool(quality_priors)

        # When 3-phase is on we inject the prior ourselves at Round A,
        # so suppress the duplicate block in build_user_prompt.
        self._suppress_prior_in_prompt = use_3phase
        try:
            evidence = self.build_user_prompt(state)
        finally:
            self._suppress_prior_in_prompt = False

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

        # ── Branch: 3-phase reasoning when quality priors exist ──
        round_num = 0
        confidence_trajectory: list[int] = []
        if use_3phase:
            from src.memory import CaseBasedMemory
            prior_block = CaseBasedMemory.summarize_for_prompt(quality_priors, max_lines=5)
            current_differential = self._run_three_phase(
                llm,
                evidence=evidence,
                synthesis=synthesis,
                hypotheses=hypotheses,
                initial_differential=current_differential,
                prior_block=prior_block,
                quality_priors=quality_priors,
                mm=mm,
            )
            round_num = 3  # for the trace
        else:
            current_differential, round_num, confidence_trajectory = (
                self._run_critique_loop(
                    llm, evidence, synthesis, hypotheses,
                    current_differential, mm,
                )
            )

        # ── Final Call: Structured JSON Output (always, use json_llm) ──
        return self._finalize_json(
            llm, json_llm, evidence, synthesis, current_differential,
            round_num, confidence_trajectory, mm,
        )

    # ── Helper: original adaptive critique loop ──────────────────────
    def _run_critique_loop(
        self, llm, evidence, synthesis, hypotheses,
        current_differential, mm,
    ):
        """The original adaptive critique loop, now extracted so the
        3-phase path can branch around it. Behaviour is unchanged from
        the pre-3-phase implementation."""
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

        return current_differential, round_num, confidence_trajectory

    # ── Helper: 3-phase reasoning (with-prior / clean / synthesise) ──
    def _run_three_phase(
        self, llm,
        evidence: str,
        synthesis: str,
        hypotheses: str,
        initial_differential: str,
        prior_block: str,
        quality_priors: list[dict],
        mm,
    ) -> str:
        """Three explicit rounds replacing the adaptive critique loop
        when high-quality case-based priors are available.

        Round A re-ranks WITH the case-based prior visible.
        Round B re-ranks WITHOUT the prior, with an explicit
        anti-anchoring instruction.
        Round C synthesises A and B into a final differential, prefer
        the consensus where they agree and Round B's clean-room
        reasoning where they disagree.

        Each round writes a Tier-2 episodic event so the Reviewer +
        Refiner can audit which path produced the final differential.
        """
        # ── Round A: WITH prior ──
        logger.info("agent_step", agent_id=self.agent_id, step="round_a_with_prior")
        round_a = self._call_llm(llm,
            system=(
                "You are a diagnostician producing a ranked differential. "
                "You are given the patient's evidence AND a Bayesian-style "
                "prior of similar past patients with their confirmed "
                "diagnoses. Use the prior to weight your hypotheses, but "
                "anchor every diagnosis to evidence in this patient's "
                "data — do not invoke a prior diagnosis without supporting "
                "evidence in the current case."
            ),
            user=(
                f"# Patient evidence\n{evidence}\n\n"
                f"# Hypotheses considered\n{hypotheses}\n\n"
                f"# Prior — similar past patients (Tier-4 case-based memory)\n"
                f"{prior_block}\n\n"
                "# Initial ranking (no prior considered)\n"
                f"{initial_differential}\n\n"
                "Produce your ranked differential. State your confidence "
                "(0–100) in the primary diagnosis."
            ),
            agent_id=self.agent_id,
        )
        logger.info("agent_step_done", agent_id=self.agent_id,
                    step="round_a_with_prior", length=len(round_a))

        # ── Round B: WITHOUT prior, clean-room ──
        logger.info("agent_step", agent_id=self.agent_id, step="round_b_clean_room")
        round_b = self._call_llm(llm,
            system=(
                "You are a diagnostician producing a ranked differential "
                "from this patient's evidence ALONE. IGNORE any prior "
                "cases or external priors — reason from the EHR and lab "
                "data in front of you, as if this were the first patient "
                "you have ever seen. Resist anchoring on common diagnoses "
                "if the evidence does not support them."
            ),
            user=(
                f"# Patient evidence\n{evidence}\n\n"
                f"# Hypotheses considered\n{hypotheses}\n\n"
                "Produce your ranked differential clean-room. State your "
                "confidence (0–100) in the primary diagnosis. Do NOT "
                "consider any prior cases."
            ),
            agent_id=self.agent_id,
        )
        logger.info("agent_step_done", agent_id=self.agent_id,
                    step="round_b_clean_room", length=len(round_b))

        # ── Round C: Synthesise ──
        logger.info("agent_step", agent_id=self.agent_id, step="round_c_synthesise")
        round_c = self._call_llm(llm,
            system=(
                "You are a senior diagnostician synthesising two "
                "differentials produced by a junior under different "
                "instructions. Round A used a Bayesian-style prior of "
                "similar past patients; Round B reasoned clean-room from "
                "the evidence alone. Compare them: where they agree, "
                "output the consensus. Where they disagree, prefer Round "
                "B unless Round A's prior choice has clear, named "
                "supporting evidence in this patient's data. Flag any "
                "diagnosis that appears only because of the prior."
            ),
            user=(
                f"# Patient evidence (anchor every claim here)\n{evidence}\n\n"
                f"# Round A — with case-based prior\n{round_a}\n\n"
                f"# Round B — clean-room (no prior)\n{round_b}\n\n"
                "Produce the final synthesised differential. State your "
                "confidence (0–100). If A and B disagree, briefly note "
                "which you preferred and why."
            ),
            agent_id=self.agent_id,
        )
        logger.info("agent_step_done", agent_id=self.agent_id,
                    step="round_c_synthesise", length=len(round_c))

        # Tier-2 episodic events for the trace
        if mm is not None:
            mm.working.put("three_phase_used", True)
            mm.working.put("priors_count", len(quality_priors))
            for label, payload in [
                ("round_a", {"with_prior": True,
                             "priors_used": len(quality_priors)}),
                ("round_b", {"with_prior": False, "anti_anchoring": True}),
                ("round_c", {"synthesis": True}),
            ]:
                self._pending_memory_events.append(EpisodicMemory.write(
                    event_type="critique",
                    agent_id=self.agent_id,
                    summary=f"3-phase {label}",
                    payload=payload,
                    tags=["diagnostic", "three_phase", label],
                ))

        return round_c

    # ── Helper: structured-JSON finalisation (shared by both paths) ──
    def _finalize_json(
        self, llm, json_llm,
        evidence: str,
        synthesis: str,
        current_differential: str,
        round_num: int,
        confidence_trajectory: list[int],
        mm,
    ) -> dict:
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

    # ── Quality-filtered case-based recall (Tier 4) ─────────────────
    # Used by the 3-phase reasoning in run_reasoning(). Only DIRECT-match
    # past cases above a similarity threshold are returned; INDIRECT and
    # MISS cases are filtered out so the prior cannot reinforce errors.
    def _get_quality_priors(self, state: dict,
                            ehr_out: dict, lab_out: dict,
                            similarity_threshold: float = 0.5,
                            top_k: int = 3) -> list[dict]:
        if not self._memory_enabled():
            return []
        try:
            mm = self.memory(state)
            ctx = state.get("patient_context") or {}
            this_uuid = (ctx.get("ehr_case") or {}).get("patient_uuid")
            # Pull more than we need, then filter — gives stable top-K
            # after the quality cut.
            similar = mm.case_based.recall(
                patient_context=ctx,
                ehr_summary=ehr_out,
                lab_summary=lab_out,
                top_k=top_k * 4,
                exclude_uuid=this_uuid,
            )
        except Exception:  # noqa: BLE001 — never break the prompt
            return []
        return [
            c for c in similar
            if c.get("match_type") == "DIRECT"
            and float(c.get("score", 0)) >= similarity_threshold
        ][:top_k]

    def build_user_prompt(self, state: dict) -> str:
        agent_outputs = state.get("agent_outputs", {})
        ehr_out = agent_outputs.get("ehr_analyst", {})
        lab_out = agent_outputs.get("lab_interpreter", {})

        sections = []
        sections.append("# Clinical Evidence for Diagnostic Reasoning\n")

        # ── 0. Case-based prior (Tier 4: similar past patients) ──
        # Kept for backwards compatibility with the original
        # single-pass reasoning. The 3-phase reasoning in
        # run_reasoning() uses _get_quality_priors() and injects the
        # prior at a controlled point — when memory is on AND quality
        # priors exist we suppress this section to avoid duplication.
        if self._memory_enabled() and not self._suppress_prior_in_prompt:
            try:
                mm = self.memory(state)
                ctx = state.get("patient_context") or {}
                this_uuid = (ctx.get("ehr_case") or {}).get("patient_uuid")
                similar = mm.case_based.recall(
                    patient_context=ctx,
                    ehr_summary=ehr_out,
                    lab_summary=lab_out,
                    top_k=5,
                    exclude_uuid=this_uuid,
                )
            except Exception:  # noqa: BLE001 — never break the prompt
                similar = []
            if similar:
                sections.append(
                    "## 0. SIMILAR PAST PATIENTS — case-based prior "
                    "(Tier 4 memory)\n"
                )
                sections.append(
                    "Past patients whose EHR + lab profile resembles the "
                    "current case, with the diagnosis the pipeline reached "
                    "and how strongly the judge accepted it. Use as a prior, "
                    "not as ground truth — every case is similarity-ranked "
                    "by vector embedding only, not by clinical match.\n"
                )
                from src.memory import CaseBasedMemory
                sections.append(
                    CaseBasedMemory.summarize_for_prompt(similar, max_lines=5)
                )
                sections.append("")

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
