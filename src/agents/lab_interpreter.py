"""Lab Interpreter Agent — Stage 1 (parallel with EHR Analyst).

Reads: patient_context (lab_case from Gold layer)
Writes: agent_outputs.lab_interpreter

Classifies lab results, interprets trends, identifies clinical patterns,
and ranks findings by severity.

Implements: SDD §5.3, MA-020–024
"""

import json
from src.agents.base import BaseAgent
from src.schemas.lab_interpreter import LabInterpreterOutput


class LabInterpreterAgent(BaseAgent):
    agent_id = "lab_interpreter"
    output_schema = LabInterpreterOutput
    temperature = 0.1
    max_tokens = 3000

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        return self._run_analysis_structure_review(state, llm, json_llm)

    def build_user_prompt(self, state: dict) -> str:
        ctx = state.get("patient_context", {})
        lab = ctx.get("lab_case", {})

        sections = []
        sections.append("# Patient Laboratory Data\n")

        # Latest labs
        latest = lab.get("latest_labs", [])
        if latest:
            sections.append(f"## Latest Lab Results ({len(latest)} tests)")
            for l in latest:
                if isinstance(l, dict):
                    name = l.get("name", l.get("lab_name", l.get("test", "Unknown")))
                    value = l.get("value", l.get("value_latest", "?"))
                    units = l.get("units", "")
                    date = l.get("date", l.get("latest_date", ""))
                    sections.append(f"- {name}: {value} {units} ({date})")
                else:
                    sections.append(f"- {l}")
            sections.append("")

        # Lab trends
        trends = lab.get("lab_trends", [])
        if trends:
            sections.append(f"## Lab Trends ({len(trends)} tracked)")
            for t in trends:
                if isinstance(t, dict):
                    name = t.get("lab_name", t.get("name", "Unknown"))
                    trend_dir = t.get("trend", t.get("trend_direction", "?"))
                    latest_val = t.get("value_latest", t.get("latest_value", "?"))
                    first_val = t.get("value_first", "?")
                    count = t.get("measurement_count", t.get("count", "?"))
                    pct = t.get("pct_change_first_to_latest", "")
                    units = t.get("units", "")
                    sections.append(
                        f"- {name}: {trend_dir} | latest={latest_val} {units}"
                        f" | first={first_val} | n={count}"
                        f"{f' | change={pct}%' if pct else ''}"
                    )
            sections.append("")

        # Critical flags
        flags = lab.get("critical_flags", [])
        if flags:
            sections.append(f"## Critical Lab Flags ({len(flags)})")
            for f in flags:
                if isinstance(f, dict):
                    name = f.get("lab_name", f.get("name", "Unknown"))
                    flag = f.get("flag", "flagged")
                    value = f.get("value_latest", f.get("value", "?"))
                    severity = f.get("severity", "?")
                    sections.append(f"- {name}: {value} — {flag} (severity: {severity})")
            sections.append("")

        # Recent vitals
        vitals = lab.get("recent_vitals", [])
        if vitals:
            sections.append(f"## Recent Vitals ({len(vitals)})")
            for v in vitals:
                if isinstance(v, dict):
                    name = v.get("name", v.get("vital", "Unknown"))
                    value = v.get("value", "?")
                    units = v.get("units", "")
                    sections.append(f"- {name}: {value} {units}")
            sections.append("")

        # Summary counts
        lab_count = lab.get("lab_count", 0)
        vital_count = lab.get("vital_count", 0)
        sections.append(f"## Data Summary")
        sections.append(f"- Total lab measurements available: {lab_count}")
        sections.append(f"- Total vital measurements available: {vital_count}")
        cutoff = lab.get("cutoff_date", "")
        if cutoff:
            sections.append(f"- Data cutoff date: {cutoff}")
        sections.append("")

        output_schema = LabInterpreterOutput.model_json_schema()
        sections.append(f"## Required Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```")

        return "\n".join(sections)


# LangGraph node function
lab_interpreter_agent = LabInterpreterAgent()
