"""Structured protocol observation utilities for SN13 listener experiments."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


MAX_DEPTH = 5
MAX_ITEMS = 25


@dataclass
class QueryObservation:
    """Serializable capture of one validator request as seen by Jarvis."""

    query_id: str
    timestamp: str
    query_type: str
    validator_hotkey: str
    synapse_type: str
    timeout_seconds: float | None
    latency_ms: float | None
    payload: dict[str, Any]
    payload_schema: dict[str, Any]
    response_payload: dict[str, Any]
    response_schema: dict[str, Any]
    dendrite: dict[str, Any]
    axon: dict[str, Any]
    public_attributes: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary for persistence."""
        return asdict(self)


class ProtocolObserver:
    """Persists inbound query captures and keeps lightweight aggregate stats."""

    def __init__(self, capture_dir: str | Path = "listener/captures", recent_limit: int = 200):
        self.capture_dir = Path(capture_dir)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.recent_limit = recent_limit
        self.events_file = self.capture_dir / "queries.jsonl"
        self.summary_file = self.capture_dir / "summary.json"
        self._counts_by_type: Counter[str] = Counter()
        self._counts_by_validator: Counter[str] = Counter()
        self._recent: list[dict[str, Any]] = []

    def record(
        self,
        *,
        query_type: str,
        synapse: Any,
        response_payload: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        notes: list[str] | None = None,
        extra: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> QueryObservation:
        """Capture one query and persist both raw and summarized views."""
        timestamp = datetime.now(timezone.utc)
        query_id = f"{timestamp.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"

        public_attrs = extract_public_attributes(synapse)
        dendrite = json_safe(public_attrs.get("dendrite", {}))
        axon = json_safe(public_attrs.get("axon", {}))
        payload = extract_payload(public_attrs)
        response_payload = json_safe(response_payload or {})

        observation = QueryObservation(
            query_id=query_id,
            timestamp=timestamp.isoformat(),
            query_type=query_type,
            validator_hotkey=extract_validator_hotkey(synapse, public_attrs),
            synapse_type=type(synapse).__name__,
            timeout_seconds=extract_timeout_seconds(synapse, public_attrs),
            latency_ms=round(latency_ms, 3) if latency_ms is not None else None,
            payload=payload,
            payload_schema=describe_schema(payload),
            response_payload=response_payload,
            response_schema=describe_schema(response_payload),
            dendrite=dendrite if isinstance(dendrite, dict) else {"value": dendrite},
            axon=axon if isinstance(axon, dict) else {"value": axon},
            public_attributes=public_attrs,
            notes=notes or [],
            extra=json_safe(extra or {}),
            error=error,
        )

        self._persist_observation(observation)
        return observation

    def format_summary(self) -> str:
        """Return a short human-readable summary for console output."""
        if not self._counts_by_type:
            return "No queries captured yet."

        parts = [f"{query_type}={count}" for query_type, count in sorted(self._counts_by_type.items())]
        return f"Captured {sum(self._counts_by_type.values())} queries | " + ", ".join(parts)

    def _persist_observation(self, observation: QueryObservation) -> None:
        event = observation.to_dict()
        day_dir = self.capture_dir / observation.timestamp[:10]
        day_dir.mkdir(parents=True, exist_ok=True)
        event_path = day_dir / f"{observation.query_id}.json"
        event_path.write_text(json.dumps(event, indent=2, sort_keys=True), encoding="utf-8")

        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True))
            handle.write("\n")

        self._counts_by_type.update([observation.query_type])
        self._counts_by_validator.update([observation.validator_hotkey])

        self._recent.append(
            {
                "query_id": observation.query_id,
                "timestamp": observation.timestamp,
                "query_type": observation.query_type,
                "validator_hotkey": observation.validator_hotkey,
                "latency_ms": observation.latency_ms,
                "timeout_seconds": observation.timeout_seconds,
                "event_path": str(event_path),
            }
        )
        self._recent = self._recent[-self.recent_limit :]

        summary = {
            "capture_dir": str(self.capture_dir),
            "total_queries": sum(self._counts_by_type.values()),
            "counts_by_query_type": dict(sorted(self._counts_by_type.items())),
            "counts_by_validator": dict(sorted(self._counts_by_validator.items())),
            "recent_queries": self._recent,
        }
        self.summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def extract_payload(public_attrs: dict[str, Any]) -> dict[str, Any]:
    """Keep likely request fields while excluding transport metadata."""
    ignored = {
        "axon",
        "body_hash",
        "computed_body_hash",
        "dendrite",
        "header_size",
        "name",
        "required_hash_fields",
        "timeout",
        "total_size",
    }
    payload = {
        key: value
        for key, value in public_attrs.items()
        if key not in ignored and not key.endswith("_headers")
    }
    return json_safe(payload) if isinstance(json_safe(payload), dict) else {"value": json_safe(payload)}


def extract_public_attributes(value: Any) -> dict[str, Any]:
    """Extract non-callable public attributes from an arbitrary object."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}

    attrs: dict[str, Any] = {}
    for attr in dir(value):
        if attr.startswith("_"):
            continue
        try:
            item = getattr(value, attr)
        except Exception as exc:
            attrs[attr] = f"<error: {type(exc).__name__}>"
            continue
        if callable(item):
            continue
        attrs[attr] = json_safe(item)
    return attrs


def extract_validator_hotkey(synapse: Any, public_attrs: dict[str, Any] | None = None) -> str:
    """Best-effort extraction of the caller hotkey."""
    public_attrs = public_attrs or extract_public_attributes(synapse)
    dendrite = public_attrs.get("dendrite")
    if isinstance(dendrite, dict):
        hotkey = dendrite.get("hotkey")
        if hotkey:
            return str(hotkey)

    for key in ("validator_hotkey", "hotkey"):
        value = public_attrs.get(key)
        if value:
            return str(value)
    return "unknown"


def extract_timeout_seconds(synapse: Any, public_attrs: dict[str, Any] | None = None) -> float | None:
    """Best-effort extraction of any timeout carried on the request."""
    public_attrs = public_attrs or extract_public_attributes(synapse)
    candidates = [public_attrs.get("timeout")]

    dendrite = public_attrs.get("dendrite")
    if isinstance(dendrite, dict):
        candidates.extend(
            [
                dendrite.get("timeout"),
                dendrite.get("timeout_seconds"),
                dendrite.get("process_time"),
            ]
        )

    for candidate in candidates:
        if candidate in (None, "", "None"):
            continue
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


def json_safe(value: Any, *, depth: int = 0) -> Any:
    """Convert nested objects into JSON-safe values for persistence."""
    if depth >= MAX_DEPTH:
        return f"<max_depth:{type(value).__name__}>"

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        items = list(value.items())[:MAX_ITEMS]
        return {str(key): json_safe(item, depth=depth + 1) for key, item in items}

    if isinstance(value, (list, tuple, set)):
        items = list(value)[:MAX_ITEMS]
        return [json_safe(item, depth=depth + 1) for item in items]

    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return json_safe(value.model_dump(), depth=depth + 1)
        except Exception:
            pass

    if hasattr(value, "dict") and callable(value.dict):
        try:
            return json_safe(value.dict(), depth=depth + 1)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return {
                str(key): json_safe(item, depth=depth + 1)
                for key, item in list(vars(value).items())[:MAX_ITEMS]
                if not str(key).startswith("_")
            }
        except Exception:
            pass

    return repr(value)


def describe_schema(value: Any) -> dict[str, Any]:
    """Describe the shape of an already JSON-safe value."""
    if isinstance(value, dict):
        return {
            "type": "object",
            "fields": {key: describe_schema(item) for key, item in value.items()},
        }

    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": "unknown"}
        return {"type": "array", "items": describe_schema(value[0])}

    return {"type": type(value).__name__}
