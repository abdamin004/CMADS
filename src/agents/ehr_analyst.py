"""EHR Analyst Agent — Stage 1 (parallel with Lab Interpreter).

Reads: patient_context (ehr_case from Gold layer)
Writes: agent_outputs.ehr_analyst

Extracts a structured clinical summary from the patient's EHR data.
Does NOT diagnose — summarises and structures for downstream agents.

Implements: SDD §5.2, MA-010–013
"""

import json
import structlog
from src.agents.base import BaseAgent
from src.schemas.ehr_analyst import EHRAnalystOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the EHR Analyst Agent in a multi-agent clinical decision pipeline.

Your role is to extract and structure clinical information from the patient's electronic health record. You do NOT diagnose — you produce a comprehensive clinical summary that downstream agents will use for diagnostic reasoning.

## Your Task
1. Identify the chief complaint from visit patterns and active conditions
2. Summarise the history of present illness (recent clinical trajectory)
3. List all active problems ranked by clinical significance
4. Summarise past medical history
5. List current medications with their clinical relevance
6. Summarise risk scores and comorbidity flags
7. Flag any data quality issues (missing fields, outdated data)
8. Provide a brief clinical impression (NOT a diagnosis)

## Critical: Risk Factor Assessment
Assess risk factors across ALL organ systems — do not limit to any specific diseases:
- Identify which organ systems are affected based on conditions, labs, and medications
- Note any medications that suggest conditions not explicitly documented
- Medications are clues: each drug was prescribed for a reason — infer what conditions the patient likely has based on their medication list
- In your risk_factor_summary, state which organ systems are at elevated risk based on the full clinical profile

## Important Rules
- Extract information, do not invent it. Only use data present in the input.
- Rank active problems by clinical significance (most significant first)
- Note any medications that suggest undiagnosed conditions
- Identify patterns across conditions, medications, and risk scores
- Flag missing data that could impact downstream diagnostic reasoning

## Output Format
Respond ONLY with valid JSON matching the required schema. No preamble or explanation."""


class EHRAnalystAgent(BaseAgent):
    agent_id = "ehr_analyst"
    system_prompt = SYSTEM_PROMPT
    output_schema = EHRAnalystOutput
    temperature = 0.1
    max_tokens = 3000

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Multi-call EHR analysis:
        Call 1: Deep analysis — identify patterns, flag concerns, assess data quality
        Call 2: Produce structured JSON output from the analysis
        Call 3: Self-review — check for missed patterns or wrong significance rankings
        """
        patient_data = self.build_user_prompt(state)

        # ── Call 1: Deep analysis ──
        logger.info("agent_step", agent_id=self.agent_id, step="analysis")
        analysis = self._call_llm(llm,
            system="You are a senior clinical analyst reviewing a patient's electronic health record. "
                   "Perform a thorough analysis. Do NOT produce JSON yet.",
            user=f"{patient_data}\n\n"
                 "Analyse this patient's record thoroughly:\n"
                 "1. What are the most significant active conditions and why?\n"
                 "2. What patterns do you see across conditions, medications, and visits?\n"
                 "3. Are any medications unusual or suggestive of undiagnosed conditions?\n"
                 "4. What risk factors stand out (cardiovascular, renal, metabolic, etc.)?\n"
                 "5. What data is missing that could change the clinical picture?\n"
                 "6. What is your overall clinical impression?\n"
                 "Be thorough. Consider every condition, medication, and risk score."
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="analysis",
                     length=len(analysis))

        # ── Call 2: Structured output (use json_llm for guaranteed valid JSON) ──
        logger.info("agent_step", agent_id=self.agent_id, step="structure")
        jllm = json_llm or llm
        output_schema = EHRAnalystOutput.model_json_schema()
        raw_json = self._call_llm(jllm,
            system=self.system_prompt,
            user=f"# Your Previous Analysis\n{analysis}\n\n"
                 f"# Original Patient Data\n{patient_data}\n\n"
                 f"Now convert your analysis into the required JSON format.\n"
                 f"Use your analysis above to fill every field accurately.\n"
                 f"Rank active_problems by clinical significance (most significant first).\n\n"
                 f"## Required Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```\n\n"
                 f"Respond ONLY with valid JSON."
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Convert to JSON"),
        ])
        output_dict = output.model_dump()

        # ── Call 3: Self-review (use json_llm since output is JSON) ──
        logger.info("agent_step", agent_id=self.agent_id, step="review")
        review = self._call_llm(jllm,
            system="You are a quality reviewer checking a clinical EHR summary for completeness and accuracy.",
            user=f"# Original Patient Data\n{patient_data}\n\n"
                 f"# Produced Summary\n{json.dumps(output_dict, indent=2, default=str)}\n\n"
                 "Review this summary against the original data:\n"
                 "1. Are all significant conditions captured with correct significance?\n"
                 "2. Are any important medications missed?\n"
                 "3. Is the clinical impression accurate and complete?\n"
                 "4. Are there risk factors not mentioned?\n"
                 "5. Should any significance rankings be changed?\n\n"
                 "If improvements needed, output the CORRECTED full JSON.\n"
                 "If the summary is good, output it unchanged.\n"
                 "Output ONLY valid JSON."
        )

        # Try to parse the review — if it's improved JSON, use it
        try:
            reviewed = self._parse_output(review)
            logger.info("agent_step_done", agent_id=self.agent_id, step="review",
                         result="updated")
            return reviewed.model_dump()
        except Exception:
            logger.info("agent_step_done", agent_id=self.agent_id, step="review",
                         result="kept_original")
            return output_dict

    def build_user_prompt(self, state: dict) -> str:
        ctx = state.get("patient_context", {})
        ehr = ctx.get("ehr_case", {})

        sections = []
        sections.append("# Patient EHR Data\n")

        # Demographics
        demo = ehr.get("demographics", {})
        if demo:
            sections.append(f"## Demographics\n{json.dumps(demo, indent=2, default=str)}\n")

        # Conditions (Gold structure: dict with 'active' list and 'resolved' list)
        conditions = ehr.get("conditions", {})
        if isinstance(conditions, dict):
            active = conditions.get("active", [])
            resolved = conditions.get("resolved", [])
            if active:
                sections.append(f"## Active Conditions ({len(active)})")
                for c in active:
                    if isinstance(c, dict):
                        name = c.get('condition', c.get('name', 'Unknown'))
                        code = c.get('code', '?')
                        onset = c.get('start_date', '?')
                        sections.append(f"- {name} (SNOMED: {code}, onset: {onset})")
                    else:
                        sections.append(f"- {c}")
                sections.append("")
            if resolved:
                sections.append(f"## Resolved Conditions ({len(resolved)})")
                for c in resolved[:10]:
                    if isinstance(c, dict):
                        name = c.get('condition', c.get('name', 'Unknown'))
                        sections.append(f"- {name} (resolved: {c.get('stop_date', c.get('end_date', '?'))})")
                sections.append("")
        elif isinstance(conditions, list):
            sections.append(f"## Conditions ({len(conditions)})")
            for c in conditions:
                if isinstance(c, dict):
                    sections.append(f"- {c.get('condition', c.get('name', 'Unknown'))}")
                else:
                    sections.append(f"- {c}")
            sections.append("")

        # Medications (Gold structure: dict with 'active' list)
        meds = ehr.get("medications", {})
        if isinstance(meds, dict):
            active_meds = meds.get("active", [])
            if active_meds:
                sections.append(f"## Current Medications ({len(active_meds)})")
                for m in active_meds:
                    if isinstance(m, dict):
                        med_name = m.get('medication', m.get('name', 'Unknown'))
                        med_reason = m.get('condition_treated', m.get('reason', 'unspecified'))
                        sections.append(f"- {med_name} (for: {med_reason})")
                    else:
                        sections.append(f"- {m}")
                sections.append("")
            else:
                sections.append("## Current Medications\nNone documented.\n")
        elif isinstance(meds, list):
            sections.append(f"## Medications ({len(meds)})")
            for m in meds:
                if isinstance(m, dict):
                    sections.append(f"- {m.get('medication', m.get('name', 'Unknown'))}")
                else:
                    sections.append(f"- {m}")
            sections.append("")

        # Risk Scores
        risk = ehr.get("risk_scores", {})
        if risk:
            sections.append(f"## Risk Scores\n{json.dumps(risk, indent=2, default=str)}\n")

        # Comorbidity
        comorbidity = ehr.get("comorbidity", {})
        if comorbidity:
            sections.append(f"## Comorbidity Flags\n{json.dumps(comorbidity, indent=2, default=str)}\n")

        # Visits (Gold structure: dict with counts)
        visits = ehr.get("visits", {})
        if isinstance(visits, dict):
            sections.append(f"## Visit Summary")
            sections.append(f"- Total visits: {visits.get('total', '?')}")
            sections.append(f"- Emergency: {visits.get('emergency', 0)}")
            sections.append(f"- Inpatient: {visits.get('inpatient', 0)}")
            sections.append(f"- Outpatient: {visits.get('outpatient', 0)}")
            sections.append(f"- Wellness: {visits.get('wellness', 0)}")
            if visits.get("first_visit"):
                sections.append(f"- First visit: {visits['first_visit']}")
            if visits.get("last_visit"):
                sections.append(f"- Last visit: {visits['last_visit']}")
            sections.append("")

        # Imaging studies
        imaging = ehr.get("imaging_studies", [])
        if imaging:
            sections.append(f"## Imaging Studies ({len(imaging)})")
            for img in imaging[:10]:
                if isinstance(img, dict):
                    sections.append(f"- {img.get('date', '?')}: "
                                    f"{img.get('modality', img.get('modality_description', '?'))}"
                                    f" of {img.get('body_site', img.get('bodysite_description', '?'))}")
            sections.append("")

        # Drug-condition links
        links = ehr.get("drug_condition_links", [])
        if links:
            sections.append(f"## Drug-Condition Links ({len(links)})")
            for lnk in links[:15]:
                if isinstance(lnk, dict):
                    sections.append(f"- {lnk.get('medication', '?')} → "
                                    f"{lnk.get('condition_treated', lnk.get('condition', '?'))}")
            sections.append("")

        # Cutoff date
        cutoff = ehr.get("cutoff_date", "")
        if cutoff:
            sections.append(f"## Data Cutoff: {cutoff}")
            sections.append("All data above is from BEFORE this date.\n")

        # Data sufficiency warning (based on EHR data only — no lab_case access)
        n_conditions = len(ehr.get("conditions", {}).get("active", []))
        n_meds = len(ehr.get("medications", {}).get("active", []))
        n_imaging = len(ehr.get("imaging_studies", []))
        if n_conditions == 0 and n_meds == 0:
            sections.append("## ⚠ DATA SUFFICIENCY WARNING")
            sections.append("This patient has ZERO conditions and ZERO medications in the EHR.")
            sections.append("Flag this in data_quality_flags.\n")

        output_schema = EHRAnalystOutput.model_json_schema()
        sections.append(f"## Required Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```")

        return "\n".join(sections)


# LangGraph node function
ehr_analyst_agent = EHRAnalystAgent()
