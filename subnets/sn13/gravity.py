#!/usr/bin/env python3
"""
Real Gravity/Dynamic Desirability retrieval and cache management for SN13.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, field_validator

from .desirability import DesirabilitySnapshot
from .models import ensure_utc

GRAVITY_TOTAL_URL = "https://raw.githubusercontent.com/macrocosm-os/gravity/main/total.json"
GRAVITY_CACHE_FILENAME = "total.json"
GRAVITY_METADATA_FILENAME = "metadata.json"


class GravityFetchError(RuntimeError):
    """Raised when Jarvis cannot retrieve or validate a Gravity payload."""


class GravityCacheMetadata(BaseModel):
    """Metadata describing a locally cached Gravity snapshot."""

    model_config = {"frozen": True}

    fetched_at: datetime
    source_url: str
    record_count: int = Field(..., ge=0)
    sha256: str = Field(..., min_length=64, max_length=64)

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class GravityCacheResult(BaseModel):
    """Result returned after writing or loading a Gravity cache."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    snapshot: DesirabilitySnapshot
    cache_path: Path
    metadata_path: Path
    metadata: GravityCacheMetadata


def default_gravity_cache_dir() -> Path:
    """Return the default runtime cache directory for live Gravity data."""
    return Path(__file__).resolve().parent / "cache" / "gravity"


def gravity_cache_file(cache_dir: Path | None = None) -> Path:
    """Return the cached `total.json` path."""
    return (cache_dir or default_gravity_cache_dir()) / GRAVITY_CACHE_FILENAME


def gravity_metadata_file(cache_dir: Path | None = None) -> Path:
    """Return the cached metadata path."""
    return (cache_dir or default_gravity_cache_dir()) / GRAVITY_METADATA_FILENAME


def fetch_gravity_records(
    *,
    url: str = GRAVITY_TOTAL_URL,
    timeout_seconds: int = 30,
) -> list[dict[str, Any]]:
    """Fetch the latest public Gravity aggregate jobs from GitHub raw content."""
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "jarvis-orchestrator-sn13",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise GravityFetchError(f"Gravity request failed with HTTP {exc.code}: {url}") from exc
    except URLError as exc:
        raise GravityFetchError(f"Gravity request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise GravityFetchError(f"Gravity request timed out after {timeout_seconds}s") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GravityFetchError("Gravity response was not valid JSON") from exc

    if not isinstance(payload, list):
        raise GravityFetchError("Gravity response must be a JSON list of jobs")
    if not all(isinstance(item, dict) for item in payload):
        raise GravityFetchError("Gravity response contains a non-object job")
    return payload


def write_gravity_cache(
    records: list[dict[str, Any]],
    *,
    cache_dir: Path | None = None,
    source_url: str = GRAVITY_TOTAL_URL,
    fetched_at: datetime | None = None,
) -> GravityCacheResult:
    """Validate and write a Gravity records list to the local cache atomically."""
    target_dir = cache_dir or default_gravity_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    fetched_time = ensure_utc(fetched_at or datetime.now(timezone.utc).replace(microsecond=0))
    raw = json.dumps(records, indent=2, sort_keys=True).encode("utf-8")
    metadata = GravityCacheMetadata(
        fetched_at=fetched_time,
        source_url=source_url,
        record_count=len(records),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    snapshot = DesirabilitySnapshot.from_upstream_records(
        records,
        source_ref=source_url,
        retrieved_at=fetched_time,
    )

    cache_path = gravity_cache_file(target_dir)
    metadata_path = gravity_metadata_file(target_dir)
    cache_tmp = cache_path.with_suffix(".json.tmp")
    metadata_tmp = metadata_path.with_suffix(".json.tmp")
    cache_tmp.write_bytes(raw)
    metadata_tmp.write_text(metadata.model_dump_json(indent=2))
    cache_tmp.replace(cache_path)
    metadata_tmp.replace(metadata_path)
    return GravityCacheResult(
        snapshot=snapshot,
        cache_path=cache_path,
        metadata_path=metadata_path,
        metadata=metadata,
    )


def refresh_gravity_cache(
    *,
    cache_dir: Path | None = None,
    url: str = GRAVITY_TOTAL_URL,
    timeout_seconds: int = 30,
) -> GravityCacheResult:
    """Fetch real Gravity jobs and update the local cache."""
    records = fetch_gravity_records(url=url, timeout_seconds=timeout_seconds)
    return write_gravity_cache(records, cache_dir=cache_dir, source_url=url)


def load_gravity_cache(*, cache_dir: Path | None = None) -> GravityCacheResult:
    """Load the local Gravity cache and metadata."""
    cache_path = gravity_cache_file(cache_dir)
    metadata_path = gravity_metadata_file(cache_dir)
    if not cache_path.exists():
        raise FileNotFoundError(
            f"No Gravity cache found at {cache_path}. "
            "Run `jarvis-miner sn13 dd refresh` or pass `--dd-file`."
        )

    records = json.loads(cache_path.read_text())
    if not isinstance(records, list):
        raise GravityFetchError(f"Cached Gravity file is not a JSON list: {cache_path}")

    if metadata_path.exists():
        metadata = GravityCacheMetadata.model_validate_json(metadata_path.read_text())
        retrieved_at = metadata.fetched_at
        source_ref = metadata.source_url
    else:
        raw = json.dumps(records, indent=2, sort_keys=True).encode("utf-8")
        metadata = GravityCacheMetadata(
            fetched_at=datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc),
            source_url=str(cache_path),
            record_count=len(records),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        retrieved_at = metadata.fetched_at
        source_ref = str(cache_path)

    snapshot = DesirabilitySnapshot.from_upstream_records(
        records,
        source_ref=source_ref,
        retrieved_at=retrieved_at,
    )
    return GravityCacheResult(
        snapshot=snapshot,
        cache_path=cache_path,
        metadata_path=metadata_path,
        metadata=metadata,
    )
