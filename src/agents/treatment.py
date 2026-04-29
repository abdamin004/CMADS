"""Treatment Planning Agent — Proposes treatment based on NICE guidelines.

Reads: agent_outputs.final_diagnosis, agent_outputs.evaluation,
       patient_context (medications, conditions, allergies),
       NICE guideline JSON for the matched disease (via Qdrant)
Writes: agent_outputs.treatment_planning

Uses the NICE clinical guideline as a rule-based context to propose
medications, check interactions/contraindications, and create a monitoring plan.
"""

import json
import structlog
from src.agents.base import BaseAgent, SkipAgentException
from src.memory import EpisodicMemory
from src.schemas.treatment import TreatmentOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()


class TreatmentPlanningAgent(BaseAgent):
    agent_id = "treatment_planning"
    output_schema = TreatmentOutput
    temperature = 0.2
    max_tokens = 8192

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Two-call treatment planning:
        1. Check evaluation from shared memory — skip if not DIRECT
        2. Search Qdrant for NICE guidelines
        3. Call 1: Analyse patient context against guideline (free text)
        4. Call 2: Produce structured treatment plan (JSON)
        """
        agent_outputs = state.get("agent_outputs", {})
        ctx = state.get("patient_context", {})
        ehr_case = ctx.get("ehr_case", {})
        patient_uuid = ehr_case.get("patient_uuid", "")

        # Check evaluation result from shared memory (not disk)
        eval_result = agent_outputs.get("evaluation", {})
        match_type = eval_result.get("match_type", "MISS")

        if match_type != "DIRECT":
            logger.info("treatment_skipped",
                        reason=f"Not a DIRECT match ({match_type})",
                        patient=patient_uuid[:12])
            raise SkipAgentException({
                "primary_diagnosis_treated": "SKIPPED — not a DIRECT match",
                "treatment_summary": f"Treatment not generated. Evaluation result: {match_type} "
                                     f"(only DIRECT matches receive treatment plans).",
            })

        primary = eval_result.get("matched_diagnosis", "Unknown")
        logger.info("treatment_for_direct_match", disease=primary,
                     rank=eval_result.get("rank"))

        # Search Qdrant for top 3 matching NICE guidelines
        from src.vectordb.query_guidelines import search_guidelines
        guideline_results = search_guidelines(primary, top_k=3)

        if not guideline_results:
            logger.error("treatment_no_guideline", disease=primary,
                         patient=patient_uuid[:12])
            raise SkipAgentException({
                "primary_diagnosis_treated": primary,
                "treatment_summary": f"ERROR: No NICE guideline found for "
                                     f"'{primary}' in vector database.",
            })

        logger.info("treatment_qdrant_search",
                     disease=primary,
                     top_match=guideline_results[0]["disease_name"],
                     score=guideline_results[0]["score"],
                     matches=len(guideline_results))

        # Build prompt and extract contraindications
        prompt_data = self._build_prompt(state, primary, guideline_results)
        contra_list = self._extract_contraindications(guideline_results)

        # ── Semantic memory (Tier 3): how has this disease played out before? ──
        # Doesn't change the treatment plan directly — but adding the prior
        # observation count and rank-1 frequency to the prompt lets the LLM
        # calibrate its confidence (e.g. "we've seen this disease N times,
        # rank-1 rate is X%, so the diagnosis is likely robust").
        if self._memory_enabled():
            mm = self.memory(state)
            semantic_summary = mm.semantic.summarize_for_diseases([primary])
            prompt_data = (
                f"## CROSS-SESSION CONTEXT (Tier-3 semantic memory)\n"
                f"{semantic_summary}\n\n"
                f"{prompt_data}"
            )

        # ── Call 1: Analyse and plan ──
        logger.info("agent_step", agent_id=self.agent_id, step="analysis")
        analysis = self._call_llm(llm,
            system=self._get_call_prompt("analysis", "system",
                fallback="You are a clinical pharmacist reviewing a patient case "
                         "against NICE guidelines."),
            user=self._get_call_prompt("analysis", "user",
                fallback=f"{prompt_data}\n{contra_list}",
                prompt_data=prompt_data, contra_list=contra_list),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="analysis",
                     length=len(analysis))

        # ── Call 2: Structured JSON output ──
        logger.info("agent_step", agent_id=self.agent_id, step="structure")
        jllm = json_llm or llm
        output_schema = json.dumps(TreatmentOutput.model_json_schema(), indent=2)
        raw_json = self._call_llm(jllm,
            system=self._get_call_prompt("structure", "system",
                fallback=self.system_prompt),
            user=self._get_call_prompt("structure", "user",
                fallback=f"{analysis}\n{prompt_data}",
                analysis=analysis, prompt_data=prompt_data,
                output_schema=output_schema),
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Produce treatment JSON"),
        ])
        logger.info("agent_step_done", agent_id=self.agent_id, step="structure")

        result = output.model_dump()
        if self._memory_enabled():
            self._pending_memory_events.append(EpisodicMemory.write(
                event_type="decision",
                agent_id=self.agent_id,
                summary=(
                    f"Treatment plan generated for '{primary}' "
                    f"({len(result.get('medications') or [])} meds)"
                ),
                payload={"disease": primary},
                tags=["treatment", "plan"],
            ))

        return result

    @staticmethod
    def _extract_contraindications(guideline_results: list[dict]) -> str:
        """Extract contraindicated drugs from all matched guidelines."""
        all_contras = []
        for gr in guideline_results:
            gl = gr["guideline"]
            for c in gl.get("contraindicated_drugs", []):
                if isinstance(c, dict):
                    all_contras.append(
                        f"  - {c.get('drug', '?')}: {c.get('reason', '?')}")
        if all_contras:
            return ("\n\nCONTRAINDICATED DRUGS FROM NICE GUIDELINES "
                    "(MUST CHECK):\n" + "\n".join(all_contras))
        return ""

    @staticmethod
    def _build_prompt(state: dict, primary: str,
                      guideline_results: list[dict]) -> str:
        """Build the treatment prompt from state data and guidelines."""
        agent_outputs = state.get("agent_outputs", {})

        differential = (
            agent_outputs.get("final_diagnosis", {}) or
            agent_outputs.get("diagnostic_reasoning", {})
        ).get("differential", [])

        sections = []

        # ── NICE Guidelines from Qdrant (top 3 matches) ──
        sections.append(
            "# NICE CLINICAL GUIDELINES (top 3 matches from vector search)\n")
        for i, gr in enumerate(guideline_results):
            gl = gr["guideline"]
            sections.append(
                f"## Match {i+1} (score={gr['score']:.3f}): "
                f"{gr['disease_name']}")
            sections.append(
                f"Guideline: {gr['nice_guideline']} — {gr['nice_title']}")
            sections.append(f"Source: {gr['source']}")
            sections.append(
                f"\n{json.dumps(gl, indent=2, default=str)}")
            sections.append("")

        # ── Diagnosis ──
        sections.append("# DIAGNOSIS TO TREAT\n")
        sections.append(f"Primary: {primary}")
        if differential:
            sections.append("Full differential:")
            for dx in differential[:5]:
                if isinstance(dx, dict):
                    sections.append(
                        f"  #{dx.get('rank','?')} {dx.get('name','?')} "
                        f"(P={dx.get('probability','?')})")
        sections.append("")

        # ── Patient Context (from agent outputs) ──
        sections.append(
            "# PATIENT CONTEXT (collected by upstream agents)\n")

        # From EHR Analyst output
        ehr_out = agent_outputs.get("ehr_analyst", {})
        if ehr_out:
            sections.append(
                f"**Clinical Impression:** "
                f"{ehr_out.get('clinical_impression', 'Not available')}")
            sections.append(
                f"**Risk Factors:** "
                f"{ehr_out.get('risk_factor_summary', 'Not available')}")

            # Medications from EHR Analyst
            agent_meds = ehr_out.get("active_medications", [])
            sections.append(f"\n## Current Medications ({len(agent_meds)})")
            if agent_meds:
                for m in agent_meds:
                    if isinstance(m, dict):
                        sections.append(
                            f"- {m.get('name', '?')} "
                            f"(purpose: {m.get('purpose', '?')}, "
                            f"relevance: {m.get('relevance', '?')})")
            else:
                sections.append("None reported by EHR Analyst")

            # Conditions from EHR Analyst
            agent_problems = ehr_out.get("active_problems", [])
            sections.append(
                f"\n## Active Problems ({len(agent_problems)})")
            for p in agent_problems[:15]:
                if isinstance(p, dict):
                    sections.append(
                        f"- [{p.get('clinical_significance', '?')}] "
                        f"{p.get('name', '?')}")
        else:
            sections.append("*EHR Analyst output not available*")

        # From Lab Interpreter output — key values for dosing
        lab_out = agent_outputs.get("lab_interpreter", {})
        if lab_out:
            sections.append(
                f"\n## Key Lab Findings (from Lab Interpreter)")
            for f in lab_out.get("findings", [])[:10]:
                if isinstance(f, dict) and f.get("severity", 0) >= 3:
                    sections.append(
                        f"- [sev {f.get('severity')}] "
                        f"{f.get('test_name', '?')}: {f.get('value', '?')} "
                        f"({f.get('classification', '?')})")
            sections.append(
                f"\n**Lab Assessment:** "
                f"{lab_out.get('overall_assessment', 'Not available')[:200]}")
        else:
            sections.append("\n*Lab Interpreter output not available*")

        # Critical alerts from Lab Interpreter
        if lab_out and lab_out.get("critical_alerts"):
            sections.append(
                f"\n## Critical Alerts (from Lab Interpreter)")
            for a in lab_out["critical_alerts"]:
                sections.append(f"- !! {a}")

        return "\n".join(sections)

    def build_user_prompt(self, state: dict) -> str:
        """Not used — treatment agent overrides run_reasoning directly."""
        raise NotImplementedError(
            "Treatment agent uses run_reasoning directly")


# LangGraph node function
treatment_planning_agent = TreatmentPlanningAgent()
