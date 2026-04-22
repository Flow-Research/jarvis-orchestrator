from datetime import datetime, timedelta, timezone

from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.models import DataSource
from subnets.sn13.quality import RejectionReason, SubmissionQualityChecker, SubmissionStatus
from subnets.sn13.storage import SQLiteStorage


def _submission(
    *,
    operator_id: str = "operator_1",
    source_created_at: datetime | None = None,
    content: dict | None = None,
) -> OperatorSubmission:
    created_at = source_created_at or datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    uri = f"https://x.com/example/status/{int(created_at.timestamp())}"
    return OperatorSubmission(
        operator_id=operator_id,
        source=DataSource.X,
        label="#bittensor",
        uri=uri,
        source_created_at=created_at,
        scraped_at=created_at + timedelta(minutes=1),
        content=content
        or {
            "tweet_id": str(int(created_at.timestamp())),
            "username": "example",
            "text": "fresh bittensor post",
            "url": uri,
            "timestamp": created_at.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="x.custom.v1",
            query_type="label_search",
            query_value="#bittensor",
        ),
    )


def test_quality_accepts_recent_valid_submission_as_scorable():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    result = SubmissionQualityChecker().assess(_submission(source_created_at=now), now=now)

    assert result.status == SubmissionStatus.ACCEPTED_SCORABLE
    assert result.accepted is True
    assert result.scorable_decision.reason == "scorable_within_default_freshness"


def test_quality_accepts_stale_submission_as_non_scorable_not_rejected():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    old_submission = _submission(source_created_at=now - timedelta(days=31))

    result = SubmissionQualityChecker().assess(old_submission, now=now)

    assert result.status == SubmissionStatus.ACCEPTED_NON_SCORABLE
    assert result.accepted is True
    assert result.scorable_decision.reason == "stale_beyond_default_freshness"


def test_quality_rejects_missing_source_specific_fields():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    result = SubmissionQualityChecker().assess(
        _submission(content={"text": "missing url and ids"}),
        now=now,
    )

    assert result.status == SubmissionStatus.REJECTED
    assert any(
        reason.startswith(RejectionReason.MISSING_SOURCE_FIELD.value)
        for reason in result.reasons
    )


def test_storage_records_rejections_duplicates_and_operator_stats(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    checker = SubmissionQualityChecker()
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    submission = _submission(operator_id="operator_9", source_created_at=now)

    accepted = checker.assess(submission, now=now)
    storage.store_submission(submission, status=accepted.status.value)

    duplicate_submission = _submission(operator_id="operator_9", source_created_at=now)
    duplicate = checker.assess(
        duplicate_submission,
        duplicate=storage.uri_exists(duplicate_submission.uri),
        now=now,
    )
    storage.record_duplicate(duplicate_submission, duplicate_submission.uri)
    storage.record_rejection(duplicate_submission, duplicate.reasons)

    stats = storage.get_operator_quality_stats("operator_9")

    assert stats["accepted_scorable"] == 1
    assert stats["duplicate"] == 1
    assert stats["rejected"] == 1
