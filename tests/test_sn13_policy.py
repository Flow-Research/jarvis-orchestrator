from datetime import datetime, timedelta, timezone

from subnets.sn13.models import DataEntity, DataEntityBucket, DataEntityBucketId, DataEntityIndexEntry, DataSource, MinerIndex
from subnets.sn13.policy import DesirableJobWindow, SN13Policy


def _entity_at(dt: datetime, *, source: DataSource = DataSource.X, label: str = "#bittensor") -> DataEntity:
    return DataEntity(
        uri=f"https://x.com/example/status/{int(dt.timestamp())}",
        datetime=dt,
        source=source,
        label=label,
        content={"text": "hello", "url": f"https://x.com/example/status/{int(dt.timestamp())}"},
    )


def test_policy_defaults_match_phase_one_targets():
    policy = SN13Policy()

    assert policy.default_freshness_days == 30
    assert policy.bucket_size_limit_bytes == 128 * 1024 * 1024
    assert policy.miner_index_bucket_limit == 350_000
    assert policy.get_source_weight(DataSource.REDDIT) == 0.55
    assert policy.get_source_weight(DataSource.X) == 0.35
    assert policy.credibility.alpha == 0.15
    assert policy.credibility.exponent == 2.5


def test_recent_entity_is_scorable_under_default_freshness():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    entity = _entity_at(now - timedelta(days=5))
    policy = SN13Policy()

    decision = policy.classify_entity(entity, now=now)

    assert decision.is_scorable is True
    assert decision.reason == "scorable_within_default_freshness"


def test_old_entity_is_not_scorable_under_default_freshness():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    entity = _entity_at(now - timedelta(days=31))
    policy = SN13Policy()

    decision = policy.classify_entity(entity, now=now)

    assert decision.is_scorable is False
    assert decision.reason == "stale_beyond_default_freshness"


def test_desirable_window_can_make_old_entity_scorable():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    entity = _entity_at(now - timedelta(days=90), label="#macrocosmos")
    policy = SN13Policy()
    desirable_job = DesirableJobWindow(
        source=DataSource.X,
        label="#macrocosmos",
        scale_factor=3.2,
        start_time_bucket=entity.time_bucket - 1,
        end_time_bucket=entity.time_bucket + 1,
    )

    decision = policy.classify_entity(entity, now=now, desirable_job=desirable_job)

    assert decision.is_scorable is True
    assert decision.reason == "scorable_within_desirable_window"
    assert decision.desirable_window_applied is True
    assert decision.desirable_scale_factor == 3.2


def test_desirable_window_rejects_entity_outside_range():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    entity = _entity_at(now - timedelta(days=90), label="#macrocosmos")
    policy = SN13Policy()
    desirable_job = DesirableJobWindow(
        source=DataSource.X,
        label="#macrocosmos",
        scale_factor=2.0,
        start_time_bucket=entity.time_bucket + 5,
        end_time_bucket=entity.time_bucket + 10,
    )

    decision = policy.classify_entity(entity, now=now, desirable_job=desirable_job)

    assert decision.is_scorable is False
    assert decision.reason == "outside_desirable_window"


def test_policy_exposes_bucket_and_index_limits():
    policy = SN13Policy()
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    entity = _entity_at(now)
    bucket = DataEntityBucket(
        id=DataEntityBucketId(time_bucket=entity.time_bucket, source=entity.source, label=entity.label),
        entities=[entity],
    )
    index = MinerIndex(
        miner_id="miner_hotkey",
        blocks=[
            DataEntityIndexEntry(
                bucket=bucket.id,
                size_bytes=bucket.total_bytes,
                item_count=bucket.count,
                last_updated=now,
            )
        ],
    )

    assert policy.bucket_is_within_limit(bucket) is True
    assert policy.index_is_within_limit(index) is True
