"""Diagnostic Reasoning Agent output schema — Pydantic v2.

Implements: SDD §5.4, MA-030–034
Output: Ranked differential diagnosis with ≥3 diagnoses and evidence mapping.
"""

from pydantic import BaseModel, Field


class SupportingEvidence(BaseModel):
    source: str = Field(
        default="",
        description="Which agent or data provided this evidence: "
                    "ehr_analyst, lab_interpreter, risk_scores, comorbidity, imaging"
    )
    finding: str = Field(default="", description="The specific clinical finding")
    strength: str = Field(
        default="moderate",
        description="strong, moderate, or weak — how strongly this supports the diagnosis"
    )


class Diagnosis(BaseModel):
    rank: int = Field(default=0, description="Rank in differential (1 = most likely)")
    name: str = Field(default="", description="Diagnosis name")
    icd10: str = Field(default="", description="ICD-10 code")
    snomed: str = Field(default="", description="SNOMED-CT code")
    probability: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Estimated probability (0.0–1.0)"
    )
    confidence: str = Field(
        default="moderate",
        description="high, moderate, or low"
    )
    supporting_evidence: list[SupportingEvidence] = Field(
        default_factory=list,
        description="Evidence from upstream agents supporting this diagnosis"
    )
    reasoning: str = Field(
        default="",
        description="Clinical reasoning chain — how the evidence leads to this diagnosis"
    )


class DiagnosticOutput(BaseModel):
    """Ranked differential diagnosis produced by the Diagnostic Reasoning Agent."""

    differential: list[Diagnosis] = Field(
        default_factory=list,
        description="Ranked differential diagnoses (minimum 3, most likely first)"
    )
    primary_diagnosis: str = Field(
        default="",
        description="Name of the top-ranked diagnosis"
    )
    primary_probability: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Probability of the primary diagnosis"
    )
    clinical_reasoning_summary: str = Field(
        default="",
        description="Overall reasoning narrative — how the clinical picture, "
                    "lab evidence, and risk factors were synthesised"
    )
    unresolved_findings: list[str] = Field(
        default_factory=list,
        description="Findings that don't fit any proposed diagnosis — "
                    "unexplained abnormalities that need further investigation"
    )
    recommended_workup: list[str] = Field(
        default_factory=list,
        description="Additional tests or studies that would help confirm "
                    "or rule out the differential diagnoses"
    )
