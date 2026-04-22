from datetime import datetime, timezone

from subnets.sn13.simulator import (
    ClosedLoopSimulationConfig,
    create_tasks_from_demands,
    load_snapshot,
    plan_demands,
    run_closed_loop_simulation,
)
from subnets.sn13.storage import SQLiteStorage

NOW = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)


def test_default_snapshot_can_plan_operator_tasks(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    snapshot = load_snapshot(use_sample=True)
    config = ClosedLoopSimulationConfig(
        target_items_per_bucket=3,
        default_recent_buckets=1,
        max_tasks=2,
    )

    demands = plan_demands(storage=storage, snapshot=snapshot, config=config, now=NOW)
    tasks = create_tasks_from_demands(storage=storage, demands=demands, config=config)

    assert len(demands) == 2
    assert len(tasks) == 2
    assert tasks[0].status == "queued"
    assert tasks[0].quantity_target == 3


def test_closed_loop_simulation_reaches_validator_and_export_paths(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    snapshot = load_snapshot(use_sample=True)
    config = ClosedLoopSimulationConfig(
        target_items_per_bucket=2,
        default_recent_buckets=1,
        max_tasks=2,
        export=True,
    )

    report = run_closed_loop_simulation(
        storage=storage,
        snapshot=snapshot,
        output_root=tmp_path / "exports",
        config=config,
        now=NOW,
    )

    assert report.desirability_jobs == 2
    assert report.planned_tasks == 2
    assert report.accepted_submissions == 4
    assert report.rejected_submissions == 0
    assert report.index_source_groups >= 1
    assert report.validator_bucket_entities == 2
    assert report.validator_content_buckets == 1
    assert report.exported_rows >= 2
    assert any(result.file_path and result.file_path.exists() for result in report.export_results)


def test_closed_loop_simulation_uses_coverage_to_avoid_replanning_full_bucket(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    snapshot = load_snapshot(use_sample=True)
    config = ClosedLoopSimulationConfig(
        target_items_per_bucket=1,
        default_recent_buckets=1,
        max_tasks=2,
        export=False,
    )

    first = run_closed_loop_simulation(
        storage=storage,
        snapshot=snapshot,
        output_root=tmp_path / "exports",
        config=config,
        now=NOW,
    )
    second = run_closed_loop_simulation(
        storage=storage,
        snapshot=snapshot,
        output_root=tmp_path / "exports",
        config=config,
        now=NOW,
    )

    assert first.planned_tasks == 2
    assert second.planned_tasks == 0
    assert second.accepted_submissions == 0
