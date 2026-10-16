"""Exercise the documented startup command over a real loopback HTTP connection."""

import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


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
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "vericommit_backend"],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    started = False
    try:
        deadline = time.monotonic() + 15
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
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
    assert started, f"API failed to start and serve health:\n{output}"
