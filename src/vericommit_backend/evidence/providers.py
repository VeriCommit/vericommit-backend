"""Small provider contract shared by sample and future live retrieval."""

from typing import Protocol

from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.schemas import EvaluationRequest


class EvidenceProviderError(RuntimeError):
    """Evidence could not be supplied; never interpret this as an empty retrieval."""


class UnsupportedEvidenceSourceError(EvidenceProviderError):
    """The selected provider cannot handle the requested evidence source."""


class RepositoryAccessDeniedError(EvidenceProviderError):
    """The repository is unavailable, inaccessible, or outside public MVP scope."""


class EvidenceTimeoutError(EvidenceProviderError):
    """Evidence retrieval exceeded its bounded deadline."""


class EvidenceRateLimitError(EvidenceProviderError):
    """The upstream provider refused retrieval because of a rate limit."""


class EvidenceProvider(Protocol):
    async def retrieve(self, request: EvaluationRequest) -> EvidenceCollection:
        """Return normalized evidence or fail explicitly; never silently switch source."""
        ...


class EvidenceSourceRouter:
    def __init__(self, sample: EvidenceProvider, github: EvidenceProvider) -> None:
        self.providers = {"sample": sample, "github": github}

    async def retrieve(self, request: EvaluationRequest) -> EvidenceCollection:
        provider = self.providers.get(request.evidence_source)
        if provider is None:
            raise UnsupportedEvidenceSourceError("Unsupported evidence source.")
        return await provider.retrieve(request)
