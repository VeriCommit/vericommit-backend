"""Small provider contract shared by sample and future live retrieval."""

from typing import Protocol

from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.schemas import EvaluationRequest


class EvidenceProviderError(RuntimeError):
    """Evidence could not be supplied; never interpret this as an empty retrieval."""


class UnsupportedEvidenceSourceError(EvidenceProviderError):
    """The selected provider cannot handle the requested evidence source."""


class EvidenceProvider(Protocol):
    async def retrieve(self, request: EvaluationRequest) -> EvidenceCollection:
        """Return normalized evidence or fail explicitly; never silently switch source."""
        ...
