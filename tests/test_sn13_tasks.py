from datetime import datetime, timezone

from subnets.sn13.desirability import DesirabilitySnapshot
from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.models import DataSource, MinerIndex
from subnets.sn13.planner import PlannerConfig, SN13Planner
from subnets.sn13.quality import SubmissionStatus
from subnets.sn13.storage import SQLiteStorage
from subnets.sn13.tasks import OperatorTaskStatus, SN13OperatorRuntime


def _snapshot():
    return DesirabilitySnapshot.from_upstream_records(
        [
            {
                "id": "macro",
                "weight": 4.0,
                "params": {
                    "keyword": None,
                    "platform": "x",
                    "label": "#macrocosmos",
                    "post_start_datetime": None,
                    "post_end_datetime": None,
                },
            }
        ]
    )


def _submission(now: datetime) -> OperatorSubmission:
    uri = f"https://x.com/macro/status/{int(now.timestamp())}"
    return OperatorSubmission(
        operator_id="operator_1",
        source=DataSource.X,
        label="#macrocosmos",
        uri=uri,
        source_created_at=now,
        scraped_at=now,
        content={
            "tweet_id": str(int(now.timestamp())),
            "username": "macro",
            "text": "operator result",
            "url": uri,
            "timestamp": now.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="x.custom.v1",
            query_type="label_search",
            query_value="#macrocosmos",
            job_id="macro",
        ),
    )


def test_runtime_turns_planner_demand_into_assigned_tasks(tmp_path):
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    planner = SN13Planner(config=PlannerConfig(default_recent_buckets=1))
    demands = planner.plan(index=MinerIndex(miner_id="miner"), desirability=_snapshot(), now=now)
    runtime = SN13OperatorRuntime(storage=SQLiteStorage(tmp_path / "sn13.sqlite3"))

    tasks = runtime.create_tasks(demands, operator_ids=["operator_1", "operator_2"])

    assert tasks
    assert tasks[0].status == OperatorTaskStatus.ASSIGNED
    assert tasks[0].assigned_operator_id == "operator_1"
    assert tasks[0].label == "#macrocosmos"


def test_runtime_ingests_valid_submission_into_storage(tmp_path):
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    runtime = SN13OperatorRuntime(storage=storage)

    result = runtime.ingest_submission(_submission(now), now=now)
    index = storage.get_index("miner")

    assert result.stored is True
    assert result.quality.status == SubmissionStatus.ACCEPTED_SCORABLE
    assert index.total_data_items == 1
    assert storage.get_operator_quality_stats("operator_1")["accepted_scorable"] == 1


def test_runtime_rejects_duplicate_submission_without_overwriting_truth(tmp_path):
    now = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    runtime = SN13OperatorRuntime(storage=storage)

    first = runtime.ingest_submission(_submission(now), now=now)
    second = runtime.ingest_submission(_submission(now), now=now)

    assert first.stored is True
    assert second.stored is False
    assert second.duplicate_recorded is True
    assert second.rejection_recorded is True
    assert storage.get_index("miner").total_data_items == 1
    stats = storage.get_operator_quality_stats("operator_1")
    assert stats["duplicate"] == 1
    assert stats["rejected"] == 1
