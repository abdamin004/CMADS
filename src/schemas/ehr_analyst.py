"""EHR Analyst output schema — Pydantic v2.

Implements: SDD §5.2, MA-010–013
Output: Structured clinical summary from ehr_case.json
"""

from pydantic import BaseModel, Field


class ActiveProblem(BaseModel):
    name: str = Field(description="Condition name")
    snomed_code: str = Field(default="", description="SNOMED-CT code if available")
    onset_date: str = Field(default="", description="Date condition started")
    status: str = Field(default="active", description="active, resolved, or chronic")
    clinical_significance: str = Field(
        default="moderate",
        description="low, moderate, or high — relevance to current clinical picture"
    )


class Medication(BaseModel):
    name: str = Field(description="Medication name")
    purpose: str = Field(default="", description="Why this medication is prescribed")
    relevance: str = Field(
        default="routine",
        description="routine, significant, or critical — relevance to differential"
    )


class DataQualityFlag(BaseModel):
    field: str = Field(description="Field name with issue")
    issue: str = Field(description="Description of data quality concern")


class EHRAnalystOutput(BaseModel):
    """Structured clinical summary produced by the EHR Analyst Agent."""

    chief_complaint: str = Field(
        default="",
        description="Primary clinical concern based on visit patterns and conditions"
    )
    history_of_present_illness: str = Field(
        default="",
        description="Narrative summary of the patient's recent clinical trajectory"
    )
    active_problems: list[ActiveProblem] = Field(
        default_factory=list,
        description="Active conditions ranked by clinical significance"
    )
    past_medical_history: str = Field(
        default="",
        description="Summary of resolved or chronic background conditions"
    )
    active_medications: list[Medication] = Field(
        default_factory=list,
        description="Current medications with clinical relevance"
    )
    allergies: list[str] = Field(
        default_factory=list,
        description="Known allergies"
    )
    social_determinants: str = Field(
        default="",
        description="Relevant social/demographic factors affecting health"
    )
    risk_factor_summary: str = Field(
        default="",
        description="Summary of computed risk scores and comorbidity flags"
    )
    data_quality_flags: list[DataQualityFlag] = Field(
        default_factory=list,
        description="Missing or suspicious data fields"
    )
    clinical_impression: str = Field(
        default="",
        description="Brief overall clinical impression — NOT a diagnosis, "
                    "but a summary of the clinical picture"
    )
