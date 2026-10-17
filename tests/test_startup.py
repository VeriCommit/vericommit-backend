"""Exercise the documented startup command over a real loopback HTTP connection."""

import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


def test_module_starts_uvicorn_and_serves_health(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    environment = {
        **os.environ,
        "VERICOMMIT_HOST": "127.0.0.1",
        "VERICOMMIT_PORT": str(port),
        "VERICOMMIT_RELOAD": "false",
        "VERICOMMIT_LOG_LEVEL": "info",
        "VERICOMMIT_OPENAI_API_KEY": "",
        "OPENAI_API_KEY": "",
        "VERICOMMIT_AI_PROVIDER": "openai",
    }
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "vericommit_backend"],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    started = False
    try:
        # Cold imports of FastAPI/Pydantic and the AI SDK can exceed 15 seconds
        # on Windows. This is startup allowance, not an upstream-call timeout.
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=0.5
                ) as response:
                    assert response.status == 200
                    assert json.load(response) == {"status": "ok"}
                    started = True
                    break
            except (URLError, TimeoutError):
                time.sleep(0.1)
        if started:
            # Real loopback POST: missing credentials must never produce findings.
            dataset = SampleEvidenceProvider().load_dataset()
            payload = {
                "project_name": "Sample smoke test",
                "repository_url": "https://github.com/VeriCommit/vericommit-backend",
                "milestone": dataset.milestone.model_dump(mode="json"),
                "evidence_source": "sample",
            }
            request = Request(
                f"http://127.0.0.1:{port}/api/v1/evaluations",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urlopen(request, timeout=10)
            except HTTPError as exc:
                assert exc.code == 502
                assert json.load(exc) == {
                    "error": {
                        "code": "EVALUATION_FAILED",
                        "message": "The evaluation service is not configured. No evaluation was performed.",
                    }
                }
            else:
                raise AssertionError(
                    "Missing AI credentials produced a successful response."
                )
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
    assert started, f"API failed to start and serve health:\n{output}"
