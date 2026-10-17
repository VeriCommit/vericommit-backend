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
host/port/reload options. Health and validation work without provider credentials;
successful AI evaluation requires a running local model or hosted provider below.
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

CI runs the same Pytest, Ruff lint, Ruff formatting and whitespace checks on pull
requests targeting `staging`/`main` and pushes to either branch. The matrix covers
Python 3.12 and 3.14 on Linux and Windows, uses read-only repository permissions,
and receives no provider secrets. Tests isolate provider settings and block
unmocked upstream HTTP; loopback HTTP remains available for executable API tests.
Any failed step fails its job. Maintainers must select these checks as required in
GitHub branch protection/rulesets if merges must be blocked; workflow configuration
alone cannot enforce that repository policy.

### Frontend CORS and safe failures

`VERICOMMIT_CORS_ORIGINS` is a JSON array of exact frontend origins, defaulting to
`["http://localhost:3000"]`. Set deployed origins explicitly, for example
`["https://demo.example"]`; `[]` denies cross-origin access. Wildcards, credentials
and URL paths are rejected. GET, POST and preflight OPTIONS support Content-Type
and Accept headers. Cookies/cross-origin credentials are not enabled. CORS is not
authentication; the public MVP API has no funding-administration permissions.

Unexpected evaluation and invalid-report errors return the existing safe
`EVALUATION_FAILED`/502 envelope. Application diagnostics contain only safe
category/component/status guidance. Verbose HTTP transport, ASGI scope and raw
access logs are suppressed to avoid logging headers, query strings or upstream
bodies, including when the configured server log level is verbose.

## Evaluation schemas

`src/vericommit_backend/schemas.py` models the JSON request, response, and error
shapes in `docs/API_CONTRACT.md`. The endpoint reuses these models unchanged.
Sample and public GitHub evidence providers are implemented, with configurable
Ollama, Groq and OpenAI evaluators. Funding-agreement storage is not implemented.
`repository_url` remains required and validated as a GitHub repository URL for
both `github` and `sample`; sample mode
does not imply live retrieval. Model validation cannot establish that an evidence
URL is genuine, that a report is grounded in evidence, or that a criterion result
matches a particular request; grounding and criterion correlation are enforced by
the evaluation services described below.

## Evaluation endpoint

`POST /api/v1/evaluations` validates the approved request and delegates to the async
`EvaluationService.evaluate(request)` interface. Routing is in
`api/routes/evaluations.py`; the service interface is in `services/evaluation.py`.
FastAPI's `get_evaluation_service` dependency connects the configured AI evaluator;
tests can replace its AI or evidence boundary through `app.dependency_overrides`.

Example request (illustrative project context only):

```sh
curl -X POST http://127.0.0.1:8000/api/v1/evaluations \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"Demo","repository_url":"https://github.com/example/demo","milestone":{"title":"Registration","description":"Allow registration","acceptance_criteria":["Users can register"]},"evidence_source":"sample"}'
```

If the selected hosted provider lacks its key/model, valid sample requests return
**HTTP 502**, with:

```json
{
  "error": {
    "code": "EVALUATION_FAILED",
    "message": "The evaluation service is not configured. No evaluation was performed."
  }
}
```

No successful findings, live evidence retrieval, AI calls, or fallback are fabricated.
The health endpoint still succeeds because it reports process liveness only.

### Run an AI-assisted sample evaluation

Select exactly one provider using `VERICOMMIT_AI_PROVIDER` (`openai`, `ollama`,
or `groq`). The application default remains `openai` for existing installations;
`.env.example` selects local `ollama`. Selection never falls back to another provider.

#### Windows: local Ollama, no API credits

Install [Ollama for Windows](https://ollama.com/download/windows), or run
`winget install --id Ollama.Ollama -e`, then open a new PowerShell terminal.
Start the Ollama app (or `ollama serve` if it is not already running), then:

```powershell
ollama pull qwen2.5:3b
ollama list
# From the repository root, with your Python environment activated:
python -m pip install -e ".[dev]"
$env:VERICOMMIT_AI_PROVIDER = "ollama"
$env:VERICOMMIT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:VERICOMMIT_OLLAMA_MODEL = "qwen2.5:3b"
$env:VERICOMMIT_OLLAMA_TIMEOUT_SECONDS = "120"
python -m vericommit_backend
```

These values can also be set in your existing `.env`; preserve any existing keys.
The default `qwen2.5:3b` download is about 1.9 GB. Choose an installed model suitable
for your RAM/CPU/GPU; `qwen2.5:1.5b` is a smaller option. Pull that tag and change
`VERICOMMIT_OLLAMA_MODEL` together. Models must support chat and native structured
outputs. Small models can still produce invalid or ungrounded responses, which
are rejected rather than repaired or replaced with findings.

#### Provider settings

| Provider | Environment variables |
| --- | --- |
| `ollama` | `VERICOMMIT_OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`), `VERICOMMIT_OLLAMA_MODEL` (default `qwen2.5:3b`), `VERICOMMIT_OLLAMA_TIMEOUT_SECONDS` (default `120`) |
| `openai` | `VERICOMMIT_OPENAI_API_KEY` (or `OPENAI_API_KEY`), `VERICOMMIT_AI_MODEL` (default `gpt-4o-mini`), `VERICOMMIT_AI_TIMEOUT_SECONDS` (default `30`) |
| `groq` | `VERICOMMIT_GROQ_API_KEY` (or `GROQ_API_KEY`), **required** `VERICOMMIT_GROQ_MODEL` (no default), `VERICOMMIT_AI_TIMEOUT_SECONDS` (default `30`) |

Timeouts are per criterion, greater than zero and at most 300 seconds, covering
the complete AI operation. Ollama uses `/api/chat`, JSON Schema and no streaming;
environment proxies are disabled for the local client. Hosted providers use strict
JSON Schema. For Groq, choose a currently accessible model supporting `strict: true`
from its [structured-output documentation](https://console.groq.com/docs/structured-outputs).
Free-tier access, model availability and quota depend on your Groq account; none
are assumed. Keep hosted keys server-side in `.env` or the environment.

With the backend running, call from another terminal:

```sh
curl --fail-with-body -X POST http://127.0.0.1:8000/api/v1/evaluations \
  -H "Content-Type: application/json" \
  --data-binary @examples/sample_evaluation.json
```

On Windows PowerShell, use `curl.exe` with the same arguments. Successful calls
return HTTP 200 with the unchanged public report schema. Each criterion causes
one independent actual AI call, including duplicates; no fixed criterion statuses
are used. Evaluation finishes before the response, with a unique UUID-derived ID.
There is no queue, persistence, automatic retry or mock fallback.

Alternatively, the smoke client validates the actual response schema, original
criteria, and sample references before printing the report:

```sh
python examples/smoke_sample.py
```

The server must already be running with the selected provider configured. This command has no
mock mode and exits unsuccessfully on an API error; it never fills in findings.
Use `--base-url` for a different backend address and `--timeout` for a longer wait
(default 600 seconds accommodates the three sample criteria on slower local hardware).

All providers implement `CriterionAIClient.assess`. Credentials are
server-only, excluded from settings serialization and repr. No repository URL,
author metadata, credentials or unrelated criteria are sent in the prompt; the
current criterion, milestone context and supplied untrusted excerpts are sent.
OpenAI storage is disabled with `store=false`; this does not claim zero provider
retention. Groq uses its own provider retention policy. Ollama inference goes to
the configured local server. HTTP/SDK clients are closed after the request.

The separate Python grounding validator checks exact criterion text, authorized
IDs, exact contiguous quotes, citation requirements, uncertainty disclosure and
known unsafe output patterns. AI-supplied URLs and extra output fields are rejected.
Whole cited records (including their titles) are checked for known evaluator
instructions, so a harmless fragment cannot launder an instruction-bearing record.
Activity-count-only excerpts cannot independently support completion. Recognizable
commit/file/PR/namespace references in AI prose must occur in cited source records;
funding-relationship assertions and self-asserted verification are rejected.
Known instructions attempting to waive human review are rejected in reasoning,
gaps, suggestions, and cited records; AI output cannot set the report's mandatory
`human_review_required: true` field.
Public references are rebuilt exclusively from retrieved records. Model reasoning
is labelled **AI interpretation, not verified fact**; quoted text establishes only
what the source says. These structural checks and targeted policy rules are not a
general semantic truth checker or a guarantee against every prompt-injection
paraphrase. Human review remains mandatory; reports grant no funding authority.

`supported`/`uncertain` require evidence citations; non-supported outcomes require
explicit gaps or ambiguities. Summaries count the actual validated outcomes and
retain uncertainty. Sample provenance and fixture limitations are always included.
AI-reported gaps appear in the criterion explanation and in limitations indexed by
criterion position, including duplicates; they are labelled as unverified AI output.
AI next steps are also explicitly labelled as suggestions for human review.
Successful zero-evidence retrieval may produce an honest limited report after AI
assessment; retrieval failures never become empty successful retrievals.

AI errors, invalid output, refusal, truncation and grounding rejection return
`EVALUATION_FAILED`/502; AI timeouts return the same code with 504. Invalid credentials
are provider failures, not successful evaluations. Missing AI configuration retains
the explicit error above. GitHub retrieval failures never use sample fallback.
Error responses contain no provider details or excerpts.

### Public GitHub evidence (BE-06)

Set `evidence_source` to `github` with an approved `https://github.com/owner/repo`
URL. For example, submit `examples/github_evaluation.json` to the same endpoint.
This retrieves live evidence and invokes the selected real AI provider; `sample`
continues to use only the local synthetic fixture.

Public repositories work without a token, subject to GitHub rate limits. Optional
`VERICOMMIT_GITHUB_TOKEN` (or `GITHUB_TOKEN`) is server-only; put it in your ignored
`.env` or environment. Private/internal repositories are outside this MVP scope,
even when a token could access them.

Retrieval covers repository metadata, recent default-branch commits, pull requests
in all states, releases, and checks/workflow runs for the newest retrieved commit.
Up to three commit details and two PR file lists supply changed-file metadata.
Patch fields returned by GitHub are discarded; raw files and full source files are
not downloaded. Reported check conclusions are not tests executed or independently
verified by VeriCommit.

Bounds: `VERICOMMIT_GITHUB_TIMEOUT_SECONDS=10` per request (maximum 30),
`VERICOMMIT_GITHUB_TOTAL_TIMEOUT_SECONDS=60` overall (maximum 120),
`VERICOMMIT_GITHUB_PAGE_SIZE=5` (maximum 20), `VERICOMMIT_GITHUB_MAX_PAGES=2`
(maximum 3), and `VERICOMMIT_GITHUB_MAX_REQUESTS=25` (maximum 100).
Each activity list is capped at five records; changed-file lists at 20 files.
Responses are capped at 1 MB each / 4 MB total; evidence content at 3,000 characters
per record / 30,000 total, and titles at 300 characters. Scope and truncation appear
in report limitations. Metadata-only or empty successful retrieval is not a failure.

Only constructed `https://api.github.com/repos/...` endpoints are requested.
Redirects, upstream pagination URLs, content URLs and external check detail URLs
are never fetched; local proxy environment settings are disabled. Links in reports
come from GitHub response fields and are restricted to the requested repository.
No automatic retries occur. Any actual HTTP/network/malformed-response failure
stops evaluation rather than returning a misleading partial success.

Missing/inaccessible repositories return `REPOSITORY_ACCESS_DENIED`/403. Rate limits,
other HTTP failures and malformed evidence return `EVIDENCE_RETRIEVAL_FAILED`/502;
retrieval timeouts use that code with 504. No tokens, upstream bodies or evidence
text are logged or included in public errors.

Server-side evaluation failure logs identify the component, exception category,
upstream HTTP status and allowlisted provider error code/type, with static troubleshooting
guidance. They do not include exception text, upstream bodies, authorization headers,
prompts or evidence. In particular, HTTP 429 with `insufficient_quota` requires
checking the API key's OpenAI project billing, credits and spending limits; it is
not fixed by changing grounding checks. Other 429 failures may indicate rate limits.

Verification uses mocked upstream HTTP through the real adapters and actual application
services:

```sh
python -m pytest -q tests/test_providers.py tests/test_ollama.py tests/test_grounding.py tests/test_ai_evaluations.py
```

**Live verification on 2026-10-17 reached OpenAI but failed with HTTP 429 /
`insufficient_quota`; no live report was generated and grounding was not reached.**
Mocked tests verify transport, evaluation, grounding, and report serialization,
not model judgment or resistance to all adversarial prompts. Ollama was not on PATH
and its local API was unavailable in this environment, so local inference has not
been verified. The smoke client above tests real inference once Ollama is running
with the selected model installed.

Invalid JSON, missing/null/wrong-type fields, blank required strings, empty or
invalid criteria, unsupported sources, and undocumented fields return HTTP 400
with the existing `error.code`/`error.message` envelope. URL-format/blank-URL
validation failures use `INVALID_REPOSITORY_URL`, including alongside generic
field errors; other request validation failures use `INVALID_REQUEST`. Validation
failures never invoke `evaluate`. Responses do not echo submitted values or
framework validation details. OpenAPI documents HTTP 400 instead of FastAPI's
default 422. Broader BE-10 safeguards remain future work.

## Internal evidence

`evidence/models.py` defines strict, immutable internal records separately from the
public schemas. Each record carries a stable `evidence_id`, actual `source`,
`source_id`, evidence kind, meaningful title, optional source URL/content, and
optional repository/commit/PR/release/author metadata. Missing metadata stays null;
URLs are validated syntactically and preserved, not fetched or proven authentic.

`evidence/normalization.py` provides pure adapters for GitHub-shaped commit,
pull-request, and release payloads. IDs are namespaced by source, repository, kind,
and the supplied upstream identifier. These adapters do not retrieve GitHub data.

`NormalizedEvidence.to_public_reference()` returns the existing `EvidenceReference`
with only `type`, `title`, and present `url`. The title carries the stable internal
reference; samples require a `Sample: ` label, including when their URL is null.
Missing genuine URLs remain null, with source-qualified stable references retained
in titles rather than fabricated links. No URLs, authors, timestamps, or findings are
invented. `EvidenceProvider.retrieve(request)` is the async boundary for sample and
future live providers, returning an `EvidenceCollection` with source and limitations.

### Deterministic sample provider

`services/sample_evidence.py` implements `EvidenceProvider.retrieve(request)` using
the packaged `fixtures/registration-demo-v1.json`. Every request explicitly using
`evidence_source: "sample"` selects this one fixed fixture, independent of project
name, repository URL, criterion wording, working directory, or time. No request
field or fixture-selection endpoint is added. The provider rejects `github` mode;
it is never an automatic fallback after a live failure.

The dataset contains four labelled, synthetic commit/PR/test/release-style excerpts,
an illustrative milestone, and explicit coverage limitations. Form notes supply
supporting material, invalid-input behavior has an evidence gap, and incomplete
test/release notes leave uncertainty for later evaluation. These are demo inputs,
not predetermined criterion results or claims about the submitted repository.
All bundled evidence URLs are null; no fake SHA, PR number, file path, or external
URL is created. Stable IDs use `sample:registration-demo-v1:<local-source-id>`.

Records validate on load; missing/unreadable, malformed, unsupported, duplicate-ID,
and mislabelled fixtures raise explicit internal errors rather than empty evidence
or substituted data. Genuine supplied URLs are preserved by the normalized models.
The fixture is included in installed packages and requires no network or credentials.

The FastAPI `get_evidence_provider` dependency is injected into the evaluation
service as `evidence_provider`. The configured evaluator awaits
`evidence_provider.retrieve(request)` before independently assessing criteria.
Without AI configuration, the unconfigured evaluator retains the honest HTTP 502
failure. Full source dispatch/live retrieval remains BE-06.

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

The sample provider implements D5's deterministic fixture selection without silent
fallback. Later report services must preserve D6's actual-source disclosure through
existing fields and
D7's distinction between insufficient evidence and retrieval/evaluation failures.
No additional public error or provenance fields are approved. The current handlers
cover validation, missing configuration, evidence retrieval failure, AI failure,
grounding rejection and AI timeouts. BE-10 owns remaining transport/security
safeguards beyond the bounded public GitHub provider.
The public MVP contract is finalized at the policy level. Synchronous execution,
ID uniqueness, criterion/result correlation, grounded AI output and report assembly
are implemented by the evaluation services and tested with mocked AI responses.
