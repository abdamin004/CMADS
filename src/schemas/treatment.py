"""Treatment Planning Agent output schema — Pydantic v2.

Output: Treatment plan based on NICE guidelines for the diagnosed disease.
"""

from pydantic import BaseModel, Field


class PrescribedMedication(BaseModel):
    medication: str = Field(description="Drug name and dose")
    drug_class: str = Field(default="", description="Drug class (e.g., ACE inhibitor, Beta-blocker)")
    dose: str = Field(default="", description="Dosing regimen (e.g., 5mg once daily)")
    duration: str = Field(default="", description="Duration (e.g., Ongoing, 12 months, Until review)")
    purpose: str = Field(default="", description="Why this drug is prescribed for this patient")
    nice_justification: str = Field(default="", description="NICE guideline reference supporting this choice")
    line: str = Field(default="first_line", description="first_line, second_line, or additional")


class InteractionCheck(BaseModel):
    drug_pair: list[str] = Field(description="The two drugs that interact")
    interaction: str = Field(description="Description of the interaction")
    severity: str = Field(default="moderate", description="mild, moderate, or severe")
    action: str = Field(default="", description="What to do about it")


class ContraindicationCheck(BaseModel):
    drug: str = Field(description="Drug that is contraindicated")
    reason: str = Field(description="Why it is contraindicated for this patient")
    alternative: str = Field(default="", description="What to use instead")


class MonitoringPlan(BaseModel):
    test: str = Field(description="What to monitor")
    frequency: str = Field(description="How often")
    reason: str = Field(default="", description="Why this monitoring is needed")


class TreatmentOutput(BaseModel):
    """Treatment plan produced by the Treatment Planning Agent."""

    primary_diagnosis_treated: str = Field(
        default="",
        description="The diagnosis this treatment plan addresses"
    )
    nice_guideline_used: str = Field(
        default="",
        description="NICE guideline reference (e.g., NG106, NG136)"
    )
    medications: list[PrescribedMedication] = Field(
        default_factory=list,
        description="Prescribed medications with dose, duration, and justification"
    )
    interactions_checked: list[InteractionCheck] = Field(
        default_factory=list,
        description="Drug interactions identified between proposed and current medications"
    )
    contraindications: list[ContraindicationCheck] = Field(
        default_factory=list,
        description="Drugs that should NOT be given to this patient"
    )
    assumptions_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings where NICE guideline requires data the patient record does not have. "
                    "E.g., 'NICE NG136 requires QRISK assessment — not available in patient data', "
                    "'eGFR unknown — assumed normal for ACE-I dosing', "
                    "'Allergy status unknown — cannot verify drug safety'"
    )
    treatment_summary: str = Field(
        default="",
        description="Brief summary of the treatment plan and rationale"
    )
