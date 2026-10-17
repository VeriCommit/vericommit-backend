# Windows MVP demo (BE-12)

Use hosted Groq on both 4 GB and 8 GB machines: only the Python backend runs
locally. No local inference, Ollama installation, GPU or model-weight download is
required. The application default remains OpenAI for compatibility; select Groq
explicitly below. OpenAI and Ollama remain optional providers.

Existing `.env` credentials are loaded automatically and must be preserved.
On a new checkout only, create `.env` from `.env.example` and configure the Groq key
locally. Never put keys in frontend settings, commands committed to Git or screenshots.
`openai/gpt-oss-120b` has passed genuine inference tests; model access/free-tier
quota remain account-dependent, and `VERICOMMIT_GROQ_MODEL` is configurable.

## Git Bash — from the repository root

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -e ".[dev]"
export VERICOMMIT_AI_PROVIDER=groq
export VERICOMMIT_GROQ_MODEL=openai/gpt-oss-120b
export VERICOMMIT_AI_TIMEOUT_SECONDS=120
export VERICOMMIT_CORS_ORIGINS='["http://localhost:3000"]'
python -m vericommit_backend
```

## PowerShell — from the repository root

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:VERICOMMIT_AI_PROVIDER = "groq"
$env:VERICOMMIT_GROQ_MODEL = "openai/gpt-oss-120b"
$env:VERICOMMIT_AI_TIMEOUT_SECONDS = "120"
$env:VERICOMMIT_CORS_ORIGINS = '["http://localhost:3000"]'
python -m vericommit_backend
```

In a second terminal, activate the same environment and run:

```text
python examples/smoke_sample.py --summary
python examples/smoke_github.py --summary
```

These call the real public endpoint, verify `/health`, POST/Content-Type/Accept
browser preflight, a rejected invalid request, and the report. A successful
summary requires human review, original criterion order/wording, source disclosure
and traceable references. Sample references must match the labelled fixture,
including explicit nullable URLs. GitHub reference scope/shape is checked by the
client; the server verifies citations against its actual retrieved snapshot.
No provider is mocked by these commands. Exit code 0 means verification passed;
1 means failure, with only sanitized diagnostics. `--base-url`, `--origin` and
`--timeout` are configurable. Omit `--summary` to print the validated report.

For a bounded public demo, the backend can additionally use
`VERICOMMIT_GITHUB_PAGE_SIZE=2`, `VERICOMMIT_GITHUB_MAX_PAGES=1`, and
`VERICOMMIT_GITHUB_MAX_REQUESTS=12`. Anonymous GitHub access is supported;
`VERICOMMIT_GITHUB_TOKEN` is optional and server-only.

Fixtures: `examples/sample_evaluation.json`, `examples/github_evaluation.json`,
and `examples/invalid_evaluation.json`. Submit them as JSON to
`POST http://127.0.0.1:8000/api/v1/evaluations`; the invalid fixture must return
400 / `INVALID_REQUEST`. API documentation is at `/docs` and `/openapi.json`.

## Repeatable checks (no live providers)

```text
python -m pytest
python -m ruff check .
python -m ruff format --check .
git diff --check
```

Tests mock upstream HTTP and block accidental live GitHub/AI requests. CI runs
on Linux/Windows and Python 3.12/3.14. Provider failures remain errors; successful
but evidence-poor retrieval can produce an honest limited report. Sample mode is
always synthetic. Every report requires human review and grants no approval or
funding authority. No persistent funding/ownership administration is implemented.

Known limits: public repositories only; bounded recent activity, not complete
source/history; no code/test execution; rule-based grounding is not a semantic
truth guarantee; provider quota, latency and conservative grounding may reject
otherwise valid requests. Both target computers still need their own hands-on
smoke run, and the frontend lead must confirm the actual browser integration.
The approved public API baseline and funding/privacy boundaries remain unchanged.
