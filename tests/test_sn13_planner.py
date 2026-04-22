from datetime import datetime, timezone

from subnets.sn13.desirability import DesirabilitySnapshot
from subnets.sn13.models import DataEntityBucketId, DataEntityIndexEntry, DataSource, MinerIndex
from subnets.sn13.planner import PlannerConfig, SN13Planner


def _snapshot():
    return DesirabilitySnapshot.from_upstream_records(
        [
            {
                "id": "low",
                "weight": 1.0,
                "params": {
                    "keyword": None,
                    "platform": "x",
                    "label": "#bitcoin",
                    "post_start_datetime": None,
                    "post_end_datetime": None,
                },
            },
            {
                "id": "high",
                "weight": 4.0,
                "params": {
                    "keyword": None,
                    "platform": "x",
                    "label": "#macrocosmos",
                    "post_start_datetime": None,
                    "post_end_datetime": None,
                },
            },
        ],
        retrieved_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )


def test_planner_prioritizes_high_desirability_gap():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    index = MinerIndex(miner_id="miner_hotkey")
    planner = SN13Planner(config=PlannerConfig(default_recent_buckets=1))

    demands = planner.plan(index=index, desirability=_snapshot(), now=now)

    assert demands[0].desirability_job_id == "high"
    assert demands[0].label == "#macrocosmos"
    assert demands[0].quantity_target == 250


def test_planner_suppresses_fully_covered_bucket():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    current_bucket = int(now.timestamp() // 3600)
    index = MinerIndex(
        miner_id="miner_hotkey",
        blocks=[
            DataEntityIndexEntry(
                bucket=DataEntityBucketId(
                    time_bucket=current_bucket,
                    source=DataSource.X,
                    label="#macrocosmos",
                ),
                size_bytes=10_000,
                item_count=250,
                last_updated=now,
            )
        ],
    )
    planner = SN13Planner(config=PlannerConfig(default_recent_buckets=1))

    demands = planner.plan(index=index, desirability=_snapshot(), now=now)

    assert all(demand.label != "#macrocosmos" for demand in demands)


def test_planner_emits_partial_quantity_for_undercovered_bucket():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    current_bucket = int(now.timestamp() // 3600)
    index = MinerIndex(
        miner_id="miner_hotkey",
        blocks=[
            DataEntityIndexEntry(
                bucket=DataEntityBucketId(
                    time_bucket=current_bucket,
                    source=DataSource.X,
                    label="#macrocosmos",
                ),
                size_bytes=10_000,
                item_count=100,
                last_updated=now,
            )
        ],
    )
    planner = SN13Planner(
        config=PlannerConfig(default_recent_buckets=1, target_items_per_bucket=250)
    )

    demands = planner.plan(index=index, desirability=_snapshot(), now=now)
    macro = next(demand for demand in demands if demand.label == "#macrocosmos")

    assert macro.existing_items == 100
    assert macro.quantity_target == 150


def test_planner_respects_explicit_desirability_window():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    snapshot = DesirabilitySnapshot.from_upstream_records(
        [
            {
                "id": "ranged",
                "weight": 3.0,
                "params": {
                    "keyword": None,
                    "platform": "reddit",
                    "label": "r/Bittensor_",
                    "post_start_datetime": "2026-04-20T00:00:00+00:00",
                    "post_end_datetime": "2026-04-20T02:00:00+00:00",
                },
            }
        ]
    )
    planner = SN13Planner(config=PlannerConfig(default_recent_buckets=5))

    demands = planner.plan(
        index=MinerIndex(miner_id="miner_hotkey"),
        desirability=snapshot,
        now=now,
    )

    assert demands
    max_bucket = int(datetime(2026, 4, 20, 2, tzinfo=timezone.utc).timestamp() // 3600)
    assert all(demand.time_bucket <= max_bucket for demand in demands)
    assert all(demand.label == "r/bittensor_" for demand in demands)


def test_planner_skips_unsupported_sources_by_default():
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    snapshot = DesirabilitySnapshot.from_upstream_records(
        [
            {
                "id": "youtube_job",
                "weight": 5.0,
                "params": {
                    "keyword": None,
                    "platform": "youtube",
                    "label": "#macrocosmos",
                    "post_start_datetime": None,
                    "post_end_datetime": None,
                },
            },
            {
                "id": "x_job",
                "weight": 1.0,
                "params": {
                    "keyword": None,
                    "platform": "x",
                    "label": "#macrocosmos",
                    "post_start_datetime": None,
                    "post_end_datetime": None,
                },
            },
        ]
    )

    demands = SN13Planner(config=PlannerConfig(default_recent_buckets=1)).plan(
        index=MinerIndex(miner_id="miner_hotkey"),
        desirability=snapshot,
        now=now,
    )

    assert [demand.desirability_job_id for demand in demands] == ["x_job"]
