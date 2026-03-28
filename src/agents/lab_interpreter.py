"""Lab Interpreter Agent — Stage 1 (parallel with EHR Analyst).

Reads: patient_context (lab_case from Gold layer)
Writes: agent_outputs.lab_interpreter

Classifies lab results, interprets trends, identifies clinical patterns,
and ranks findings by severity.

Implements: SDD §5.3, MA-020–024
"""

import json
import structlog
from src.agents.base import BaseAgent
from src.schemas.lab_interpreter import LabInterpreterOutput
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Lab Interpreter Agent in a multi-agent clinical decision pipeline.

Your role is to analyse laboratory results and vital signs, classify them against reference ranges, interpret trends, identify clinical patterns, and rank findings by severity.

## Your Task
1. Classify each lab result as normal, borderline, or abnormal
2. Assign severity (1-5): 1=normal, 2=mild, 3=moderate, 4=significant, 5=critical
3. Interpret trends (rising, falling, stable) and their clinical meaning
4. Identify panel patterns (e.g., elevated BUN + creatinine = renal pattern)
5. Flag critical values that need immediate attention
6. Note trending concerns (worsening values over time)
7. Identify important missing labs

## Reference Ranges (use these or standard clinical ranges)
- Hemoglobin: M 13.5-17.5, F 12.0-16.0 g/dL
- Creatinine: 0.6-1.2 mg/dL
- BUN: 7-20 mg/dL
- eGFR: >90 normal, 60-89 mild, 30-59 moderate, 15-29 severe, <15 kidney failure
- HbA1c: <5.7 normal, 5.7-6.4 borderline, ≥6.5 abnormal
- Glucose (fasting): 70-100 mg/dL
- Sodium: 136-145 mmol/L
- Potassium: 3.5-5.0 mmol/L
- WBC: 4.5-11.0 10*3/uL
- Platelets: 150-400 10*3/uL
- Troponin I: <0.04 ng/mL (high sensitivity: <14 pg/mL)
- LVEF: >55% normal, 40-55% mildly reduced, <40% significantly reduced
- Cholesterol: <200 desirable, 200-239 borderline, ≥240 high
- LDL: <100 optimal, 100-129 near-optimal, ≥160 high

## Important Rules
- Only interpret labs present in the input data — do not invent values
- Rank findings by severity (most severe first)
- When labs form a pattern (e.g., renal panel), group them
- A critical lab (severity 5) should always appear in critical_alerts
- Note trends that show deterioration even if current value is borderline

## Output Format
Respond ONLY with valid JSON matching the required schema. No preamble or explanation."""


class LabInterpreterAgent(BaseAgent):
    agent_id = "lab_interpreter"
    system_prompt = SYSTEM_PROMPT
    output_schema = LabInterpreterOutput
    temperature = 0.1
    max_tokens = 3000

    def run_reasoning(self, state: dict, llm, json_llm=None) -> dict:
        """Multi-call lab interpretation:
        Call 1: Classify each lab, identify patterns and trends
        Call 2: Produce structured JSON
        Call 3: Self-review — check for missed correlations or wrong severities
        """
        patient_data = self.build_user_prompt(state)

        # ── Call 1: Deep lab analysis ──
        logger.info("agent_step", agent_id=self.agent_id, step="analysis")
        analysis = self._call_llm(llm,
            system=self._get_call_prompt("analysis", "system",
                fallback="You are a senior clinical pathologist. Perform a thorough analysis. Do NOT produce JSON yet."),
            user=self._get_call_prompt("analysis", "user",
                fallback=patient_data, patient_data=patient_data),
        )
        logger.info("agent_step_done", agent_id=self.agent_id, step="analysis",
                     length=len(analysis))

        # ── Call 2: Structured output ──
        logger.info("agent_step", agent_id=self.agent_id, step="structure")
        jllm = json_llm or llm
        output_schema = json.dumps(LabInterpreterOutput.model_json_schema(), indent=2)
        raw_json = self._call_llm(jllm,
            system=self._get_call_prompt("structure", "system",
                fallback=self.system_prompt),
            user=self._get_call_prompt("structure", "user",
                fallback=f"{analysis}\n{patient_data}",
                analysis=analysis, patient_data=patient_data,
                output_schema=output_schema),
        )

        output = self._parse_output(raw_json, jllm, [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content="Convert to JSON"),
        ])
        output_dict = output.model_dump()

        # ── Call 3: Self-review ──
        logger.info("agent_step", agent_id=self.agent_id, step="review")
        output_json = json.dumps(output_dict, indent=2, default=str)
        review = self._call_llm(jllm,
            system=self._get_call_prompt("review", "system",
                fallback="You are a quality reviewer checking a laboratory interpretation."),
            user=self._get_call_prompt("review", "user",
                fallback=f"{patient_data}\n{output_json}",
                patient_data=patient_data, output_json=output_json),
        )

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
