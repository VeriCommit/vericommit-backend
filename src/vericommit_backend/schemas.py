"""Pydantic models for the documented MVP evaluation JSON contract.

These models describe evaluation inputs and reports, not persistent funding records.
See docs/API_CONTRACT.md and docs/API_CONTRACT_REVIEW.md for open decisions.
"""

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankString = Annotated[str, AfterValidator(_non_blank)]
EvidenceSource = Literal["github", "sample"]
CriterionStatus = Literal["supported", "insufficient_evidence", "uncertain"]

# Conservative GitHub web URL form for this schema; URL form/normalization is D2.
_REPOSITORY_PATH = re.compile(
    r"/[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_.-]+/?\Z"
)


class ContractModel(BaseModel):
    """Reject undocumented fields and type coercion in contract JSON."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Milestone(ContractModel):
    """Agreed evaluation scope, not a persistent Milestone ownership record."""

    title: NonBlankString
    description: NonBlankString
    acceptance_criteria: list[NonBlankString] = Field(min_length=1)


class EvaluationRequest(ContractModel):
    project_name: NonBlankString
    repository_url: NonBlankString
    milestone: Milestone
    evidence_source: EvidenceSource

    @field_validator("repository_url")
    @classmethod
    def supported_repository_url(cls, value: str) -> str:
        # Do not normalize the input or interpret it as authorization to access a repo.
        if any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError("must be a GitHub repository URL")
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.netloc.lower() != "github.com"
            or "?" in value
            or "#" in value
            or not _REPOSITORY_PATH.fullmatch(parts.path)
            or parts.path.rstrip("/").split("/")[-1] in {".", ".."}
        ):
            raise ValueError("must be a GitHub repository URL")
        return value


class EvidenceReference(ContractModel):
    type: NonBlankString
    title: NonBlankString
    # Field remains required; a URL-less sample reference uses JSON null (D6).
    url: NonBlankString | None


class CriterionResult(ContractModel):
    criterion: NonBlankString
    status: CriterionStatus
    explanation: NonBlankString
    evidence: list[EvidenceReference]


class EvaluationResponse(ContractModel):
    evaluation_id: NonBlankString
    project_name: NonBlankString
    milestone_title: NonBlankString
    overall_summary: NonBlankString
    criteria_results: list[CriterionResult]
    suggested_next_steps: list[str]
    limitations: list[str]
    human_review_required: Literal[True]

    @field_validator("human_review_required", mode="before")
    @classmethod
    def strict_human_review_required(cls, value: object) -> bool:
        # Literal[True] alone also accepts numeric values equal to True.
        if value is not True:
            raise ValueError("must be the boolean true")
        return value


class ErrorDetail(ContractModel):
    # The documented error codes are suggested, not an approved closed enum (D8).
    code: NonBlankString
    message: NonBlankString


class ErrorResponse(ContractModel):
    error: ErrorDetail
