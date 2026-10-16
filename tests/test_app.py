"""Application, configuration and server startup checks."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vericommit_backend.__main__ import main
from vericommit_backend.config import Settings
from vericommit_backend.main import app, create_app


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch, tmp_path):
    # Tests do not depend on a developer's shell settings or local .env file.
    for name in ("APP_NAME", "HOST", "PORT", "RELOAD", "LOG_LEVEL"):
        monkeypatch.delenv(f"VERICOMMIT_{name}", raising=False)
    monkeypatch.chdir(tmp_path)


def test_asgi_app_starts_and_health_is_successful():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_app_factory_uses_settings_without_exposing_them():
    settings = Settings(app_name="VeriCommit Test", port=9000)
    application = create_app(settings)
    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/openapi.json").json()["info"]["title"] == "VeriCommit Test"
    assert application.state.settings is settings


def test_settings_defaults():
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.reload is False
    assert settings.log_level == "info"


def test_environment_overrides_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "VERICOMMIT_APP_NAME=Local Demo\n"
        "VERICOMMIT_PORT=8100\n"
        "VERICOMMIT_RELOAD=true\n"
        "UNRELATED_SETTING=ignored\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VERICOMMIT_PORT", "8200")
    settings = Settings()
    assert settings.app_name == "Local Demo"
    assert settings.port == 8200
    assert settings.reload is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PORT", "0"),
        ("PORT", "65536"),
        ("PORT", "not-an-integer"),
        ("RELOAD", "not-a-boolean"),
        ("LOG_LEVEL", "invalid"),
        ("HOST", "  "),
        ("APP_NAME", "  "),
    ],
)
def test_invalid_environment_prevents_app_creation(monkeypatch, name, value):
    monkeypatch.setenv(f"VERICOMMIT_{name}", value)
    with pytest.raises(ValidationError):
        create_app()


def test_configuration_error_does_not_echo_input(monkeypatch):
    marker = "sensitive-input-placeholder"
    monkeypatch.setenv("VERICOMMIT_PORT", marker)
    with pytest.raises(ValidationError) as exc_info:
        create_app()
    assert marker not in str(exc_info.value)


def test_uvicorn_entry_point_uses_environment(monkeypatch):
    monkeypatch.setenv("VERICOMMIT_HOST", "127.0.0.1")
    monkeypatch.setenv("VERICOMMIT_PORT", "8100")
    monkeypatch.setenv("VERICOMMIT_RELOAD", "true")
    monkeypatch.setenv("VERICOMMIT_LOG_LEVEL", "debug")
    with patch("vericommit_backend.__main__.uvicorn.run") as run:
        main()
    run.assert_called_once_with(
        "vericommit_backend.main:app",
        host="127.0.0.1",
        port=8100,
        reload=True,
        log_level="debug",
    )
