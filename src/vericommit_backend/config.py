"""Validated application and local server settings."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERICOMMIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="VeriCommit", min_length=1)
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = (
        "info"
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERICOMMIT_OPENAI_API_KEY", "OPENAI_API_KEY"),
        exclude=True,
        repr=False,
    )
    ai_provider: Literal["openai", "ollama", "groq"] = "openai"
    ai_model: str = Field(default="gpt-4o-mini", min_length=1)
    ai_timeout_seconds: float = Field(default=30, gt=0, le=300)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = Field(default="qwen2.5:3b", min_length=1)
    ollama_timeout_seconds: float = Field(default=120, gt=0, le=300)
    groq_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERICOMMIT_GROQ_API_KEY", "GROQ_API_KEY"),
        exclude=True,
        repr=False,
    )
    groq_model: str | None = Field(default=None, min_length=1)
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERICOMMIT_GITHUB_TOKEN", "GITHUB_TOKEN"),
        exclude=True,
        repr=False,
    )
    github_timeout_seconds: float = Field(default=10, gt=0, le=30)
    github_total_timeout_seconds: float = Field(default=60, gt=0, le=120)
    github_page_size: int = Field(default=5, ge=1, le=20)
    github_max_pages: int = Field(default=2, ge=1, le=3)
    github_max_requests: int = Field(default=25, ge=1, le=100)

    @field_validator(
        "openai_api_key", "groq_api_key", "groq_model", "github_token", mode="before"
    )
    @classmethod
    def empty_key_is_unconfigured(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("ollama_base_url")
    @classmethod
    def valid_ollama_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or "?" in value
            or "#" in value
            or any(char.isspace() or ord(char) < 32 for char in value)
        ):
            raise ValueError("must be an HTTP(S) base URL without credentials or query")
        # Accessing port also validates invalid/out-of-range port specifications.
        _ = parts.port
        return value.rstrip("/")

    @property
    def evaluation_timeout_seconds(self) -> float:
        return (
            self.ollama_timeout_seconds
            if self.ai_provider == "ollama"
            else self.ai_timeout_seconds
        )
