"""Evaluation boundary for later evidence, AI and report integrations."""

from typing import Protocol

from vericommit_backend.evidence.providers import EvidenceProvider
from vericommit_backend.schemas import EvaluationRequest, EvaluationResponse


class EvaluationService(Protocol):
    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        """Evaluate the supplied criteria and return a validated report."""
        ...


class EvaluationNotConfiguredError(RuntimeError):
    """No evaluation implementation is connected to the application yet."""


class UnconfiguredEvaluationService:
    def __init__(self, evidence_provider: EvidenceProvider) -> None:
        self.evidence_provider = evidence_provider

    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        # Never turn missing provider integrations into fabricated findings.
        raise EvaluationNotConfiguredError
