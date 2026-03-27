"""Clinical Reviewer output schema — Pydantic v2.

Implements: SDD §5.6, MA-050–054
Output: Per-disease confidence verification, consistency check, concerns.
"""

from pydantic import BaseModel, Field


class DiagnosisVerification(BaseModel):
    diagnosis: str = Field(description="Diagnosis name from the differential")
    original_probability: float = Field(description="Probability assigned by Diagnostic Agent")
    verified_probability: float = Field(
        ge=0.0, le=1.0,
        description="Reviewer's adjusted probability after evidence verification"
    )
    confidence_score: int = Field(
        ge=0, le=100,
        description="Reviewer's confidence that this diagnosis is correct (0-100)"
    )
    evidence_strength: str = Field(
        description="strong, moderate, weak, or insufficient — "
                    "how well the available evidence supports this diagnosis"
    )
    supporting_evidence_verified: list[str] = Field(
        description="Evidence claims from Diagnostic Agent that the Reviewer confirms"
    )
    evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Missing evidence that would strengthen or weaken this diagnosis"
    )
    concerns: list[str] = Field(
        default_factory=list,
        description="Specific concerns about this diagnosis"
    )
    verdict: str = Field(
        description="supported, plausible, questionable, or unsupported"
    )


class ConsistencyCheck(BaseModel):
    area: str = Field(description="What was checked")
    status: str = Field(description="consistent, inconsistent, or unable_to_verify")
    detail: str = Field(description="Explanation")


class ReviewerOutput(BaseModel):
    """Clinical review of the diagnostic reasoning output."""

    diagnosis_verifications: list[DiagnosisVerification] = Field(
        description="Per-diagnosis verification with adjusted confidence"
    )
    overall_confidence: int = Field(
        ge=0, le=100,
        description="Overall confidence in the diagnostic differential (0-100)"
    )
    consistency_checks: list[ConsistencyCheck] = Field(
        description="Cross-checks between EHR, lab, and diagnostic outputs"
    )
    critical_findings_addressed: list[str] = Field(
        default_factory=list,
        description="Severity ≥3 lab findings that ARE addressed by the differential"
    )
    critical_findings_missed: list[str] = Field(
        default_factory=list,
        description="Severity ≥3 lab findings NOT explained by any diagnosis"
    )
    top_concerns: list[str] = Field(
        description="Most important issues the Reviewer identified"
    )
    recommended_primary: str = Field(
        description="Reviewer's opinion on what the primary diagnosis should be"
    )
    recommended_primary_confidence: int = Field(
        ge=0, le=100,
        description="Confidence in the recommended primary (0-100)"
    )
    review_summary: str = Field(
        description="Overall assessment of the diagnostic reasoning quality"
    )
