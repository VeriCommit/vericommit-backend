# VeriCommit backend

Requires Python 3.12+. From the repository root, create a virtual environment and
install the application and development tools:

```sh
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m vericommit_backend
```

The equivalent installed command is `vericommit-backend`. The ASGI entry point is
`vericommit_backend.main:app`. For direct Uvicorn development startup:

```sh
python -m uvicorn vericommit_backend.main:app --host 127.0.0.1 --port 8000 --reload
```

`python -m vericommit_backend` reads the validated `VERICOMMIT_*` server settings
from the environment and an optional `.env` in the current working directory.
Copy `.env.example` to `.env` to customize the application name, host, port, reload,
and log level; shell environment values take precedence. The default binding is
`127.0.0.1:8000`, with reload disabled. Direct Uvicorn CLI startup uses its own
host/port/reload options. No provider credentials are required at this stage.
Local `.env` files are Git-ignored; `.env.example` contains no secrets.

## Local checks

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
curl http://127.0.0.1:8000/health
```

`GET /health` returns HTTP 200 with `{"status":"ok"}`. It checks process liveness,
not evidence/AI provider readiness. Interactive docs are at `/docs`; the OpenAPI
schema is at `/openapi.json`.

## Evaluation schemas

`src/vericommit_backend/schemas.py` models the JSON request, response, and error
shapes in `docs/API_CONTRACT.md`. The endpoint reuses these models unchanged.
No evidence provider, funding-agreement storage, or AI evaluator is implemented.
`repository_url` remains required and validated as a GitHub repository URL for
both `github` and `sample`; sample mode
does not imply live retrieval. Model validation cannot establish that an evidence
URL is genuine, that a report is grounded in evidence, or that a criterion result
matches a particular request; those checks belong to later services.

## Evaluation endpoint

`POST /api/v1/evaluations` validates the approved request and delegates to the async
`EvaluationService.evaluate(request)` interface. Routing is in
`api/routes/evaluations.py`; the service interface is in `services/evaluation.py`.
Use FastAPI's `get_evaluation_service` dependency to connect a later implementation;
tests inject a fake service through `app.dependency_overrides`.

Example request (illustrative project context only):

```sh
curl -X POST http://127.0.0.1:8000/api/v1/evaluations \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"Demo","repository_url":"https://github.com/example/demo","milestone":{"title":"Registration","description":"Allow registration","acceptance_criteria":["Users can register"]},"evidence_source":"sample"}'
```

Until the real service is integrated, **valid requests return HTTP 502**, with:

```json
{
  "error": {
    "code": "EVALUATION_FAILED",
    "message": "The evaluation service is not configured. No evaluation was performed."
  }
}
```

No successful findings, evidence retrieval, AI calls, or fallback are fabricated.
The health endpoint still succeeds because it reports process liveness only.

Invalid JSON, missing/null/wrong-type fields, blank required strings, empty or
invalid criteria, unsupported sources, and undocumented fields return HTTP 400
with the existing `error.code`/`error.message` envelope. URL-format/blank-URL
validation failures use `INVALID_REPOSITORY_URL`, including alongside generic
field errors; other request validation failures use `INVALID_REQUEST`. Validation
failures never invoke `evaluate`. Responses do not echo submitted values or
framework validation details. OpenAPI documents HTTP 400 instead of FastAPI's
default 422. Provider-specific errors/timeouts and full BE-10 safeguards remain
future work.

## Confirmed MVP defaults and implementation boundaries

The backend maintainer has approved the final D1–D8 MVP policies, including HTTP
mappings and error precedence, alongside the frontend lead's previously recorded
approval. See sections 8–9 of
`docs/API_CONTRACT_REVIEW.md`. The schema keeps the contract's current fields:

- **D1 — approved:** Evaluation is synchronous and successful responses require a
  unique nonblank `evaluation_id`. No queue, UUID format, or persistence is required.
  The schema checks nonblank IDs; future service code must generate unique IDs.
- **D2 — approved:** Retain strict validation and the existing GitHub URL validator,
  including an optional trailing slash and preservation of the original string.
  Required strings must be nonblank, types must match, extra fields are rejected,
  and criteria must contain at least one nonblank string. Wording, order, and
  duplicates are preserved. No numeric maximum lengths/counts/request-size bounds
  are imposed by the schemas. Exact URL rules are in `docs/API_CONTRACT.md` section 3.
- **D3 — confirmed MVP limitation:** `repository_url` is required in both modes.
- **D4:** Response fields shown in the example are required; evidence and other
  collections may be empty. Evidence `type` is a string, not an invented enum.
  The models preserve list order; matching response criteria to a request remains
  an integration responsibility.
- **D6 — approved URL-less sample representation:** `EvidenceReference.url` must
  be present and accepts a nonblank string or `null`. Use `null` only for sample
  evidence with no genuine URL; clearly label the sample, and never invent a URL.
  Empty `evidence` lists remain valid as illustrated in the contract. Actual-source
  disclosure is a later service responsibility; no public provenance fields are added.
- **D8:** The existing nested `error.code` and `error.message` shape is preserved.
  `INVALID_REQUEST` and `INVALID_REPOSITORY_URL` map to HTTP 400,
  `REPOSITORY_ACCESS_DENIED` to 403, and `EVIDENCE_RETRIEVAL_FAILED` and
  `EVALUATION_FAILED` to 502. Upstream timeouts use 504 with the failed operation's
  existing code. Earlier workflow failures stop later stages; request validation
  uses the most specific applicable code, including `INVALID_REPOSITORY_URL`.
  No automatic retry or fallback may disguise the original failure. No new public
  error codes or fields are introduced.

Later services must implement D5's deterministic fixture selection without silent
fallback, D6's actual-source preservation/disclosure through existing fields, and
D7's distinction between insufficient evidence and retrieval/evaluation failures.
No additional public error or provenance fields are approved. The current handlers
cover request validation and the unconfigured service. BE-10 owns remaining
provider-error mappings, timeouts and security safeguards.
The public MVP contract is finalized at the policy level. Synchronous execution,
ID uniqueness, and criterion/result correlation are service requirements, not claims
of existing runtime functionality.
