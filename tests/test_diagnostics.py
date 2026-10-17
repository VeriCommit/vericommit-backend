"""Diagnostics use allowlisted metadata even with hostile upstream bodies."""

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, BadRequestError
from pydantic import ValidationError

from vericommit_backend.services.ai import CriterionAssessment
from vericommit_backend.services.diagnostics import log_failure


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "invalid_json_schema",
            "Check the model's supported structured-output schema.",
        ),
        ("unsupported_parameter", "Check request parameters supported by the model."),
        ("private-code\nAuthorization: private-key", "provider_code=unclassified"),
        ({"private": "private-key"}, "provider_code=unclassified"),
    ],
)
def test_provider_diagnostics_never_log_unrecognized_text(code, expected, caplog):
    response = httpx.Response(
        400,
        request=httpx.Request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer private-key"},
        ),
    )
    exc = BadRequestError(
        "private-exception-message",
        response=response,
        body={"code": code, "message": "private-body", "param": "private-param"},
    )
    log_failure("openai.chat.completions", exc)
    assert expected in caplog.text
    assert "exception=BadRequestError status=400" in caplog.text
    assert "private" not in caplog.text
    assert "Authorization" not in caplog.text


@pytest.mark.parametrize("timeout", [False, True])
def test_network_diagnostics_do_not_log_request_or_exception(timeout, caplog):
    request = httpx.Request("POST", "https://private-host/private-path")
    exc = (
        APITimeoutError(request=request)
        if timeout
        else APIConnectionError(request=request, message="private-detail")
    )
    log_failure("openai.chat.completions", exc)
    assert "timeout" in caplog.text if timeout else "connectivity" in caplog.text
    assert "private" not in caplog.text


def test_validation_diagnostics_do_not_log_input_values(caplog):
    with pytest.raises(ValidationError) as exc_info:
        CriterionAssessment.model_validate({"criterion": "private-evidence"})
    log_failure("ai.structured_response", exc_info.value)
    assert "exception=ValidationError" in caplog.text
    assert "component=ai.structured_response" in caplog.text
    assert "private-evidence" not in caplog.text
