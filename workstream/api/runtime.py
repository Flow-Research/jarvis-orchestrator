"""Default runtime wiring for the Jarvis workstream API."""

from __future__ import annotations

import os

from fastapi import FastAPI

from subnets.sn13.api_adapter import SN13OperatorIntakeAdapter, SN13OperatorStatsAdapter
from subnets.sn13.storage import SQLiteStorage
from subnets.sn13.tasks import SN13OperatorRuntime
from workstream.sqlite_store import SQLiteWorkstream

from .app import create_workstream_app
from .auth import HMACOperatorAuthenticator
from .settings import WorkstreamAPISettings, load_workstream_api_settings


def runtime_configuration(env: dict[str, str] | None = None) -> dict[str, object]:
    """Describe the default runtime wiring without starting the API server."""
    values = env or os.environ
    config_error: str | None = None
    try:
        settings = load_workstream_api_settings(values)
    except ValueError as exc:
        config_error = str(exc)
        settings = WorkstreamAPISettings.from_env(
            {
                **values,
                "JARVIS_OPERATOR_REQUIRE_AUTH": "0",
            }
        )

    return {
        "host": settings.host,
        "port": settings.port,
        "workstream_db_path": str(settings.workstream_db_path),
        "sn13_db_path": str(settings.sn13_db_path),
        "auth_required": settings.require_auth,
        "configured_operator_count": settings.configured_operator_count,
        "configured_operator_ids": settings.configured_operator_ids,
        "max_clock_skew_seconds": settings.max_clock_skew_seconds,
        "config_error": config_error,
    }


def create_default_app(env: dict[str, str] | None = None) -> FastAPI:
    """Create the default single-node Jarvis workstream API app from environment."""
    settings = load_workstream_api_settings(env or os.environ)
    workstream = SQLiteWorkstream(settings.workstream_db_path)
    sn13_storage = SQLiteStorage(settings.sn13_db_path)
    sn13_runtime = SN13OperatorRuntime(storage=sn13_storage)
    authenticator = _authenticator_from_settings(settings)

    return create_workstream_app(
        workstream=workstream,
        intake=SN13OperatorIntakeAdapter(runtime=sn13_runtime, workstream=workstream),
        stats=SN13OperatorStatsAdapter(storage=sn13_storage),
        authenticator=authenticator.authenticate if authenticator else None,
    )


def _authenticator_from_settings(
    settings: WorkstreamAPISettings,
) -> HMACOperatorAuthenticator | None:
    if settings.require_auth:
        return HMACOperatorAuthenticator(
            secrets=settings.operator_secrets,
            max_clock_skew_seconds=settings.max_clock_skew_seconds,
        )
    return None
