"""Validated settings for the Jarvis workstream API runtime."""

from __future__ import annotations

import json
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
    operator_secrets_json: str | None = None
    max_clock_skew_seconds: int = Field(default=300, ge=30, le=3600)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> WorkstreamAPISettings:
        values = env or os.environ
        return cls(
            host=values.get("JARVIS_WORKSTREAM_HOST", "127.0.0.1"),
            port=int(values.get("JARVIS_WORKSTREAM_PORT", "8787")),
            workstream_db_path=Path(
                values.get("JARVIS_WORKSTREAM_DB_PATH", "data/workstream.sqlite3")
            ),
            sn13_db_path=Path(
                values.get("JARVIS_SN13_DB_PATH", "subnets/sn13/data/sn13.sqlite3")
            ),
            require_auth=(values.get("JARVIS_WORKSTREAM_REQUIRE_AUTH", "1") != "0"),
            operator_secrets_json=values.get("JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON"),
            max_clock_skew_seconds=int(
                values.get("JARVIS_WORKSTREAM_MAX_CLOCK_SKEW_SECONDS", "300")
            ),
        )

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> WorkstreamAPISettings:
        if self.operator_secrets_json:
            parsed = self.operator_secrets
            if not parsed:
                raise ValueError(
                    "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON must include at least one operator"
                )
        elif self.require_auth:
            raise ValueError(
                "Workstream API auth is required. Set "
                "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON. For local-only unsigned "
                "development, set JARVIS_WORKSTREAM_REQUIRE_AUTH=0."
            )
        return self

    @property
    def operator_secrets(self) -> dict[str, str]:
        if self.operator_secrets_json:
            try:
                parsed = json.loads(self.operator_secrets_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON: {exc.msg}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError("JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON must be a JSON object")
            secrets: dict[str, str] = {}
            for operator_id, secret in parsed.items():
                operator_id_text = str(operator_id).strip()
                secret_text = str(secret).strip()
                if not operator_id_text or not secret_text:
                    raise ValueError(
                        "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON must map non-empty "
                        "operator IDs to non-empty secrets"
                    )
                secrets[operator_id_text] = secret_text
            return secrets
        return {}

    @property
    def configured_operator_count(self) -> int:
        return len(self.operator_secrets)

    @property
    def configured_operator_ids(self) -> list[str]:
        return sorted(self.operator_secrets.keys())


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
