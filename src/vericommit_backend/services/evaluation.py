"""Evaluation boundary for later evidence, AI and report integrations."""

from typing import Protocol

from vericommit_backend.schemas import EvaluationRequest, EvaluationResponse


class EvaluationService(Protocol):
    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        """Evaluate the supplied criteria and return a validated report."""
        ...


class EvaluationNotConfiguredError(RuntimeError):
    """No evaluation implementation is connected to the application yet."""


class UnconfiguredEvaluationService:
    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        # Never turn missing provider integrations into fabricated findings.
        raise EvaluationNotConfiguredError
