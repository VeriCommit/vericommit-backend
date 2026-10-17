"""Evaluation HTTP endpoint; no evidence or AI business logic lives here."""

from typing import Annotated

from fastapi import APIRouter, Depends

from vericommit_backend.api.dependencies import get_evaluation_service
from vericommit_backend.schemas import (
    ErrorResponse,
    EvaluationRequest,
    EvaluationResponse,
)
from vericommit_backend.services.evaluation import EvaluationService

router = APIRouter(tags=["evaluations"])


@router.post(
    "/evaluations",
    response_model=EvaluationResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid request or repository URL",
        },
        502: {
            "model": ErrorResponse,
            "description": "Evaluation could not be completed",
        },
        403: {"model": ErrorResponse, "description": "Repository access unavailable"},
        504: {"model": ErrorResponse, "description": "Evidence or AI upstream timeout"},
    },
)
async def evaluate(
    request: EvaluationRequest,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationResponse:
    return await service.evaluate(request)
