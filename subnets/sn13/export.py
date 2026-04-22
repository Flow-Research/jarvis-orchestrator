#!/usr/bin/env python3
"""
SN13 parquet export from canonical SQLite storage.

This module intentionally mirrors the current Macrocosm SN13 S3 validation
shape for Reddit and X exports. It does not upload files; it creates local
parquet artifacts and path metadata that an uploader can hand to the SN13 API.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Avoid pyarrow wheels selecting CPU instructions unavailable on some hosts.
os.environ.setdefault("ARROW_USER_SIMD_LEVEL", "NONE")

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field, field_validator

from .desirability import DesirabilityJob
from .models import DataEntity, DataSource, ensure_utc, normalize_label
from .storage import StorageBackend

EXPORT_FILENAME_RE = re.compile(
    r"^data_(?P<timestamp>\d{8}_\d{6})_(?P<count>\d+)_(?P<hex>[a-f0-9]{16})\.parquet$"
)

EXPECTED_COLUMNS_X: tuple[str, ...] = (
    "datetime",
    "label",
    "username",
    "text",
    "tweet_hashtags",
    "timestamp",
    "url",
    "media",
    "user_id",
    "user_display_name",
    "user_verified",
    "tweet_id",
    "is_reply",
    "is_quote",
    "conversation_id",
    "in_reply_to_user_id",
    "language",
    "in_reply_to_username",
    "quoted_tweet_id",
    "like_count",
    "retweet_count",
    "reply_count",
    "quote_count",
    "view_count",
    "bookmark_count",
    "user_blue_verified",
    "user_description",
    "user_location",
    "profile_image_url",
    "cover_picture_url",
    "user_followers_count",
    "user_following_count",
    "scraped_at",
)

EXPECTED_COLUMNS_REDDIT: tuple[str, ...] = (
    "datetime",
    "label",
    "id",
    "username",
    "communityName",
    "body",
    "title",
    "createdAt",
    "dataType",
    "parentId",
    "url",
    "media",
    "is_nsfw",
    "score",
    "upvote_ratio",
    "num_comments",
    "scrapedAt",
)


class ExportError(Exception):
    """Base exception for SN13 export failures."""


class UnsupportedExportSourceError(ExportError):
    """Raised when a source has no confirmed upstream export schema."""


class SN13ExportJob(BaseModel):
    """Concrete export target, normally derived from a Gravity desirability job."""

    model_config = {"frozen": True}

    job_id: str = Field(..., min_length=1, max_length=128)
    source: DataSource
    label: str | None = Field(default=None, max_length=140)
    keyword: str | None = Field(default=None, max_length=140)
    start_time_bucket: int | None = Field(default=None, ge=0)
    end_time_bucket: int | None = Field(default=None, ge=0)
    max_rows: int | None = Field(default=None, ge=1)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str | None) -> str | None:
        return value.strip().casefold() if value else None

    @classmethod
    def from_desirability_job(
        cls,
        job: DesirabilityJob,
        *,
        max_rows: int | None = None,
    ) -> SN13ExportJob:
        return cls(
            job_id=job.job_id,
            source=job.source,
            label=job.label,
            keyword=job.keyword,
            start_time_bucket=job.start_time_bucket,
            end_time_bucket=job.end_time_bucket,
            max_rows=max_rows,
        )

    def matches_entity(self, entity: DataEntity) -> bool:
        if entity.source != self.source:
            return False
        if self.start_time_bucket is not None and entity.time_bucket < self.start_time_bucket:
            return False
        if self.end_time_bucket is not None and entity.time_bucket > self.end_time_bucket:
            return False

        content = _content_dict(entity)
        if self.label is not None and not _label_matches(self.source, self.label, entity, content):
            return False
        if self.keyword is not None and self.keyword not in _search_text(
            self.source,
            entity,
            content,
        ):
            return False
        return True


class ExportResult(BaseModel):
    """Metadata for one local parquet export artifact."""

    model_config = {"frozen": True}

    job_id: str
    source: DataSource
    row_count: int = Field(..., ge=0)
    file_path: Path | None = None
    filename: str | None = None
    s3_relative_path: str | None = None
    s3_logical_path: str | None = None
    skipped: bool = False
    reason: str | None = None


class SN13ParquetExporter:
    """Build SN13-compatible parquet files from accepted canonical storage."""

    def __init__(
        self,
        *,
        storage: StorageBackend,
        output_root: Path,
        miner_hotkey: str,
    ):
        self.storage = storage
        self.output_root = output_root
        self.miner_hotkey = miner_hotkey

    def export_job(
        self,
        job: SN13ExportJob,
        *,
        now: datetime | None = None,
        hex_token: str | None = None,
    ) -> ExportResult:
        entities = self.storage.list_entities(
            source=job.source,
            label=None,
            start_time_bucket=job.start_time_bucket,
            end_time_bucket=job.end_time_bucket,
            limit=None,
        )
        matched = [entity for entity in entities if job.matches_entity(entity)]
        if job.max_rows is not None:
            matched = matched[: job.max_rows]

        if not matched:
            return ExportResult(
                job_id=job.job_id,
                source=job.source,
                row_count=0,
                skipped=True,
                reason="no_matching_canonical_data",
            )

        rows = build_export_rows(matched, job.source)
        filename = build_export_filename(
            record_count=len(rows),
            now=now,
            hex_token=hex_token,
        )
        output_dir = self.output_root / f"hotkey={self.miner_hotkey}" / f"job_id={job.job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / filename

        write_parquet_rows(file_path, rows, expected_columns_for_source(job.source))
        validate_filename_row_count(filename, len(rows))

        return ExportResult(
            job_id=job.job_id,
            source=job.source,
            row_count=len(rows),
            file_path=file_path,
            filename=filename,
            s3_relative_path=f"job_id={job.job_id}/{filename}",
            s3_logical_path=f"hotkey={self.miner_hotkey}/job_id={job.job_id}/{filename}",
        )


def build_export_filename(
    *,
    record_count: int,
    now: datetime | None = None,
    hex_token: str | None = None,
) -> str:
    if record_count < 0:
        raise ValueError("record_count must be non-negative")

    timestamp = ensure_utc(now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    token = (hex_token or secrets.token_hex(8)).lower()
    if not re.fullmatch(r"[a-f0-9]{16}", token):
        raise ValueError("hex_token must be exactly 16 lowercase hexadecimal characters")
    return f"data_{timestamp}_{record_count}_{token}.parquet"


def is_valid_export_filename(filename: str) -> bool:
    return EXPORT_FILENAME_RE.fullmatch(filename) is not None


def extract_record_count_from_filename(filename: str) -> int:
    match = EXPORT_FILENAME_RE.fullmatch(filename)
    if match is None:
        raise ValueError(f"Invalid SN13 export filename: {filename}")
    return int(match.group("count"))


def validate_filename_row_count(filename: str, actual_row_count: int) -> None:
    claimed = extract_record_count_from_filename(filename)
    if claimed != actual_row_count:
        raise ValueError(
            f"filename row count {claimed} does not match parquet row count {actual_row_count}"
        )


def expected_columns_for_source(source: DataSource) -> tuple[str, ...]:
    if source == DataSource.X:
        return EXPECTED_COLUMNS_X
    if source == DataSource.REDDIT:
        return EXPECTED_COLUMNS_REDDIT
    raise UnsupportedExportSourceError(
        f"No confirmed SN13 export schema for source: {source.value}"
    )


def build_export_rows(entities: list[DataEntity], source: DataSource) -> list[dict[str, Any]]:
    if source == DataSource.X:
        return [_x_row(entity) for entity in entities]
    if source == DataSource.REDDIT:
        return [_reddit_row(entity) for entity in entities]
    raise UnsupportedExportSourceError(
        f"No confirmed SN13 export schema for source: {source.value}"
    )


def write_parquet_rows(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    table_data = {column: [row.get(column) for row in rows] for column in columns}
    table = pa.table(table_data)
    if tuple(table.column_names) != columns:
        raise ExportError("parquet table column order does not match upstream schema")
    pq.write_table(table, path, compression="snappy", row_group_size=10_000)


def _x_row(entity: DataEntity) -> dict[str, Any]:
    content = _content_dict(entity)
    return {
        "datetime": entity.datetime,
        "label": entity.label,
        "username": content.get("username"),
        "text": content.get("text"),
        "tweet_hashtags": content.get("tweet_hashtags", _default_x_hashtags(entity)),
        "timestamp": content.get("timestamp") or entity.datetime.isoformat(),
        "url": content.get("url") or entity.uri,
        "media": content.get("media"),
        "user_id": content.get("user_id"),
        "user_display_name": content.get("user_display_name"),
        "user_verified": content.get("user_verified"),
        "tweet_id": content.get("tweet_id"),
        "is_reply": content.get("is_reply"),
        "is_quote": content.get("is_quote"),
        "conversation_id": content.get("conversation_id"),
        "in_reply_to_user_id": content.get("in_reply_to_user_id"),
        "language": content.get("language"),
        "in_reply_to_username": content.get("in_reply_to_username"),
        "quoted_tweet_id": content.get("quoted_tweet_id"),
        "like_count": content.get("like_count"),
        "retweet_count": content.get("retweet_count"),
        "reply_count": content.get("reply_count"),
        "quote_count": content.get("quote_count"),
        "view_count": content.get("view_count"),
        "bookmark_count": content.get("bookmark_count"),
        "user_blue_verified": content.get("user_blue_verified"),
        "user_description": content.get("user_description"),
        "user_location": content.get("user_location"),
        "profile_image_url": content.get("profile_image_url"),
        "cover_picture_url": content.get("cover_picture_url"),
        "user_followers_count": content.get("user_followers_count"),
        "user_following_count": content.get("user_following_count"),
        "scraped_at": content.get("scraped_at")
        or content.get("scrapedAt")
        or _iso_or_none(entity.scraped_at),
    }


def _reddit_row(entity: DataEntity) -> dict[str, Any]:
    content = _content_dict(entity)
    return {
        "datetime": entity.datetime,
        "label": entity.label,
        "id": content.get("id"),
        "username": content.get("username"),
        "communityName": content.get("communityName") or content.get("subreddit"),
        "body": content.get("body"),
        "title": content.get("title"),
        "createdAt": content.get("createdAt") or entity.datetime.isoformat(),
        "dataType": content.get("dataType"),
        "parentId": content.get("parentId"),
        "url": content.get("url") or entity.uri,
        "media": content.get("media"),
        "is_nsfw": content.get("is_nsfw"),
        "score": content.get("score"),
        "upvote_ratio": content.get("upvote_ratio"),
        "num_comments": content.get("num_comments"),
        "scrapedAt": content.get("scrapedAt")
        or content.get("scraped_at")
        or _iso_or_none(entity.scraped_at),
    }


def _content_dict(entity: DataEntity) -> dict[str, Any]:
    decoded = entity.decoded_content
    return decoded if isinstance(decoded, dict) else {}


def _search_text(source: DataSource, entity: DataEntity, content: dict[str, Any]) -> str:
    if source == DataSource.X:
        fields = [content.get("text"), entity.text_content]
    elif source == DataSource.REDDIT:
        fields = [content.get("body"), content.get("title"), entity.text_content]
    else:
        fields = [entity.text_content]
    return " ".join(str(field).casefold() for field in fields if field)


def _label_matches(
    source: DataSource,
    desired_label: str,
    entity: DataEntity,
    content: dict[str, Any],
) -> bool:
    if source == DataSource.X:
        target = _strip_hash(desired_label)
        candidates = [entity.label, content.get("label")]
        hashtags = content.get("tweet_hashtags") or []
        if isinstance(hashtags, str):
            candidates.append(hashtags)
        elif isinstance(hashtags, list):
            candidates.extend(str(item) for item in hashtags)
        return any(_strip_hash(candidate) == target for candidate in candidates if candidate)

    if source == DataSource.REDDIT:
        target = _strip_reddit_prefix(desired_label)
        candidates = [
            entity.label,
            content.get("label"),
            content.get("communityName"),
            content.get("subreddit"),
        ]
        return any(
            _strip_reddit_prefix(candidate) == target for candidate in candidates if candidate
        )

    return normalize_label(desired_label) == entity.label


def _strip_hash(value: str) -> str:
    return str(value).strip().casefold().lstrip("#")


def _strip_reddit_prefix(value: str) -> str:
    return str(value).strip().casefold().removeprefix("r/")


def _default_x_hashtags(entity: DataEntity) -> list[str]:
    if entity.label and entity.label.startswith("#"):
        return [entity.label]
    return []


def _iso_or_none(value: datetime | None) -> str | None:
    return ensure_utc(value).isoformat() if value else None
