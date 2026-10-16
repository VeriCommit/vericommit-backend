"""Deterministic local demonstration evidence, never a live-retrieval fallback."""

from importlib.resources import files
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from vericommit_backend.evidence.models import EvidenceCollection, NormalizedEvidence
from vericommit_backend.evidence.providers import (
    EvidenceProviderError,
    UnsupportedEvidenceSourceError,
)
from vericommit_backend.schemas import EvaluationRequest, Milestone, NonBlankString

SAMPLE_FIXTURE_ID = "registration-demo-v1"


class SampleEvidenceError(EvidenceProviderError):
    """A missing, invalid, or unsupported fixture prevented sample retrieval."""


class SampleDataset(EvidenceCollection):
    fixture_id: NonBlankString
    source: Literal["sample"]
    milestone: Milestone
    evidence: tuple[NormalizedEvidence, ...] = Field(min_length=1)
    limitations: tuple[NonBlankString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def stable_sample_references(self) -> Self:
        for item in self.evidence:
            if item.evidence_id != f"sample:{self.fixture_id}:{item.source_id}":
                raise ValueError(
                    "sample evidence ID must match its fixture and source ID"
                )
        return self


class SampleEvidenceProvider:
    def __init__(self, fixture_path: Path | None = None) -> None:
        # Path injection is internal-only for tests; requests cannot select files.
        self._fixture = (
            fixture_path
            if fixture_path is not None
            else files("vericommit_backend").joinpath(
                "fixtures", f"{SAMPLE_FIXTURE_ID}.json"
            )
        )

    def load_dataset(self) -> SampleDataset:
        try:
            text = self._fixture.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SampleEvidenceError(
                "Sample evidence fixture could not be read."
            ) from exc
        try:
            dataset = SampleDataset.model_validate_json(text)
        except ValidationError as exc:
            raise SampleEvidenceError("Sample evidence fixture is invalid.") from exc
        if dataset.fixture_id != SAMPLE_FIXTURE_ID:
            raise SampleEvidenceError("Unsupported sample evidence fixture.")
        return dataset

    async def retrieve(self, request: EvaluationRequest) -> EvidenceCollection:
        if request.evidence_source != "sample":
            raise UnsupportedEvidenceSourceError(
                "The sample provider only supports explicit sample mode; "
                "GitHub retrieval is not implemented."
            )
        dataset = self.load_dataset()
        return EvidenceCollection(
            source="sample",
            evidence=dataset.evidence,
            limitations=dataset.limitations,
        )
