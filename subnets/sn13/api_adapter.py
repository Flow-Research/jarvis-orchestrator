"""SN13 adapters for the generic Workstream API."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from workstream.models import (
    OperatorStats,
    OperatorSubmissionEnvelope,
    OperatorSubmissionReceipt,
    WorkstreamSubmissionRecord,
    WorkstreamTask,
    utc_now,
)
from workstream.ports import WorkstreamPort

from .intake import OperatorSubmission, SubmissionProvenance
from .models import DataSource, normalize_label
from .quality import SubmissionStatus
from .storage import SQLiteStorage
from .tasks import SN13OperatorRuntime


class SN13OperatorIntakeAdapter:
    """Route generic workstream submissions into SN13 quality-gated intake."""

    def __init__(
        self,
        *,
        runtime: SN13OperatorRuntime,
        workstream: WorkstreamPort,
    ):
        self.runtime = runtime
        self.workstream = workstream

    def submit(self, envelope: OperatorSubmissionEnvelope) -> OperatorSubmissionReceipt:
        task = self.workstream.get(envelope.task_id)
        blocking_reason = self._blocking_reason(envelope, task)
        if blocking_reason is not None:
            return _receipt(
                envelope,
                accepted=0,
                rejected=len(envelope.records),
                duplicate=0,
                status="rejected",
                reasons=[blocking_reason],
            )

        assert task is not None
        contract = task.contract
        limits = contract.get("delivery_limits") or {}
        max_records = min(
            int(limits.get("max_records") or len(envelope.records)),
            max(task.remaining_capacity, 0),
        )
        max_record_bytes = int(limits.get("max_content_bytes_per_record") or 1_000_000)
        max_total_bytes = int(
            limits.get("max_total_content_bytes") or max_record_bytes * max_records
        )

        accepted = 0
        rejected = 0
        duplicate = 0
        reasons: list[str] = []
        total_bytes = 0

        for index, record in enumerate(envelope.records):
            if not task.is_available:
                rejected += 1
                reasons.append("delivery_limit:task_acceptance_cap_reached")
                continue
            if index >= max_records:
                rejected += 1
                reasons.append("delivery_limit:task_acceptance_cap_reached")
                continue

            submission, record_reasons, content_bytes = self._build_submission(
                envelope,
                record=record,
                task=task,
                index=index,
            )
            total_bytes += content_bytes
            if content_bytes > max_record_bytes:
                record_reasons.append("delivery_limit:max_content_bytes_per_record")
            if total_bytes > max_total_bytes:
                record_reasons.append("delivery_limit:max_total_content_bytes")

            if submission is None:
                rejected += 1
                reasons.extend(record_reasons)
                continue

            record_reasons.extend(_contract_rejection_reasons(submission, contract))
            if record_reasons:
                self.runtime.storage.record_rejection(submission, record_reasons)
                rejected += 1
                reasons.extend(record_reasons)
                continue

            result = self.runtime.ingest_submission(submission)
            if result.duplicate_recorded:
                duplicate += 1
            if result.quality.status == SubmissionStatus.REJECTED:
                rejected += 1
                reasons.extend(result.quality.reasons)
            else:
                accepted += 1
                task = self.workstream.record_acceptance(task.task_id, accepted_count=1)

        status = "accepted" if accepted and not rejected else "partial" if accepted else "rejected"
        return _receipt(
            envelope,
            accepted=accepted,
            rejected=rejected,
            duplicate=duplicate,
            status=status,
            reasons=sorted(set(reasons)),
        )

    def _blocking_reason(
        self,
        envelope: OperatorSubmissionEnvelope,
        task: WorkstreamTask | None,
    ) -> str | None:
        if envelope.route_key != "sn13":
            return "route_mismatch:expected_sn13"
        if task is None:
            return "task_not_found"
        if task.route_key != "sn13":
            return "task_route_mismatch:expected_sn13"
        if task.status == task.status.CANCELLED:
            return "task_cancelled"
        if task.status == task.status.COMPLETED or task.remaining_capacity <= 0:
            return "task_acceptance_cap_reached"
        if not task.is_available:
            return "task_expired"
        return None

    def _build_submission(
        self,
        envelope: OperatorSubmissionEnvelope,
        *,
        record: WorkstreamSubmissionRecord,
        task: WorkstreamTask,
        index: int,
    ) -> tuple[OperatorSubmission | None, list[str], int]:
        contract = task.contract
        content = record.content
        content_bytes = len(json.dumps(content, sort_keys=True, default=str).encode("utf-8"))
        try:
            submission = OperatorSubmission(
                submission_id=str(
                    record.submission_id
                    or _generated_submission_id(envelope, task, index)
                ),
                operator_id=envelope.operator_id,
                source=_record_source(record, contract),
                label=record.label or contract.get("label"),
                uri=_record_uri(record, content),
                source_created_at=record.source_created_at,
                scraped_at=record.scraped_at or envelope.submitted_at,
                content=content,
                provenance=_record_provenance(record, contract, envelope.operator_id),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return None, [f"invalid_submission:{exc.__class__.__name__}"], content_bytes
        return submission, [], content_bytes


class SN13OperatorStatsAdapter:
    """Expose SN13 SQLite quality counters through the generic stats port."""

    def __init__(self, *, storage: SQLiteStorage):
        self.storage = storage

    def get_operator_stats(self, operator_id: str) -> OperatorStats:
        stats = self.storage.get_operator_quality_stats(operator_id)
        return OperatorStats(
            operator_id=operator_id,
            accepted_scorable=stats["accepted_scorable"],
            accepted_non_scorable=stats["accepted_non_scorable"],
            rejected=stats["rejected"],
            duplicate=stats["duplicate"],
            estimated_reward_units=float(stats["accepted_scorable"]),
            updated_at=stats["updated_at"] or utc_now(),
        )


def _receipt(
    envelope: OperatorSubmissionEnvelope,
    *,
    accepted: int,
    rejected: int,
    duplicate: int,
    status: str,
    reasons: list[str],
) -> OperatorSubmissionReceipt:
    return OperatorSubmissionReceipt(
        submission_id=envelope.submission_id,
        task_id=envelope.task_id,
        operator_id=envelope.operator_id,
        accepted_count=accepted,
        rejected_count=rejected,
        duplicate_count=duplicate,
        status=status,
        reasons=reasons,
    )


def _generated_submission_id(
    envelope: OperatorSubmissionEnvelope,
    task: WorkstreamTask,
    index: int,
) -> str:
    raw = f"{envelope.submission_id}:{task.task_id}:{index}".encode()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"{envelope.submission_id[:64]}:{digest}"


def _record_source(record: WorkstreamSubmissionRecord, contract: dict[str, Any]) -> DataSource:
    source = str(record.source or contract.get("source") or "").upper()
    return DataSource(source)


def _record_uri(record: WorkstreamSubmissionRecord, content: dict[str, Any]) -> str:
    uri = record.uri or content.get("uri") or content.get("url")
    if not uri:
        raise KeyError("uri")
    return str(uri)


def _record_provenance(
    record: WorkstreamSubmissionRecord,
    contract: dict[str, Any],
    operator_id: str,
) -> SubmissionProvenance:
    if record.provenance is not None:
        return SubmissionProvenance.model_validate(record.provenance)

    source_requirements = contract.get("source_requirements") or {}
    query_value = contract.get("label") or contract.get("keyword")
    return SubmissionProvenance(
        scraper_id=f"operator:{operator_id}",
        query_type=str(
            source_requirements.get("provenance_query_type")
            or "workstream_api_submission"
        ),
        query_value=str(query_value) if query_value is not None else None,
        job_id=str(
            contract.get("desirability_job_id")
            or contract.get("demand_id")
            or contract.get("task_id")
        ),
    )


def _contract_rejection_reasons(
    submission: OperatorSubmission,
    contract: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    acceptance = contract.get("acceptance") or {}

    start_raw = acceptance.get("source_created_at_gte")
    end_raw = acceptance.get("source_created_at_lt")
    start = _parse_datetime(start_raw) if start_raw else None
    end = _parse_datetime(end_raw) if end_raw else None
    if start is not None and submission.source_created_at < start:
        reasons.append("acceptance:source_created_at_before_window")
    if end is not None and submission.source_created_at >= end:
        reasons.append("acceptance:source_created_at_after_window")

    expected_label = normalize_label(contract.get("label"))
    if expected_label and not _submission_matches_contract_label(submission, expected_label):
        reasons.append("acceptance:label_mismatch")

    keyword = contract.get("keyword")
    if keyword:
        haystack = json.dumps(submission.content, default=str).lower()
        if str(keyword).lower() not in haystack:
            reasons.append("acceptance:keyword_mismatch")

    return reasons


def _parse_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _submission_matches_contract_label(
    submission: OperatorSubmission,
    expected_label: str,
) -> bool:
    if submission.source == DataSource.REDDIT:
        return _reddit_submission_matches_label(submission, expected_label)
    if submission.source == DataSource.X:
        return _x_submission_matches_label(submission, expected_label)
    return submission.label == expected_label


def _reddit_submission_matches_label(
    submission: OperatorSubmission,
    expected_label: str,
) -> bool:
    content = submission.content
    candidates = [
        content.get("subreddit"),
        content.get("subreddit_name_prefixed"),
        _extract_reddit_label_from_url(content.get("url")),
        _extract_reddit_label_from_url(submission.uri),
    ]
    normalized_candidates = {
        candidate
        for candidate in (_normalize_reddit_label(value) for value in candidates)
        if candidate is not None
    }
    return expected_label in normalized_candidates


def _x_submission_matches_label(
    submission: OperatorSubmission,
    expected_label: str,
) -> bool:
    content = submission.content
    hashtags = content.get("hashtags")
    if isinstance(hashtags, list):
        normalized_hashtags = {
            normalize_label(str(tag)) for tag in hashtags if str(tag).strip()
        }
        if expected_label in normalized_hashtags:
            return True

    text = str(content.get("text", "")).casefold()
    if expected_label.startswith("#"):
        return expected_label in text
    return expected_label in text


def _normalize_reddit_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("/r/"):
        text = text[1:]
    if not text.casefold().startswith("r/"):
        text = f"r/{text}"
    return normalize_label(text)


def _extract_reddit_label_from_url(value: Any) -> str | None:
    if value is None:
        return None
    parsed = urlparse(str(value))
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0].casefold() == "r":
        return _normalize_reddit_label(f"r/{parts[1]}")
    return None
