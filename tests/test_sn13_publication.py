from datetime import datetime, timezone

from subnets.sn13.desirability import DesirabilitySnapshot
from subnets.sn13.models import MinerIndex
from subnets.sn13.planner import PlannerConfig, SN13Planner
from subnets.sn13.publication import PublicationEconomicsConfig, evaluate_publication_batch
from subnets.sn13.storage import SQLiteStorage
from subnets.sn13.tasks import SN13OperatorRuntime


def _planned_tasks(tmp_path):
    now = datetime(2026, 4, 22, 12, tzinfo=timezone.utc)
    snapshot = DesirabilitySnapshot.from_upstream_records(
        [
            {
                "id": "macro",
                "weight": 5.0,
                "params": {"platform": "x", "label": "#bittensor"},
            }
        ]
    )
    demands = SN13Planner(config=PlannerConfig(default_recent_buckets=1)).plan(
        index=MinerIndex(miner_id="miner"),
        desirability=snapshot,
        now=now,
    )
    runtime = SN13OperatorRuntime(storage=SQLiteStorage(tmp_path / "sn13.sqlite3"))
    return runtime.create_tasks(demands)


def test_publication_batch_refuses_tasks_with_missing_economics(tmp_path):
    decision = evaluate_publication_batch(
        _planned_tasks(tmp_path),
        economics=PublicationEconomicsConfig(),
    )

    assert len(decision.publishable_tasks) == 0
    assert len(decision.refused_tasks) == 1
    assert "missing_max_task_cost" in decision.refused_tasks[0].blockers


def test_publication_batch_accepts_tasks_with_complete_economics(tmp_path):
    decision = evaluate_publication_batch(
        _planned_tasks(tmp_path),
        economics=PublicationEconomicsConfig(
            max_task_cost=20.0,
            expected_reward_value=30.0,
            expected_submitted_records=1200,
            expected_accepted_scorable_records=900,
            expected_duplicate_rate=0.04,
            expected_rejection_rate=0.10,
            validation_pass_probability=0.95,
            payout_basis="accepted_scorable_record",
        ),
    )

    assert len(decision.publishable_tasks) == 1
    assert len(decision.refused_tasks) == 0
