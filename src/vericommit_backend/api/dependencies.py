"""Dependency injection points for later business-service implementations."""

from vericommit_backend.services.evaluation import (
    EvaluationService,
    UnconfiguredEvaluationService,
)


def get_evaluation_service() -> EvaluationService:
    return UnconfiguredEvaluationService()
