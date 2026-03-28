"""EHR Analyst Agent — Stage 1 (parallel with Lab Interpreter).

Reads: patient_context (ehr_case from Gold layer)
Writes: agent_outputs.ehr_analyst

Extracts a structured clinical summary from the patient's EHR data.
Does NOT diagnose — summarises and structures for downstream agents.

Implements: SDD §5.2, MA-010–013
"""

import json
from src.agents.base import BaseAgent
from src.schemas.ehr_analyst import EHRAnalystOutput


class EHRAnalystAgent(BaseAgent):
    agent_id = "ehr_analyst"
    output_schema = EHRAnalystOutput
    temperature = 0.1
    max_tokens = 3000

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        return self._run_analysis_structure_review(state, llm, json_llm)

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
