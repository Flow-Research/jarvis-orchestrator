from datetime import datetime, timedelta, timezone

import pytest

from subnets.sn13.desirability import DesirabilityJob, DesirabilitySnapshot
from subnets.sn13.models import DataEntity, DataSource
from subnets.sn13.policy import SN13Policy


def _record(
    *,
    job_id: str = "job_1",
    platform: str = "x",
    label: str = "#macrocosmos",
    weight: float = 3.5,
    start: str | None = None,
    end: str | None = None,
):
    return {
        "id": job_id,
        "weight": weight,
        "params": {
            "keyword": None,
            "platform": platform,
            "label": label,
            "post_start_datetime": start,
            "post_end_datetime": end,
        },
    }


def _entity(dt: datetime, *, label: str = "#macrocosmos") -> DataEntity:
    return DataEntity(
        uri=f"https://x.com/macro/status/{int(dt.timestamp())}",
        datetime=dt,
        source=DataSource.X,
        label=label,
        content={
            "tweet_id": str(int(dt.timestamp())),
            "username": "macro",
            "text": "gravity test",
            "url": f"https://x.com/macro/status/{int(dt.timestamp())}",
            "timestamp": dt.isoformat(),
        },
    )


def test_upstream_record_normalizes_to_desirability_job():
    job = DesirabilityJob.from_upstream_record(_record(label="#MacrocosmosAI"))

    assert job.job_id == "job_1"
    assert job.source == DataSource.X
    assert job.label == "#macrocosmosai"
    assert job.weight == 3.5


def test_snapshot_finds_highest_weight_matching_job():
    snapshot = DesirabilitySnapshot.from_upstream_records(
        [
            _record(job_id="low", label="#macrocosmos", weight=1.5),
            _record(job_id="high", label="#macrocosmos", weight=4.2),
            _record(job_id="other", label="#bitcoin", weight=5.0),
        ],
        retrieved_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    bucket = _entity(datetime(2026, 4, 21, 12, tzinfo=timezone.utc)).time_bucket

    match = snapshot.find_best_match(
        source=DataSource.X,
        label="#Macrocosmos",
        time_bucket=bucket,
    )

    assert match.matched is True
    assert match.job.job_id == "high"
    assert match.weight == 4.2


def test_snapshot_respects_explicit_date_window():
    snapshot = DesirabilitySnapshot.from_upstream_records(
        [
            _record(
                start="2026-04-01T00:00:00+00:00",
                end="2026-04-30T23:59:59+00:00",
            )
        ]
    )

    in_range_bucket = _entity(datetime(2026, 4, 10, 12, tzinfo=timezone.utc)).time_bucket
    out_range_bucket = _entity(datetime(2026, 5, 10, 12, tzinfo=timezone.utc)).time_bucket

    assert snapshot.find_best_match(
        source=DataSource.X,
        label="#macrocosmos",
        time_bucket=in_range_bucket,
    ).matched is True
    assert snapshot.find_best_match(
        source=DataSource.X,
        label="#macrocosmos",
        time_bucket=out_range_bucket,
    ).matched is False


def test_desirability_window_overrides_default_freshness_policy():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    old_entity = _entity(now - timedelta(days=90))
    snapshot = DesirabilitySnapshot.from_upstream_records(
        [
            _record(
                start=(old_entity.datetime - timedelta(hours=1)).isoformat(),
                end=(old_entity.datetime + timedelta(hours=1)).isoformat(),
            )
        ]
    )

    match, decision = snapshot.classify_entity(
        old_entity,
        policy=SN13Policy(),
        now=now,
    )

    assert match.matched is True
    assert decision.is_scorable is True
    assert decision.reason == "scorable_within_desirable_window"


def test_invalid_upstream_platform_is_rejected():
    with pytest.raises(ValueError, match="Unsupported desirability platform"):
        DesirabilityJob.from_upstream_record(_record(platform="tiktok"))
