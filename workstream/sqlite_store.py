"""Durable SQLite workstream adapter."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import WorkstreamTask, WorkstreamTaskStatus, ensure_utc, utc_now
from .store import TaskNotFoundError, TaskUnavailableError


class SQLiteWorkstream:
    """SQLite-backed workstream for single-node Jarvis deployments."""

    TASK_COLUMNS = (
        "task_id",
        "route_key",
        "source",
        "status",
        "created_at",
        "expires_at",
        "payload_json",
        "updated_at",
    )

    TASK_TABLE = """
    CREATE TABLE IF NOT EXISTS workstream_tasks (
        task_id TEXT PRIMARY KEY,
        route_key TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """

    TASK_LOOKUP_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_workstream_tasks_lookup
    ON workstream_tasks (status, route_key, source, created_at, task_id)
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            self._ensure_task_table(connection)
            connection.execute(self.TASK_LOOKUP_INDEX)
            connection.commit()

    def _ensure_task_table(self, connection: sqlite3.Connection) -> None:
        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'workstream_tasks'
            """
        ).fetchone()
        if table_exists is None:
            connection.execute(self.TASK_TABLE)
            return

        columns = tuple(
            row["name"]
            for row in connection.execute("PRAGMA table_info(workstream_tasks)").fetchall()
        )
        if columns == self.TASK_COLUMNS:
            return

        # Migrate earlier schemas without losing the JSON payload that already
        # contains canonical task state. Older workstream tables used `subnet`
        # for what is now the generic internal adapter route.
        route_column = "route_key" if "route_key" in columns else "subnet"
        connection.execute("DROP INDEX IF EXISTS idx_workstream_tasks_lookup")
        connection.execute("ALTER TABLE workstream_tasks RENAME TO workstream_tasks_legacy")
        connection.execute(self.TASK_TABLE)
        connection.execute(
            f"""
            INSERT INTO workstream_tasks (
                task_id,
                route_key,
                source,
                status,
                created_at,
                expires_at,
                payload_json,
                updated_at
            )
            SELECT
                task_id,
                {route_column},
                source,
                status,
                created_at,
                expires_at,
                payload_json,
                updated_at
            FROM workstream_tasks_legacy
            """
        )
        connection.execute("DROP TABLE workstream_tasks_legacy")

    def publish(self, task: WorkstreamTask) -> WorkstreamTask:
        with self._connection() as connection:
            self._expire_open_tasks(connection)
            row = connection.execute(
                "SELECT payload_json FROM workstream_tasks WHERE task_id = ?",
                (task.task_id,),
            ).fetchone()
            updated = task
            terminal_statuses = {
                WorkstreamTaskStatus.COMPLETED,
                WorkstreamTaskStatus.CANCELLED,
            }
            if row is not None:
                existing = self._row_to_task(row)
                if task.status in terminal_statuses:
                    updated = task
                elif existing.status in terminal_statuses:
                    connection.commit()
                    return existing
                else:
                    accepted_count = existing.accepted_count
                    updated = task.model_copy(
                        update={
                            "accepted_count": accepted_count,
                            "status": (
                                WorkstreamTaskStatus.COMPLETED
                                if accepted_count >= task.acceptance_cap
                                else WorkstreamTaskStatus.OPEN
                            ),
                        }
                    )
            self._upsert(connection, updated)
            connection.commit()
        return updated

    def get(self, task_id: str) -> WorkstreamTask | None:
        with self._connection() as connection:
            self._expire_open_tasks(connection)
            row = connection.execute(
                "SELECT payload_json FROM workstream_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            connection.commit()
        return self._row_to_task(row) if row else None

    def list_available(
        self,
        *,
        route_key: str | None = None,
        source: str | None = None,
    ) -> list[WorkstreamTask]:
        self.expire_open_tasks()
        where_parts: list[str] = []
        params: list[object] = []
        if route_key is not None:
            where_parts.append("route_key = ?")
            params.append(route_key)
        if source is not None:
            where_parts.append("source = ?")
            params.append(source)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM workstream_tasks
                {where_sql}
                ORDER BY created_at ASC, task_id ASC
                """,
                params,
            ).fetchall()

        return [task for task in map(self._row_to_task, rows) if task.is_available]

    def list_tasks(
        self,
        *,
        status: WorkstreamTaskStatus | None = None,
        route_key: str | None = None,
        source: str | None = None,
        limit: int | None = None,
    ) -> list[WorkstreamTask]:
        self.expire_open_tasks()
        where_parts: list[str] = []
        params: list[object] = []
        if status is not None:
            where_parts.append("status = ?")
            params.append(status.value)
        if route_key is not None:
            where_parts.append("route_key = ?")
            params.append(route_key)
        if source is not None:
            where_parts.append("source = ?")
            params.append(source)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT ?"
            params.append(limit)

        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM workstream_tasks
                {where_sql}
                ORDER BY created_at ASC, task_id ASC
                {limit_sql}
                """,
                params,
            ).fetchall()

        return [self._row_to_task(row) for row in rows]

    def summary(
        self,
        *,
        route_key: str | None = None,
        source: str | None = None,
    ) -> dict[str, int]:
        self.expire_open_tasks()
        where_parts: list[str] = []
        params: list[object] = []
        if route_key is not None:
            where_parts.append("route_key = ?")
            params.append(route_key)
        if source is not None:
            where_parts.append("source = ?")
            params.append(source)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        counts = {status.value: 0 for status in WorkstreamTaskStatus}
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT status, COUNT(*) AS task_count
                FROM workstream_tasks
                {where_sql}
                GROUP BY status
                """,
                params,
            ).fetchall()

        total_tasks = 0
        for row in rows:
            task_count = int(row["task_count"])
            counts[row["status"]] = task_count
            total_tasks += task_count

        available_now = len(self.list_available(route_key=route_key, source=source))
        return {
            "total_tasks": total_tasks,
            "open_tasks": counts[WorkstreamTaskStatus.OPEN.value],
            "completed_tasks": counts[WorkstreamTaskStatus.COMPLETED.value],
            "cancelled_tasks": counts[WorkstreamTaskStatus.CANCELLED.value],
            "expired_tasks": counts[WorkstreamTaskStatus.EXPIRED.value],
            "available_now": available_now,
        }

    def expire_open_tasks(self, *, now: datetime | None = None) -> int:
        with self._connection() as connection:
            expired = self._expire_open_tasks(connection, now=now)
            connection.commit()
        return expired

    def record_acceptance(self, task_id: str, *, accepted_count: int) -> WorkstreamTask:
        with self._connection() as connection:
            self._expire_open_tasks(connection)
            row = connection.execute(
                "SELECT payload_json FROM workstream_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)

            task = self._row_to_task(row)
            if accepted_count < 1 or not task.is_available:
                raise TaskUnavailableError(task_id)

            new_accepted_count = min(task.acceptance_cap, task.accepted_count + accepted_count)
            updated = task.model_copy(
                update={
                    "accepted_count": new_accepted_count,
                    "status": (
                        WorkstreamTaskStatus.COMPLETED
                        if new_accepted_count >= task.acceptance_cap
                        else task.status
                    ),
                }
            )
            self._upsert(connection, updated)
            connection.commit()
            return updated

    def complete(self, task_id: str) -> WorkstreamTask:
        with self._connection() as connection:
            self._expire_open_tasks(connection)
            row = connection.execute(
                "SELECT payload_json FROM workstream_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)

            task = self._row_to_task(row)
            if task.status not in {WorkstreamTaskStatus.OPEN, WorkstreamTaskStatus.COMPLETED}:
                raise TaskUnavailableError(task_id)

            completed = task.model_copy(update={"status": WorkstreamTaskStatus.COMPLETED})
            self._upsert(connection, completed)
            connection.commit()
            return completed

    def _expire_open_tasks(
        self,
        connection: sqlite3.Connection,
        *,
        now: datetime | None = None,
    ) -> int:
        current_time = ensure_utc(now or utc_now())
        rows = connection.execute(
            """
            SELECT payload_json
            FROM workstream_tasks
            WHERE status = ? AND expires_at IS NOT NULL
            """,
            (WorkstreamTaskStatus.OPEN.value,),
        ).fetchall()
        expired = 0
        for row in rows:
            task = self._row_to_task(row)
            if not task.is_expired(current_time):
                continue
            self._upsert(
                connection,
                task.model_copy(update={"status": WorkstreamTaskStatus.EXPIRED}),
            )
            expired += 1
        return expired

    def _upsert(self, connection: sqlite3.Connection, task: WorkstreamTask) -> None:
        connection.execute(
            """
            INSERT INTO workstream_tasks (
                task_id,
                route_key,
                source,
                status,
                created_at,
                expires_at,
                payload_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(task_id) DO UPDATE SET
                route_key = excluded.route_key,
                source = excluded.source,
                status = excluded.status,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                task.task_id,
                task.route_key,
                task.source,
                task.status.value,
                task.created_at.isoformat(),
                task.expires_at.isoformat() if task.expires_at else None,
                json.dumps(task.model_dump(mode="json"), sort_keys=True),
            ),
        )

    def _row_to_task(self, row: sqlite3.Row) -> WorkstreamTask:
        return WorkstreamTask.model_validate(json.loads(row["payload_json"]))
