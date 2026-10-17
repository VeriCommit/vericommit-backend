"""Verify a running real backend. No mock fallback and no provider credentials here."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from vericommit_backend.schemas import (
    ErrorResponse,
    EvaluationRequest,
    EvaluationResponse,
)
from vericommit_backend.services.github_evidence import parse_repository
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider

FIXTURES = Path(__file__).resolve().parent
ERROR_CODES = {
    "INVALID_REQUEST",
    "INVALID_REPOSITORY_URL",
    "REPOSITORY_ACCESS_DENIED",
    "EVIDENCE_RETRIEVAL_FAILED",
    "EVALUATION_FAILED",
}


class SmokeFailure(ValueError):
    """Only static, non-sensitive diagnostic messages are exposed by this client."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def validate_report(request: EvaluationRequest, report: EvaluationResponse) -> None:
    check(
        report.project_name == request.project_name
        and report.milestone_title == request.milestone.title,
        "Report project/milestone does not match the request.",
    )
    check(
        [result.criterion for result in report.criteria_results]
        == request.milestone.acceptance_criteria,
        "Report criterion order or wording does not match the request.",
    )
    check(report.human_review_required is True, "Report must require human review.")
    check(
        any(
            note
            == f"Actual evidence source: {request.evidence_source}. No source fallback was used."
            for note in report.limitations
        ),
        "Report does not disclose the actual requested evidence source.",
    )
    for result in report.criteria_results:
        check(
            result.status == "insufficient_evidence" or bool(result.evidence),
            "Supported or uncertain results need evidence references.",
        )
    references = [
        reference for result in report.criteria_results for reference in result.evidence
    ]
    if request.evidence_source == "sample":
        authorized = [
            item.to_public_reference()
            for item in SampleEvidenceProvider().load_dataset().evidence
        ]
        check(
            all(reference in authorized for reference in references),
            "Report contains a reference outside the sample dataset.",
        )
        check(
            any("synthetic" in note.casefold() for note in report.limitations),
            "Sample provenance is not labelled synthetic.",
        )
    else:
        repository = parse_repository(request.repository_url).casefold()
        for reference in references:
            # Server grounding establishes authorization to the retrieved snapshot.
            # This client checks traceability shape/scope; it does not refetch URLs
            # or claim independent verification of GitHub text or model judgment.
            pattern = rf"\[github:{re.escape(repository)}:{re.escape(reference.type)}:[^\[\]\s]+\]$"
            check(
                re.search(pattern, reference.title) is not None,
                "GitHub evidence has a missing or mismatched stable reference.",
            )
            if reference.url is not None:
                parts = urlsplit(reference.url)
                check(
                    parts.scheme == "https"
                    and parts.netloc.casefold() == "github.com"
                    and parts.path.casefold().startswith(f"/{repository}/"),
                    "GitHub source link is outside the requested repository.",
                )


def run(
    client: httpx.Client, request: EvaluationRequest, origin: str
) -> EvaluationResponse:
    health = client.get("/health")
    check(
        health.status_code == 200 and health.json() == {"status": "ok"},
        "Health verification failed.",
    )
    preflight = client.options(
        "/api/v1/evaluations",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, accept",
        },
    )
    check(
        preflight.status_code == 200
        and preflight.headers.get("access-control-allow-origin") == origin
        and "access-control-allow-credentials" not in preflight.headers,
        "CORS preflight verification failed for the configured origin.",
    )
    invalid = json.loads(
        (FIXTURES / "invalid_evaluation.json").read_text(encoding="utf-8")
    )
    failure = client.post(
        "/api/v1/evaluations", json=invalid, headers={"Origin": origin}
    )
    check(
        failure.status_code == 400
        and ErrorResponse.model_validate_json(failure.content).error.code
        == "INVALID_REQUEST",
        "Malformed-request error verification failed.",
    )
    response = client.post(
        "/api/v1/evaluations",
        json=request.model_dump(mode="json"),
        headers={"Origin": origin},
    )
    if response.status_code != 200:
        try:
            code = ErrorResponse.model_validate_json(response.content).error.code
        except ValidationError:
            code = "UNRECOGNIZED_ERROR"
        if code not in ERROR_CODES:
            code = "UNRECOGNIZED_ERROR"
        raise SmokeFailure(
            f"Evaluation failed: HTTP {response.status_code}, category={code}."
        )
    check(
        response.headers.get("access-control-allow-origin") == origin,
        "Evaluation response is missing CORS headers.",
    )
    report = EvaluationResponse.model_validate_json(response.content)
    validate_report(request, report)
    return report


def main(
    argv: list[str] | None = None,
    *,
    default_source: str = "sample",
    transport: httpx.BaseTransport | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=["sample", "github"], default=default_source
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--origin", default="http://localhost:3000")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument(
        "--summary", action="store_true", help="Print counts instead of report text."
    )
    args = parser.parse_args(argv)
    try:
        base = urlsplit(args.base_url)
        check(
            base.scheme in {"http", "https"}
            and bool(base.hostname)
            and base.username is None
            and base.password is None
            and not base.query
            and not base.fragment,
            "Provide an HTTP(S) backend URL without credentials, query or fragment.",
        )
        check(
            0 < args.timeout <= 1200,
            "Smoke timeout must be greater than zero and at most 1200 seconds.",
        )
        request = EvaluationRequest.model_validate_json(
            (FIXTURES / f"{args.source}_evaluation.json").read_text(encoding="utf-8")
        )
        with httpx.Client(
            base_url=args.base_url.rstrip("/"),
            timeout=args.timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            report = run(client, request, args.origin)
        if args.summary:
            print(
                json.dumps(
                    {
                        "source": args.source,
                        "health": "ok",
                        "cors_preflight": "ok",
                        "invalid_request": "ok",
                        "criteria": len(report.criteria_results),
                        "references": sum(
                            len(item.evidence) for item in report.criteria_results
                        ),
                        "human_review_required": report.human_review_required,
                    }
                )
            )
        else:
            print(report.model_dump_json(indent=2))
        return 0
    except SmokeFailure as exc:
        print(str(exc), file=sys.stderr)
    except (httpx.HTTPError, ValidationError, ValueError, OSError):
        print(
            "Backend unavailable, timeout, or invalid response/fixture; no validated report received.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
