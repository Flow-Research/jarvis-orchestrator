#!/usr/bin/env python3
"""
SN13 canonical SQLite storage.

This is the only supported storage backend for the Jarvis SN13 implementation.
Operator submissions are ingested into SQLite, normalized into canonical
DataEntity rows, and served from there.
"""

from __future__ import annotations

import sqlite3
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

_dir = Path(__file__).parent
if str(_dir) not in sys.path:
    sys.path.insert(0, str(_dir))

try:
    from .intake import OperatorSubmission
    from .models import (
        DataEntity,
        DataEntityBucket,
        DataEntityBucketId,
        DataEntityIndexEntry,
        DataQueryResponse,
        DataSource,
        MinerIndex,
        ensure_utc,
        normalize_label,
        normalize_uri,
    )
except ImportError:
    from intake import OperatorSubmission
    from models import (
        DataEntity,
        DataEntityBucket,
        DataEntityBucketId,
        DataEntityIndexEntry,
        DataQueryResponse,
        DataSource,
        MinerIndex,
        ensure_utc,
        normalize_label,
        normalize_uri,
    )


class StorageError(Exception):
    """Base exception for storage operations."""


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def store_submission(self, submission: OperatorSubmission) -> DataEntity:
        pass

    @abstractmethod
    def store_submissions(self, submissions: Iterable[OperatorSubmission]) -> int:
        pass

    @abstractmethod
    def uri_exists(self, uri: str) -> bool:
        pass

    @abstractmethod
    def record_rejection(
        self,
        submission: OperatorSubmission,
        reasons: list[str],
        details: str = "",
    ) -> None:
        pass

    @abstractmethod
    def record_duplicate(self, submission: OperatorSubmission, existing_uri: str) -> None:
        pass

    @abstractmethod
    def get_operator_quality_stats(self, operator_id: str) -> dict:
        pass

    @abstractmethod
    def get_index(self, miner_id: str) -> MinerIndex:
        pass

    @abstractmethod
    def list_entities(
        self,
        *,
        source: Optional[DataSource] = None,
        label: Optional[str] = None,
        start_time_bucket: Optional[int] = None,
        end_time_bucket: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[DataEntity]:
        pass

    @abstractmethod
    def query_bucket(
        self,
        source: DataSource,
        label: Optional[str],
        time_bucket: int,
        limit: int = 100,
    ) -> DataQueryResponse:
        pass

    @abstractmethod
    def get_all_buckets(self) -> list[DataEntityBucket]:
        pass

    @abstractmethod
    def get_buckets_for_source(self, source: DataSource) -> list[DataEntityBucket]:
        pass

    @abstractmethod
    def get_buckets_for_label(self, label: str) -> list[DataEntityBucket]:
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass


class SQLiteStorage(StorageBackend):
    """Canonical SN13 storage based on SQLite."""

    ENTITY_TABLE = """
    CREATE TABLE IF NOT EXISTS data_entities (
        uri TEXT PRIMARY KEY,
        datetime TEXT NOT NULL,
        time_bucket INTEGER NOT NULL,
        source TEXT NOT NULL,
        label TEXT,
        content BLOB NOT NULL,
        content_size_bytes INTEGER NOT NULL,
        scraped_at TEXT
    )
    """

    SUBMISSION_TABLE = """
    CREATE TABLE IF NOT EXISTS operator_submissions (
        submission_id TEXT PRIMARY KEY,
        operator_id TEXT NOT NULL,
        uri TEXT NOT NULL,
        source TEXT NOT NULL,
        label TEXT,
        source_created_at TEXT NOT NULL,
        scraped_at TEXT NOT NULL,
        scraper_id TEXT NOT NULL,
        query_type TEXT NOT NULL,
        query_value TEXT,
        job_id TEXT,
        accepted_at TEXT NOT NULL,
        FOREIGN KEY(uri) REFERENCES data_entities(uri)
    )
    """

    REJECTION_TABLE = """
    CREATE TABLE IF NOT EXISTS rejected_submissions (
        submission_id TEXT PRIMARY KEY,
        operator_id TEXT NOT NULL,
        uri TEXT NOT NULL,
        source TEXT NOT NULL,
        label TEXT,
        reasons TEXT NOT NULL,
        details TEXT,
        rejected_at TEXT NOT NULL
    )
    """

    DUPLICATE_TABLE = """
    CREATE TABLE IF NOT EXISTS duplicate_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id TEXT NOT NULL,
        operator_id TEXT NOT NULL,
        uri TEXT NOT NULL,
        existing_uri TEXT NOT NULL,
        observed_at TEXT NOT NULL
    )
    """

    OPERATOR_QUALITY_TABLE = """
    CREATE TABLE IF NOT EXISTS operator_quality_stats (
        operator_id TEXT PRIMARY KEY,
        accepted_scorable INTEGER NOT NULL DEFAULT 0,
        accepted_non_scorable INTEGER NOT NULL DEFAULT 0,
        rejected INTEGER NOT NULL DEFAULT 0,
        duplicate INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """

    ENTITY_BUCKET_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_data_entities_bucket
    ON data_entities (time_bucket, source, label, datetime, uri)
    """

    SUBMISSION_OPERATOR_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_operator_submissions_operator
    ON operator_submissions (operator_id, source, label, accepted_at)
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(self.ENTITY_TABLE)
            cursor.execute(self.SUBMISSION_TABLE)
            cursor.execute(self.REJECTION_TABLE)
            cursor.execute(self.DUPLICATE_TABLE)
            cursor.execute(self.OPERATOR_QUALITY_TABLE)
            cursor.execute(self.ENTITY_BUCKET_INDEX)
            cursor.execute(self.SUBMISSION_OPERATOR_INDEX)
            cursor.execute("PRAGMA journal_mode=WAL")
            connection.commit()

    def store_submission(
        self,
        submission: OperatorSubmission,
        status: str = "accepted_scorable",
    ) -> DataEntity:
        entity = submission.to_data_entity()
        accepted_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO data_entities (
                    uri, datetime, time_bucket, source, label, content, content_size_bytes, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uri) DO UPDATE SET
                    datetime=excluded.datetime,
                    time_bucket=excluded.time_bucket,
                    source=excluded.source,
                    label=excluded.label,
                    content=excluded.content,
                    content_size_bytes=excluded.content_size_bytes,
                    scraped_at=excluded.scraped_at
                """,
                (
                    entity.uri,
                    entity.datetime.isoformat(),
                    entity.time_bucket,
                    entity.source.value,
                    entity.label,
                    entity.content,
                    entity.content_size_bytes,
                    entity.scraped_at.isoformat() if entity.scraped_at else None,
                ),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO operator_submissions (
                    submission_id,
                    operator_id,
                    uri,
                    source,
                    label,
                    source_created_at,
                    scraped_at,
                    scraper_id,
                    query_type,
                    query_value,
                    job_id,
                    accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission.submission_id,
                    submission.operator_id,
                    entity.uri,
                    submission.source.value,
                    submission.label,
                    submission.source_created_at.isoformat(),
                    submission.scraped_at.isoformat(),
                    submission.provenance.scraper_id,
                    submission.provenance.query_type,
                    submission.provenance.query_value,
                    submission.provenance.job_id,
                    accepted_at,
                ),
            )
            self._increment_operator_quality(
                connection,
                submission.operator_id,
                status,
            )
            connection.commit()

        return entity

    def store_submissions(self, submissions: Iterable[OperatorSubmission]) -> int:
        stored = 0
        for submission in submissions:
            self.store_submission(submission)
            stored += 1
        return stored

    def uri_exists(self, uri: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM data_entities WHERE uri = ? LIMIT 1",
                (normalize_uri(uri),),
            ).fetchone()
        return row is not None

    def record_rejection(
        self,
        submission: OperatorSubmission,
        reasons: list[str],
        details: str = "",
    ) -> None:
        rejected_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO rejected_submissions (
                    submission_id,
                    operator_id,
                    uri,
                    source,
                    label,
                    reasons,
                    details,
                    rejected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission.submission_id,
                    submission.operator_id,
                    normalize_uri(submission.uri),
                    submission.source.value,
                    submission.label,
                    ",".join(reasons),
                    details,
                    rejected_at,
                ),
            )
            self._increment_operator_quality(connection, submission.operator_id, "rejected")
            connection.commit()

    def record_duplicate(self, submission: OperatorSubmission, existing_uri: str) -> None:
        observed_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO duplicate_observations (
                    submission_id,
                    operator_id,
                    uri,
                    existing_uri,
                    observed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    submission.submission_id,
                    submission.operator_id,
                    normalize_uri(submission.uri),
                    normalize_uri(existing_uri),
                    observed_at,
                ),
            )
            self._increment_operator_quality(connection, submission.operator_id, "duplicate")
            connection.commit()

    def get_operator_quality_stats(self, operator_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT operator_id, accepted_scorable, accepted_non_scorable, rejected, duplicate, updated_at
                FROM operator_quality_stats
                WHERE operator_id = ?
                """,
                (operator_id,),
            ).fetchone()
        if row is None:
            return {
                "operator_id": operator_id,
                "accepted_scorable": 0,
                "accepted_non_scorable": 0,
                "rejected": 0,
                "duplicate": 0,
                "updated_at": None,
            }
        return dict(row)

    def get_index(self, miner_id: str) -> MinerIndex:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    time_bucket,
                    source,
                    label,
                    SUM(content_size_bytes) AS size_bytes,
                    COUNT(*) AS item_count,
                    MAX(COALESCE(scraped_at, datetime)) AS last_updated
                FROM data_entities
                GROUP BY time_bucket, source, label
                ORDER BY source, time_bucket, label
                """
            ).fetchall()

        blocks = [
            DataEntityIndexEntry(
                bucket=DataEntityBucketId(
                    time_bucket=int(row["time_bucket"]),
                    source=DataSource(row["source"]),
                    label=row["label"],
                ),
                size_bytes=int(row["size_bytes"]),
                item_count=int(row["item_count"]),
                last_updated=self._parse_datetime(row["last_updated"]),
            )
            for row in rows
        ]
        return MinerIndex(miner_id=miner_id, blocks=blocks)

    def list_entities(
        self,
        *,
        source: Optional[DataSource] = None,
        label: Optional[str] = None,
        start_time_bucket: Optional[int] = None,
        end_time_bucket: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[DataEntity]:
        where_parts: list[str] = []
        params: list[object] = []

        if source is not None:
            where_parts.append("source = ?")
            params.append(source.value)
        if label is not None:
            where_parts.append("label = ?")
            params.append(normalize_label(label))
        if start_time_bucket is not None:
            where_parts.append("time_bucket >= ?")
            params.append(int(start_time_bucket))
        if end_time_bucket is not None:
            where_parts.append("time_bucket <= ?")
            params.append(int(end_time_bucket))

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        limit_sql = "LIMIT ?" if limit is not None else ""
        if limit is not None:
            params.append(int(limit))

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT uri, datetime, source, label, content, content_size_bytes, scraped_at
                FROM data_entities
                {where_sql}
                ORDER BY datetime ASC, uri ASC
                {limit_sql}
                """,
                params,
            ).fetchall()

        return [self._row_to_entity(row) for row in rows]

    def query_bucket(
        self,
        source: DataSource,
        label: Optional[str],
        time_bucket: int,
        limit: int = 100,
    ) -> DataQueryResponse:
        bucket = DataEntityBucketId(
            time_bucket=time_bucket,
            source=source,
            label=normalize_label(label),
        )

        where_sql, params = self._bucket_filter(bucket)
        with self._connect() as connection:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS total_count FROM data_entities WHERE {where_sql}",
                params,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT uri, datetime, source, label, content, content_size_bytes, scraped_at
                FROM data_entities
                WHERE {where_sql}
                ORDER BY datetime ASC, uri ASC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()

        entities = [self._row_to_entity(row) for row in rows]
        total_count = int(total_row["total_count"]) if total_row else 0
        return DataQueryResponse(
            bucket=bucket,
            entities=entities,
            total_count=total_count,
            has_more=total_count > len(entities),
        )

    def get_all_buckets(self) -> list[DataEntityBucket]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT time_bucket, source, label
                FROM data_entities
                ORDER BY source, time_bucket, label
                """
            ).fetchall()

        buckets: list[DataEntityBucket] = []
        for row in rows:
            query = self.query_bucket(
                source=DataSource(row["source"]),
                label=row["label"],
                time_bucket=int(row["time_bucket"]),
                limit=10_000,
            )
            buckets.append(
                DataEntityBucket(
                    id=query.bucket,
                    entities=query.entities,
                )
            )
        return buckets

    def get_buckets_for_source(self, source: DataSource) -> list[DataEntityBucket]:
        return [bucket for bucket in self.get_all_buckets() if bucket.source == source]

    def get_buckets_for_label(self, label: str) -> list[DataEntityBucket]:
        normalized = normalize_label(label)
        return [bucket for bucket in self.get_all_buckets() if bucket.label == normalized]

    def health_check(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def _bucket_filter(self, bucket: DataEntityBucketId) -> tuple[str, list]:
        where_sql = "time_bucket = ? AND source = ?"
        params: list[object] = [bucket.time_bucket, bucket.source.value]
        if bucket.label is None:
            where_sql += " AND label IS NULL"
        else:
            where_sql += " AND label = ?"
            params.append(bucket.label)
        return where_sql, params

    def _row_to_entity(self, row: sqlite3.Row) -> DataEntity:
        return DataEntity(
            uri=normalize_uri(row["uri"]),
            datetime=self._parse_datetime(row["datetime"]),
            source=DataSource(row["source"]),
            label=row["label"],
            content=row["content"],
            content_size_bytes=int(row["content_size_bytes"]),
            scraped_at=self._parse_datetime(row["scraped_at"]) if row["scraped_at"] else None,
        )

    def _parse_datetime(self, value: str) -> datetime:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))

    def _increment_operator_quality(
        self,
        connection: sqlite3.Connection,
        operator_id: str,
        status: str,
    ) -> None:
        allowed = {"accepted_scorable", "accepted_non_scorable", "rejected", "duplicate"}
        if status not in allowed:
            raise StorageError(f"Unknown operator quality status: {status}")
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO operator_quality_stats (operator_id, updated_at)
            VALUES (?, ?)
            ON CONFLICT(operator_id) DO NOTHING
            """,
            (operator_id, now),
        )
        connection.execute(
            f"""
            UPDATE operator_quality_stats
            SET {status} = {status} + 1,
                updated_at = ?
            WHERE operator_id = ?
            """,
            (now, operator_id),
        )


def create_storage(db_path: Optional[Path] = None) -> StorageBackend:
    return SQLiteStorage(db_path or Path(__file__).parent / "data" / "sn13.sqlite3")
