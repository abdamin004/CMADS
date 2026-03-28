"""Treatment Planning Agent — Proposes treatment based on NICE guidelines.

Reads: agent_outputs.final_diagnosis, patient_context (medications, conditions, allergies),
       NICE guideline JSON for the matched disease
Writes: agent_outputs.treatment_planning

Uses the NICE clinical guideline as a rule-based context to propose
medications, check interactions/contraindications, and create a monitoring plan.
"""

import json
import structlog
from pathlib import Path
from src.agents.base import BaseAgent
from src.schemas.treatment import TreatmentOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

from src.config import cfg

GUIDELINES_DIR = cfg.GUIDELINES_DIR
GUIDELINE_INDEX = GUIDELINES_DIR / "guideline_index.json"

SYSTEM_PROMPT = """You are the Treatment Planning Agent in a multi-agent clinical decision pipeline.

You receive:
1. The patient's diagnosed disease (from the Diagnostic Agent)
2. The NICE clinical guideline for that disease (evidence-based treatment rules)
3. The patient's current medications, conditions, and lab results

Your job is to produce a SPECIFIC treatment plan for THIS patient by applying the NICE guideline to their individual circumstances.

## Rules
1. FOLLOW THE NICE GUIDELINE — it is your primary reference. Cite it in your justifications.
2. Choose SPECIFIC drugs and doses, not just drug classes.
3. Check every proposed drug against the patient's CURRENT medications for interactions.
4. Check every proposed drug against the patient's CONDITIONS for contraindications.
5. If the patient already takes a guideline-recommended drug, note it as "already prescribed."
6. Adapt to the patient: age, renal function (eGFR), comorbidities, and current drugs matter.
7. Include monitoring plan per the guideline.
8. Include non-pharmacological interventions.

## Important
- If eGFR < 30: flag metformin, NSAID, and dose-adjusted drugs.
- If patient has heart failure: avoid verapamil, diltiazem, pioglitazone, NSAIDs.
- If patient is on ACE-I: do NOT add ARB (no dual RAAS blockade).
- If patient is elderly/frail: consider lower starting doses.
- Each medication must have a purpose and NICE justification.

## Duration Rules — DO NOT default to "Ongoing"
- Use the NICE guideline duration if specified (e.g., "Clopidogrel: 12 months post-ACS")
- For titration drugs: specify the titration period (e.g., "Start 2.5mg, titrate to 10mg over 4-6 weeks, then ongoing")
- For acute drugs: specify exact duration (e.g., "Antibiotics: 7 days")
- For chronic drugs: say "Lifelong — review annually" not just "Ongoing"
- For goal-directed drugs: specify the target (e.g., "Until ferritin >200, then review")
- For monitoring-dependent drugs: specify review points (e.g., "6 months, reassess based on LVEF response")

## Output Format
Respond ONLY with valid JSON matching the required schema. No preamble or explanation."""


def load_guideline(disease_name):
    """Load the NICE guideline JSON for a disease."""
    if not GUIDELINE_INDEX.exists():
        return None

    index = json.loads(GUIDELINE_INDEX.read_text())
    mappings = index.get("mappings", {})

    # Direct match
    if disease_name in mappings:
        guideline_file = GUIDELINES_DIR / mappings[disease_name]
        if guideline_file.exists():
            return json.loads(guideline_file.read_text())

    # Fuzzy match — check if disease name contains a key
    disease_lower = disease_name.lower()
    for key, filename in mappings.items():
        if any(word in disease_lower for word in key.lower().split() if len(word) > 4):
            guideline_file = GUIDELINES_DIR / filename
            if guideline_file.exists():
                return json.loads(guideline_file.read_text())

    return None


class TreatmentPlanningAgent(BaseAgent):
    agent_id = "treatment_planning"
    system_prompt = SYSTEM_PROMPT
    output_schema = TreatmentOutput
    temperature = 0.2
    max_tokens = 8192

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Two-call treatment planning:
        Call 1: Analyse patient context against NICE guideline (free text)
        Call 2: Produce structured treatment plan (JSON)
        """
        prompt_data = self.build_user_prompt(state)

        # build_user_prompt returns a dict (not str) when skipping non-DIRECT matches
        if isinstance(prompt_data, dict):
            return prompt_data

        # Extract contraindicated drugs from all matched guidelines
        contra_list = ""
        all_contras = []
        guideline_results = getattr(self, '_guideline_results', [])
        for gr in guideline_results:
            gl = gr["guideline"]
            for c in gl.get("contraindicated_drugs", []):
                if isinstance(c, dict):
                    all_contras.append(f"  - {c.get('drug', '?')}: {c.get('reason', '?')}")
        if all_contras:
            contra_list = "\n\nCONTRAINDICATED DRUGS FROM NICE GUIDELINES (MUST CHECK):\n" + "\n".join(all_contras)

        # ── Call 1: Analyse and plan ──
        logger.info("agent_step", agent_id=self.agent_id, step="analysis")
        analysis = self._call_llm(llm,
            system=self._get_call_prompt("analysis", "system",
                fallback="You are a clinical pharmacist reviewing a patient case against NICE guidelines."),
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

        return output.model_dump()

    def build_user_prompt(self, state: dict) -> str | dict:
        agent_outputs = state.get("agent_outputs", {})

        # Get patient UUID from EHR analyst output or patient context
        ehr_out = agent_outputs.get("ehr_analyst", {})
        ctx = state.get("patient_context", {})
        ehr_case = ctx.get("ehr_case", {})
        patient_uuid = ehr_case.get("patient_uuid", "")
        eval_path = cfg.MAS_RESULTS_DIR / patient_uuid / "evaluation.json"

        if eval_path.exists():
            ev = json.loads(eval_path.read_text())
            if ev.get("match_type") != "DIRECT":
                logger.info("treatment_skipped", reason=f"Not a DIRECT match ({ev.get('match_type')})",
                            patient=patient_uuid[:12])
                return {
                    "primary_diagnosis_treated": "SKIPPED — not a DIRECT match",
                    "treatment_summary": f"Treatment not generated. Evaluation result: {ev.get('match_type')} "
                                         f"(only DIRECT matches receive treatment plans).",
                }
            # Use the matched diagnosis from the LLM judge
            primary = ev.get("matched_diagnosis", "Unknown")
            logger.info("treatment_for_direct_match", disease=primary, rank=ev.get("rank"))
        else:
            # No evaluation yet — use primary diagnosis from MAS
            final = agent_outputs.get("final_diagnosis", {}) or agent_outputs.get("diagnostic_reasoning", {})
            primary = final.get("primary_diagnosis", "Unknown")
            logger.info("treatment_no_evaluation", disease=primary)

        differential = (agent_outputs.get("final_diagnosis", {}) or
                        agent_outputs.get("diagnostic_reasoning", {})).get("differential", [])

        # Search Qdrant for top 3 matching NICE guidelines
        from src.vectordb.query_guidelines import search_guidelines
        guideline_results = search_guidelines(primary, top_k=3)
        self._guideline_results = guideline_results  # Store for run_reasoning

        if not guideline_results:
            logger.error("treatment_no_guideline", disease=primary, patient=patient_uuid[:12])
            return {
                "primary_diagnosis_treated": primary,
                "treatment_summary": f"ERROR: No NICE guideline found for '{primary}' in vector database.",
            }

        # Use the top match as primary guideline
        guideline = guideline_results[0]["guideline"]
        logger.info("treatment_qdrant_search",
                     disease=primary,
                     top_match=guideline_results[0]["disease_name"],
                     score=guideline_results[0]["score"],
                     matches=len(guideline_results))

        sections = []

        # ── NICE Guidelines from Qdrant (top 3 matches) ──
        sections.append("# NICE CLINICAL GUIDELINES (top 3 matches from vector search)\n")
        for i, gr in enumerate(guideline_results):
            gl = gr["guideline"]
            sections.append(f"## Match {i+1} (score={gr['score']:.3f}): {gr['disease_name']}")
            sections.append(f"Guideline: {gr['nice_guideline']} — {gr['nice_title']}")
            sections.append(f"Source: {gr['source']}")
            sections.append(f"\n{json.dumps(gl, indent=2, default=str)}")
            sections.append("")

        # ── Diagnosis ──
        sections.append("# DIAGNOSIS TO TREAT\n")
        sections.append(f"Primary: {primary}")
        if differential:
            sections.append("Full differential:")
            for dx in differential[:5]:
                if isinstance(dx, dict):
                    sections.append(f"  #{dx.get('rank','?')} {dx.get('name','?')} (P={dx.get('probability','?')})")
        sections.append("")

        # ── Patient Context (from agent outputs, not raw data) ──
        sections.append("# PATIENT CONTEXT (collected by upstream agents)\n")

        # From EHR Analyst output
        ehr_out = agent_outputs.get("ehr_analyst", {})
        if ehr_out:
            sections.append(f"**Clinical Impression:** {ehr_out.get('clinical_impression', 'Not available')}")
            sections.append(f"**Risk Factors:** {ehr_out.get('risk_factor_summary', 'Not available')}")

            # Medications from EHR Analyst
            agent_meds = ehr_out.get("active_medications", [])
            sections.append(f"\n## Current Medications ({len(agent_meds)})")
            if agent_meds:
                for m in agent_meds:
                    if isinstance(m, dict):
                        sections.append(f"- {m.get('name', '?')} (purpose: {m.get('purpose', '?')}, relevance: {m.get('relevance', '?')})")
            else:
                sections.append("None reported by EHR Analyst")

            # Conditions from EHR Analyst
            agent_problems = ehr_out.get("active_problems", [])
            sections.append(f"\n## Active Problems ({len(agent_problems)})")
            for p in agent_problems[:15]:
                if isinstance(p, dict):
                    sections.append(f"- [{p.get('clinical_significance', '?')}] {p.get('name', '?')}")
        else:
            sections.append("*EHR Analyst output not available*")

        # From Lab Interpreter output — key values for dosing
        lab_out = agent_outputs.get("lab_interpreter", {})
        if lab_out:
            sections.append(f"\n## Key Lab Findings (from Lab Interpreter)")
            for f in lab_out.get("findings", [])[:10]:
                if isinstance(f, dict) and f.get("severity", 0) >= 3:
                    sections.append(f"- [sev {f.get('severity')}] {f.get('test_name', '?')}: {f.get('value', '?')} ({f.get('classification', '?')})")
            sections.append(f"\n**Lab Assessment:** {lab_out.get('overall_assessment', 'Not available')[:200]}")
        else:
            sections.append("\n*Lab Interpreter output not available*")

        # Critical alerts from Lab Interpreter
        if lab_out and lab_out.get("critical_alerts"):
            sections.append(f"\n## Critical Alerts (from Lab Interpreter)")
            for a in lab_out["critical_alerts"]:
                sections.append(f"- !! {a}")

        return "\n".join(sections)


# LangGraph node function
treatment_planning_agent = TreatmentPlanningAgent()
