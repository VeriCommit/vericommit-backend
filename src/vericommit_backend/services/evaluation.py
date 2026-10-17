"""Synchronous request/response evaluation over replaceable async providers."""

import asyncio
from typing import Protocol

from pydantic import ValidationError

from vericommit_backend.evidence.providers import EvidenceProvider
from vericommit_backend.schemas import EvaluationRequest, EvaluationResponse
from vericommit_backend.services.ai import (
    AIEvaluationError,
    AITimeoutError,
    CriterionAIClient,
    CriterionAssessment,
)
from vericommit_backend.services.diagnostics import log_failure
from vericommit_backend.services.grounding import validate_assessment
from vericommit_backend.services.reports import build_report


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


class AIEvaluationService:
    def __init__(
        self,
        evidence_provider: EvidenceProvider,
        ai_client: CriterionAIClient,
        timeout_seconds: float = 30,
    ) -> None:
        self.evidence_provider = evidence_provider
        self.ai_client = ai_client
        self.timeout_seconds = timeout_seconds

    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        evidence = await self.evidence_provider.retrieve(request)
        if evidence.source != request.evidence_source:
            log_failure("evaluation.evidence_source", AIEvaluationError())
            raise AIEvaluationError(
                "Evidence source does not match the requested source."
            )
        results, uncertainties, next_steps = [], [], []
        for index, criterion in enumerate(
            request.milestone.acceptance_criteria, start=1
        ):
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    assessment = await self.ai_client.assess(
                        criterion, request.milestone, evidence
                    )
                # The replaceable boundary must enforce the same schema even for
                # clients other than the SDK adapter (including model_copy bypasses).
                assessment = CriterionAssessment.model_validate(assessment)
            except TimeoutError as exc:
                log_failure("evaluation.assess_timeout", exc)
                raise AITimeoutError("AI evaluation timed out.") from exc
            except ValidationError as exc:
                log_failure("evaluation.assessment_schema", exc)
                raise AIEvaluationError("AI assessment failed validation.") from exc
            try:
                result = validate_assessment(criterion, assessment, evidence)
            except (AIEvaluationError, ValidationError) as exc:
                log_failure("grounding.validate_assessment", exc)
                raise
            results.append(result)
            uncertainties.extend(
                f"Criterion {index} — AI-reported gap/uncertainty (not verified fact): {gap}"
                for gap in assessment.uncertainties
            )
            next_steps.extend(
                f"Criterion {index} — AI suggestion for human review: {step}"
                for step in assessment.suggested_next_steps
            )
        try:
            return build_report(request, evidence, results, uncertainties, next_steps)
        except (AIEvaluationError, ValidationError) as exc:
            log_failure("reports.build_report", exc)
            raise
