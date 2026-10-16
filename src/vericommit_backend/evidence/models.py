"""Validated evidence for sample and future GitHub providers."""

from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

from vericommit_backend.schemas import EvidenceReference, EvidenceSource, NonBlankString

EvidenceType = Literal["commit", "pull_request", "release", "test_result"]
_http_url = TypeAdapter(AnyHttpUrl)


def _source_url(value: str) -> str:
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("source URL must not contain whitespace or control characters")
    parsed = _http_url.validate_python(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL must not contain credentials")
    # Validation does not prove authenticity; never normalize or invent a link.
    return value


SourceURL = Annotated[NonBlankString, AfterValidator(_source_url)]


class InternalEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class EvidenceMetadata(InternalEvidenceModel):
    repository: NonBlankString | None = None
    commit_sha: NonBlankString | None = None
    pull_request_number: int | None = Field(default=None, gt=0)
    release_tag: NonBlankString | None = None
    author: NonBlankString | None = None


class NormalizedEvidence(InternalEvidenceModel):
    evidence_id: NonBlankString
    source: EvidenceSource
    source_id: NonBlankString
    type: EvidenceType
    title: NonBlankString
    url: SourceURL | None = None
    content: NonBlankString | None = None
    metadata: EvidenceMetadata = Field(default_factory=EvidenceMetadata)

    @model_validator(mode="after")
    def sample_is_labelled(self) -> Self:
        if self.source == "sample" and (
            not self.title.startswith("Sample: ") or not self.title[8:].strip()
        ):
            raise ValueError("sample evidence titles must start with 'Sample: '")
        return self

    def to_public_reference(self) -> EvidenceReference:
        if self.url is None and self.source != "sample":
            raise ValueError(
                "URL-less public references must be explicitly labelled samples"
            )
        # Carry the stable reference in an existing field, never a new public ID.
        return EvidenceReference(
            type=self.type,
            title=f"{self.title} [{self.evidence_id}]",
            url=self.url,
        )


class EvidenceCollection(InternalEvidenceModel):
    source: EvidenceSource
    evidence: tuple[NormalizedEvidence, ...]
    limitations: tuple[NonBlankString, ...] = ()

    @model_validator(mode="after")
    def consistent_provenance_and_ids(self) -> Self:
        if any(item.source != self.source for item in self.evidence):
            raise ValueError("evidence provenance must match its collection source")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence identifiers must be unique within a collection")
        return self
