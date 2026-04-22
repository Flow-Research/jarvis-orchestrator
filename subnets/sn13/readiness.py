#!/usr/bin/env python3
"""
SN13 readiness and minimum requirement gates.

The evaluator is intentionally pure: it does not call Bittensor, hit S3, touch
wallet files, or inspect real disk. Callers pass the observed runtime facts in,
and the function returns capability gates plus blocking reasons.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

DEFAULT_MINIMUM_REQUIREMENTS_PATH = Path(__file__).with_name("config") / "minimum_requirements.yaml"
DEFAULT_S3_AUTH_URL = "https://data-universe-api.api.macrocosmos.ai"


class ReadinessStatus(str, Enum):
    """Status of one readiness check."""

    PASS = "pass"
    WARN = "warn"
    BLOCKED = "blocked"


class SN13Capability(str, Enum):
    """Jarvis-owned capabilities. Operators own scrape capability."""

    SERVE_VALIDATORS = "can_serve_validators"
    INTAKE_OPERATOR_UPLOADS = "jarvis_can_intake_operator_uploads"
    EXPORT_UPSTREAM_S3 = "jarvis_can_export_upstream_s3"
    ARCHIVE_JARVIS_S3 = "jarvis_can_archive_to_jarvis_s3"


class ReadinessCheck(BaseModel):
    """A single readiness finding."""

    model_config = {"frozen": True}

    name: str
    status: ReadinessStatus
    message: str
    upstream_confirmed: bool = False


class SN13MinimumRequirements(BaseModel):
    """Jarvis-owned resource gates derived from the YAML profile."""

    model_config = {"frozen": True}

    python_min_version: str = "3.10"
    disk_free_gb_blocker: float = Field(default=10.0, ge=0)
    disk_free_gb_recommended: float = Field(default=50.0, ge=0)
    s3_auth_url_default: str = DEFAULT_S3_AUTH_URL

    @field_validator("python_min_version")
    @classmethod
    def validate_python_min_version(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
            raise ValueError("python_min_version must look like '3.10'")
        return value


class SN13RuntimeState(BaseModel):
    """Observed runtime facts supplied by CLI or tests."""

    model_config = {"frozen": True}

    python_version: str = Field(
        default_factory=lambda: f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    wallet_name: str | None = None
    wallet_hotkey: str | None = None
    hotkey_registered: bool = False
    listener_running: bool = False
    local_db_healthy: bool = False
    disk_free_gb: float | None = Field(default=None, ge=0)
    wallet_hotkey_can_sign: bool = False
    parquet_export_available: bool = False
    jarvis_archive_bucket_configured: bool = False
    listener_capture_count: int = Field(default=0, ge=0)
    listener_query_types: tuple[str, ...] = ()


class SN13ReadinessReport(BaseModel):
    """Final readiness decision for SN13."""

    model_config = {"frozen": True}

    requirements: SN13MinimumRequirements
    checks: tuple[ReadinessCheck, ...]
    capabilities: dict[SN13Capability, bool]

    @property
    def blockers(self) -> tuple[ReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.status == ReadinessStatus.BLOCKED)

    @property
    def warnings(self) -> tuple[ReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.status == ReadinessStatus.WARN)

    def can(self, capability: SN13Capability) -> bool:
        return self.capabilities.get(capability, False)


def load_minimum_requirements(
    path: str | Path = DEFAULT_MINIMUM_REQUIREMENTS_PATH,
) -> SN13MinimumRequirements:
    """Load Jarvis SN13 readiness requirements from YAML."""
    raw = yaml.safe_load(Path(path).read_text())
    upstream = raw.get("upstream_confirmed", {})
    economic = raw.get("jarvis_economic_gates", {})
    return SN13MinimumRequirements(
        python_min_version=str(upstream.get("python_min_version", "3.10")),
        disk_free_gb_blocker=float(economic.get("disk_free_gb_blocker", 10)),
        disk_free_gb_recommended=float(economic.get("disk_free_gb_recommended", 50)),
        s3_auth_url_default=str(upstream.get("s3_auth_url_default", DEFAULT_S3_AUTH_URL)),
    )


def evaluate_sn13_readiness(
    *,
    runtime: SN13RuntimeState,
    env: Mapping[str, str] | None = None,
    requirements: SN13MinimumRequirements | None = None,
) -> SN13ReadinessReport:
    """Evaluate whether Jarvis may serve validators and accept SN13 work."""
    env_values = env or os.environ
    req = requirements or load_minimum_requirements()
    checks: list[ReadinessCheck] = []

    python_ok = _version_tuple(runtime.python_version) >= _version_tuple(req.python_min_version)
    checks.append(
        ReadinessCheck(
            name="python_at_or_above_minimum",
            status=ReadinessStatus.PASS if python_ok else ReadinessStatus.BLOCKED,
            message=(
                f"Python {runtime.python_version} observed; "
                f"SN13 upstream requires >= {req.python_min_version}."
            ),
            upstream_confirmed=True,
        )
    )

    wallet_configured = bool(runtime.wallet_name and runtime.wallet_hotkey)
    checks.append(
        ReadinessCheck(
            name="wallet_configured",
            status=ReadinessStatus.PASS if wallet_configured else ReadinessStatus.BLOCKED,
            message=(
                "Wallet name and hotkey are configured."
                if wallet_configured
                else "Wallet name and hotkey are required."
            ),
            upstream_confirmed=True,
        )
    )

    checks.append(
        ReadinessCheck(
            name="hotkey_registered_on_subnet",
            status=ReadinessStatus.PASS if runtime.hotkey_registered else ReadinessStatus.BLOCKED,
            message=(
                "Hotkey is registered on SN13."
                if runtime.hotkey_registered
                else "The hotkey must be registered on SN13 before validators can score Jarvis."
            ),
            upstream_confirmed=True,
        )
    )

    checks.append(
        ReadinessCheck(
            name="listener_running_online",
            status=ReadinessStatus.PASS if runtime.listener_running else ReadinessStatus.BLOCKED,
            message=(
                "Online miner listener is running."
                if runtime.listener_running
                else "Offline mode cannot respond to validator requests."
            ),
            upstream_confirmed=True,
        )
    )

    checks.append(
        ReadinessCheck(
            name="local_db_healthy",
            status=ReadinessStatus.PASS if runtime.local_db_healthy else ReadinessStatus.BLOCKED,
            message=(
                "Canonical SQLite storage is healthy."
                if runtime.local_db_healthy
                else "Jarvis cannot intake operator uploads until canonical SQLite is healthy."
            ),
            upstream_confirmed=False,
        )
    )

    capture_count = runtime.listener_capture_count
    checks.append(
        ReadinessCheck(
            name="listener_capture_evidence_present",
            status=ReadinessStatus.PASS if capture_count > 0 else ReadinessStatus.WARN,
            message=(
                f"{capture_count} listener capture(s) recorded."
                if capture_count > 0
                else "No listener captures recorded yet. Live validator verification is still open."
            ),
            upstream_confirmed=False,
        )
    )

    observed_query_types = set(runtime.listener_query_types)
    required_query_types = {"GetMinerIndex", "GetDataEntityBucket", "GetContentsByBuckets"}
    missing_query_types = sorted(required_query_types - observed_query_types)
    checks.append(
        ReadinessCheck(
            name="listener_query_surface_observed",
            status=ReadinessStatus.PASS if not missing_query_types else ReadinessStatus.WARN,
            message=(
                "Observed listener query types: "
                + ", ".join(sorted(observed_query_types))
                if not missing_query_types
                else "Missing live capture evidence for query types: "
                + ", ".join(missing_query_types)
            ),
            upstream_confirmed=False,
        )
    )

    disk_ok = runtime.disk_free_gb is not None and runtime.disk_free_gb >= req.disk_free_gb_blocker
    disk_status = ReadinessStatus.PASS if disk_ok else ReadinessStatus.BLOCKED
    disk_message = (
        f"{runtime.disk_free_gb:.1f} GB free disk is above Jarvis blocker floor."
        if runtime.disk_free_gb is not None and disk_ok
        else (
            f"At least {req.disk_free_gb_blocker:.1f} GB free disk is required "
            "by Jarvis before accepting work."
        )
    )
    checks.append(
        ReadinessCheck(
            name="disk_above_blocker_floor",
            status=disk_status,
            message=disk_message,
            upstream_confirmed=False,
        )
    )

    disk_in_warning_range = (
        runtime.disk_free_gb is not None
        and req.disk_free_gb_blocker <= runtime.disk_free_gb < req.disk_free_gb_recommended
    )
    if disk_in_warning_range:
        checks.append(
            ReadinessCheck(
                name="disk_below_recommended_floor",
                status=ReadinessStatus.WARN,
                message=(
                    f"{runtime.disk_free_gb:.1f} GB free disk is below "
                    f"Jarvis recommended floor of {req.disk_free_gb_recommended:.1f} GB."
                ),
                upstream_confirmed=False,
            )
        )

    s3_auth_url_configured = bool(
        _first_present(env_values, ("JARVIS_SN13_S3_AUTH_URL", "S3_AUTH_URL"))
        or req.s3_auth_url_default
    )
    checks.append(
        ReadinessCheck(
            name="s3_auth_url_configured",
            status=ReadinessStatus.PASS if s3_auth_url_configured else ReadinessStatus.BLOCKED,
            message="S3 auth URL is configured for presigned upload flow.",
            upstream_confirmed=True,
        )
    )

    checks.append(
        ReadinessCheck(
            name="wallet_hotkey_can_sign",
            status=(
                ReadinessStatus.PASS
                if runtime.wallet_hotkey_can_sign
                else ReadinessStatus.BLOCKED
            ),
            message=(
                "Wallet hotkey can sign S3 auth commitments."
                if runtime.wallet_hotkey_can_sign
                else "S3 upload requires the miner hotkey to sign the auth commitment."
            ),
            upstream_confirmed=True,
        )
    )

    checks.append(
        ReadinessCheck(
            name="parquet_export_available",
            status=(
                ReadinessStatus.PASS
                if runtime.parquet_export_available
                else ReadinessStatus.BLOCKED
            ),
            message=(
                "Local parquet export is available."
                if runtime.parquet_export_available
                else "S3 upload requires local parquet export artifacts first."
            ),
            upstream_confirmed=True,
        )
    )

    archive_bucket_configured = runtime.jarvis_archive_bucket_configured or bool(
        _first_present(
            env_values,
            (
                "JARVIS_SN13_ARCHIVE_S3_BUCKET",
                "JARVIS_ARCHIVE_S3_BUCKET",
            ),
        )
    )
    checks.append(
        ReadinessCheck(
            name="jarvis_archive_bucket_configured",
            status=ReadinessStatus.PASS if archive_bucket_configured else ReadinessStatus.WARN,
            message=(
                "Jarvis-owned archive S3 bucket is configured."
                if archive_bucket_configured
                else (
                    "Jarvis archive requires JARVIS_SN13_ARCHIVE_S3_BUCKET "
                    "or an explicit runtime archive bucket setting."
                )
            ),
            upstream_confirmed=False,
        )
    )

    can_serve_validators = all(
        _check_passed(checks, name)
        for name in (
            "python_at_or_above_minimum",
            "wallet_configured",
            "hotkey_registered_on_subnet",
            "listener_running_online",
            "local_db_healthy",
            "disk_above_blocker_floor",
        )
    )
    can_intake_operator_uploads = all(
        _check_passed(checks, name)
        for name in (
            "local_db_healthy",
            "disk_above_blocker_floor",
        )
    )
    capabilities = {
        SN13Capability.SERVE_VALIDATORS: can_serve_validators,
        SN13Capability.INTAKE_OPERATOR_UPLOADS: can_intake_operator_uploads,
        SN13Capability.EXPORT_UPSTREAM_S3: can_serve_validators
        and s3_auth_url_configured
        and runtime.wallet_hotkey_can_sign
        and runtime.parquet_export_available,
        SN13Capability.ARCHIVE_JARVIS_S3: archive_bucket_configured
        and runtime.parquet_export_available,
    }

    return SN13ReadinessReport(
        requirements=req,
        checks=tuple(checks),
        capabilities=capabilities,
    )


def _present(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def _first_present(env: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if _present(env, name):
            return env[name]
    return None


def _check_passed(checks: list[ReadinessCheck], name: str) -> bool:
    return any(check.name == name and check.status == ReadinessStatus.PASS for check in checks)


def _version_tuple(value: str) -> tuple[int, int]:
    major, minor, *_ = value.split(".")
    return int(major), int(minor)
