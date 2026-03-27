"""Lab Interpreter output schema — Pydantic v2.

Implements: SDD §5.3, MA-020–024
Output: Prioritised lab findings from lab_case.json
"""

from pydantic import BaseModel, Field


class LabFinding(BaseModel):
    test_name: str = Field(description="Laboratory test name")
    value: str = Field(description="Most recent value with units")
    reference_range: str = Field(default="", description="Normal range")
    classification: str = Field(
        description="normal, borderline, or abnormal"
    )
    trend: str = Field(
        default="stable",
        description="rising, falling, stable, or insufficient_data"
    )
    severity: int = Field(
        ge=1, le=5,
        description="1=normal, 2=mild, 3=moderate, 4=significant, 5=critical"
    )
    clinical_note: str = Field(
        description="Clinical interpretation of this finding"
    )
    panel_context: str = Field(
        default="",
        description="Related findings that form a clinical pattern "
                    "(e.g., elevated BUN + creatinine = renal pattern)"
    )


class LabPanel(BaseModel):
    panel_name: str = Field(description="Clinical panel name (e.g., renal, hepatic, CBC)")
    interpretation: str = Field(description="Overall panel interpretation")
    contributing_tests: list[str] = Field(
        description="Tests that form this panel pattern"
    )


class LabInterpreterOutput(BaseModel):
    """Prioritised lab findings produced by the Lab Interpreter Agent."""

    findings: list[LabFinding] = Field(
        default_factory=list,
        description="Lab findings ranked by severity (highest first)"
    )
    critical_alerts: list[str] = Field(
        default_factory=list,
        description="Immediate clinical concerns from critical lab values"
    )
    panel_patterns: list[LabPanel] = Field(
        default_factory=list,
        description="Identified clinical patterns across related labs"
    )
    trending_concerns: list[str] = Field(
        default_factory=list,
        description="Labs with worsening trends that need monitoring"
    )
    overall_assessment: str = Field(
        default="",
        description="Summary assessment of the laboratory picture — "
                    "key abnormalities, dominant patterns, urgency level"
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Important labs that are missing or outdated"
    )
