"""Call a running backend with the sample request and validate its actual report.

Requires a running real AI provider (local Ollama or configured hosted API).
There is no mock mode.
Run: python examples/smoke_sample.py --base-url http://127.0.0.1:8000
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vericommit_backend.schemas import EvaluationRequest, EvaluationResponse
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    request = EvaluationRequest.model_validate_json(
        Path(__file__).with_name("sample_evaluation.json").read_text(encoding="utf-8")
    )
    http_request = Request(
        f"{args.base_url.rstrip('/')}/api/v1/evaluations",
        data=request.model_dump_json().encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(http_request, timeout=args.timeout) as response:
            report = EvaluationResponse.model_validate_json(response.read())
    except HTTPError as exc:
        print(f"Evaluation failed (HTTP {exc.code}):", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except (URLError, TimeoutError):
        print(
            "Backend unavailable or request timed out; no report received.",
            file=sys.stderr,
        )
        return 1

    if (
        report.project_name != request.project_name
        or report.milestone_title != request.milestone.title
        or [item.criterion for item in report.criteria_results]
        != request.milestone.acceptance_criteria
    ):
        raise ValueError(
            "Report does not match the submitted project/milestone/criteria."
        )
    references = [
        item.to_public_reference()
        for item in SampleEvidenceProvider().load_dataset().evidence
    ]
    if any(
        reference not in references
        for result in report.criteria_results
        for reference in result.evidence
    ):
        raise ValueError("Report contains a reference outside the sample dataset.")
    # Print only the actual validated response; never supply expected statuses.
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
