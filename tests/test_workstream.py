import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from workstream.models import WorkstreamTask, WorkstreamTaskStatus
from workstream.sqlite_store import SQLiteWorkstream
from workstream.store import InMemoryWorkstream, TaskUnavailableError


def _task(task_id: str = "task_1") -> WorkstreamTask:
    return WorkstreamTask(
        task_id=task_id,
        route_key="sn13",
        source="X",
        contract={
            "task_id": task_id,
            "source": "X",
            "delivery_limits": {"max_records": 10},
            "economics": {"payout_basis": "accepted_scorable_record"},
        },
        created_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        acceptance_cap=2,
    )


def test_workstream_publishes_lists_and_tracks_accepted_progress():
    workstream = InMemoryWorkstream()
    workstream.publish(_task())

    available = workstream.list_available(route_key="sn13", source="X")
    updated = workstream.record_acceptance("task_1", accepted_count=1)

    assert available[0].task_id == "task_1"
    assert updated.status == WorkstreamTaskStatus.OPEN
    assert updated.accepted_count == 1
    assert updated.remaining_capacity == 1


def test_workstream_closes_when_acceptance_cap_is_reached():
    workstream = InMemoryWorkstream()
    workstream.publish(_task())
    workstream.record_acceptance("task_1", accepted_count=2)

    with pytest.raises(TaskUnavailableError):
        workstream.record_acceptance("task_1", accepted_count=1)


def test_workstream_completes_task_without_operator_reservation():
    workstream = InMemoryWorkstream()
    workstream.publish(_task())

    completed = workstream.complete("task_1")
    assert completed.status == WorkstreamTaskStatus.COMPLETED


def test_sqlite_workstream_persists_tasks_and_progress(tmp_path):
    db_path = tmp_path / "workstream.sqlite3"
    first = SQLiteWorkstream(db_path)
    first.publish(_task())
    first.record_acceptance("task_1", accepted_count=1)

    second = SQLiteWorkstream(db_path)
    persisted = second.get("task_1")

    assert persisted is not None
    assert persisted.status == WorkstreamTaskStatus.OPEN
    assert persisted.accepted_count == 1
    assert [task.task_id for task in second.list_available(route_key="sn13")] == ["task_1"]


def test_sqlite_workstream_filters_available_tasks(tmp_path):
    workstream = SQLiteWorkstream(tmp_path / "workstream.sqlite3")
    workstream.publish(_task("task_1"))
    workstream.publish(
        WorkstreamTask(
            task_id="task_2",
            route_key="forecasting",
            source="forecast",
            contract={"task_id": "task_2", "source": "forecast"},
            created_at=datetime(2026, 4, 22, 1, tzinfo=timezone.utc),
        )
    )

    sn13_tasks = workstream.list_available(route_key="sn13")
    forecasting_tasks = workstream.list_available(route_key="forecasting", source="forecast")

    assert [task.task_id for task in sn13_tasks] == ["task_1"]
    assert [task.task_id for task in forecasting_tasks] == ["task_2"]


def test_sqlite_workstream_summary_and_list_tasks(tmp_path):
    workstream = SQLiteWorkstream(tmp_path / "workstream.sqlite3")
    workstream.publish(_task("task_1"))
    workstream.publish(_task("task_2"))
    workstream.record_acceptance("task_1", accepted_count=2)

    listed = workstream.list_tasks(route_key="sn13", limit=10)
    summary = workstream.summary(route_key="sn13")

    assert [task.task_id for task in listed] == ["task_1", "task_2"]
    assert summary["total_tasks"] == 2
    assert summary["open_tasks"] == 1
    assert summary["completed_tasks"] == 1
    assert summary["available_now"] == 1


def test_sqlite_workstream_migrates_legacy_lease_columns(tmp_path):
    db_path = tmp_path / "workstream.sqlite3"
    payload = _task("task_legacy").model_dump_json()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE workstream_tasks (
                task_id TEXT PRIMARY KEY,
                subnet TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                leased_by TEXT,
                leased_until TEXT,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO workstream_tasks (
                task_id,
                subnet,
                source,
                status,
                created_at,
                expires_at,
                leased_by,
                leased_until,
                payload_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "task_legacy",
                "sn13",
                "X",
                "open",
                "2026-04-22T00:00:00+00:00",
                None,
                None,
                None,
                payload,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    workstream = SQLiteWorkstream(db_path)
    persisted = workstream.get("task_legacy")
    schema_columns = []
    with closing(sqlite3.connect(db_path)) as migrated:
        migrated.row_factory = sqlite3.Row
        table_info = migrated.execute("PRAGMA table_info(workstream_tasks)").fetchall()
        schema_columns = [row["name"] for row in table_info]

    assert persisted is not None
    assert persisted.task_id == "task_legacy"
    assert persisted.route_key == "sn13"
    assert "route_key" in schema_columns
    assert "subnet" not in schema_columns
    assert "leased_by" not in schema_columns
    assert "leased_until" not in schema_columns
