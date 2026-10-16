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
shapes in `docs/API_CONTRACT.md`. No evaluation endpoint, evidence provider,
funding-agreement storage, or AI service is implemented yet. `repository_url`
remains required and validated as a GitHub repository URL for both `github` and `sample`; sample mode
does not imply live retrieval. Model validation cannot establish that an evidence
URL is genuine, that a report is grounded in evidence, or that a criterion result
matches a particular request; those checks belong to later services.

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
No additional public error or provenance fields are approved. BE-10 owns exception
handlers and the approved transport mappings and overlapping-error precedence.
The public MVP contract is finalized at the policy level. Synchronous execution,
ID uniqueness, and criterion/result correlation are service requirements, not claims
of existing runtime functionality.
