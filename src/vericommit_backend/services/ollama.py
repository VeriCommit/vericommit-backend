"""Real, non-streaming Ollama inference through its native local HTTP API."""

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.schemas import Milestone, NonBlankString
from vericommit_backend.services.ai import (
    AIEvaluationError,
    AITimeoutError,
    CriterionAssessment,
    assessment_messages,
)
from vericommit_backend.services.diagnostics import log_failure


class _Message(BaseModel):
    model_config = ConfigDict(strict=True)
    role: Literal["assistant"]
    content: NonBlankString
    tool_calls: list = Field(default_factory=list)


class _ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    message: _Message
    done: bool
    done_reason: Literal["stop"]

    @field_validator("done")
    @classmethod
    def completed(cls, value: bool) -> bool:
        if not value:
            raise ValueError("incomplete response")
        return value


class OllamaCriterionClient:
    def __init__(self, http: httpx.AsyncClient, model: str) -> None:
        self.http = http
        self.model = model

    async def assess(
        self, criterion: str, milestone: Milestone, evidence: EvidenceCollection
    ) -> CriterionAssessment:
        try:
            response = await self.http.post(
                "api/chat",
                json={
                    "model": self.model,
                    "messages": assessment_messages(criterion, milestone, evidence),
                    "format": CriterionAssessment.model_json_schema(),
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 2000, "num_ctx": 8192},
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            log_failure("ollama.api.chat", exc)
            raise AITimeoutError("AI request timed out.") from exc
        except httpx.HTTPError as exc:
            log_failure("ollama.api.chat", exc)
            raise AIEvaluationError("AI provider request failed.") from exc
        try:
            result = _ChatResponse.model_validate_json(response.content)
            if result.message.tool_calls:
                raise AIEvaluationError("AI returned unexpected tool calls.")
            return CriterionAssessment.model_validate_json(result.message.content)
        except (ValidationError, AIEvaluationError) as exc:
            log_failure("ollama.structured_response", exc)
            raise AIEvaluationError("AI structured validation failed.") from exc
