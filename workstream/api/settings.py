"""Validated settings for the Flow Workstream API runtime."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator


class WorkstreamAPISettings(BaseModel):
    """Single-node workstream API configuration loaded from environment."""

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8787, ge=1, le=65535)
    workstream_db_path: Path = Path("data/workstream.sqlite3")
    sn13_db_path: Path = Path("subnets/sn13/data/sn13.sqlite3")
    require_auth: bool = True
    garden_service_auth_token: str | None = None
    garden_base_url: str | None = None
    garden_auth_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    garden_require_active_session: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> WorkstreamAPISettings:
        values = env or os.environ

        return cls(
            host=values.get("JARVIS_WORKSTREAM_HOST", "127.0.0.1"),
            port=int(values.get("JARVIS_WORKSTREAM_PORT", "8787")),
            workstream_db_path=Path(
                values.get("JARVIS_WORKSTREAM_DB_PATH", "data/workstream.sqlite3")
            ),
            sn13_db_path=Path(values.get("JARVIS_SN13_DB_PATH", "subnets/sn13/data/sn13.sqlite3")),
            require_auth=(values.get("JARVIS_WORKSTREAM_REQUIRE_AUTH", "1") != "0"),
            garden_service_auth_token=_blank_to_none(values.get("GARDEN_SERVICE_AUTH_TOKEN")),
            garden_base_url=_normalize_base_url(values.get("GARDEN_BASE_URL")),
            garden_auth_timeout_seconds=float(
                values.get("GARDEN_AUTH_TIMEOUT_SECONDS", "5")
            ),
            garden_require_active_session=(
                values.get("GARDEN_REQUIRE_ACTIVE_SESSION", "0") == "1"
            ),
        )

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> WorkstreamAPISettings:
        if self.require_auth and not self.garden_service_auth_token:
            raise ValueError(
                "Workstream API auth is required. Set GARDEN_SERVICE_AUTH_TOKEN."
            )
        if self.require_auth and not self.garden_base_url:
            raise ValueError(
                "Workstream API auth is required. Set GARDEN_BASE_URL so "
                "Workstream can call Garden's internal auth verifier."
            )
        return self

    @property
    def auth_provider(self) -> str:
        return "garden" if self.require_auth else "disabled"

    @property
    def garden_auth_configured(self) -> bool:
        return bool(self.garden_service_auth_token and self.garden_base_url)

    @property
    def garden_auth_verify_url(self) -> str | None:
        if not self.garden_base_url:
            return None
        return f"{self.garden_base_url}/api/internal/auth/verify"


def load_workstream_api_settings(
    env: dict[str, str] | None = None,
) -> WorkstreamAPISettings:
    """Load validated workstream settings or raise a readable configuration error."""
    try:
        return WorkstreamAPISettings.from_env(env)
    except ValidationError as exc:
        messages = []
        for error in exc.errors():
            message = error.get("msg")
            if message:
                text = str(message)
                if text.startswith("Value error, "):
                    text = text.removeprefix("Value error, ")
                messages.append(text)
        raise ValueError("; ".join(messages) or str(exc)) from exc


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_base_url(value: str | None) -> str | None:
    normalized = _blank_to_none(value)
    if normalized is None:
        return None
    return normalized.rstrip("/")
