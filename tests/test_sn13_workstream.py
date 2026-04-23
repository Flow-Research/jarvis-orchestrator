from datetime import datetime, timedelta, timezone

from subnets.sn13.desirability import DesirabilitySnapshot
from subnets.sn13.models import MinerIndex
from subnets.sn13.planner import PlannerConfig, SN13Planner
from subnets.sn13.storage import SQLiteStorage
from subnets.sn13.tasks import SN13OperatorRuntime
from subnets.sn13.workstream import publish_sn13_tasks, workstream_task_from_sn13
from workstream.store import InMemoryWorkstream


def test_sn13_task_publishes_as_generic_workstream_contract(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
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
    task = runtime.create_tasks(demands)[0]

    workstream_task = workstream_task_from_sn13(task)

    assert workstream_task.route_key == "sn13"
    assert workstream_task.source == "X"
    assert workstream_task.contract["task_id"] == task.task_id
    assert workstream_task.contract["delivery_limits"]["max_records"] == task.quantity_target


def test_sn13_tasks_publish_to_workstream(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
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
    tasks = runtime.create_tasks(demands)
    workstream = InMemoryWorkstream()

    published = publish_sn13_tasks(tasks, workstream=workstream)

    assert published
    assert workstream.list_available(route_key="sn13")
