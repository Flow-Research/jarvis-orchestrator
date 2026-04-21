#!/usr/bin/env python3
"""
Canonical SN13 miner models.

This module defines the subnet-facing truth that Jarvis must preserve for
Subnet 13. Operator attribution and intake metadata belong elsewhere.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_LABEL_LENGTH = 140
DEFAULT_ENTITY_ENCODING = "utf-8"
TimeBucket = Annotated[int, Field(ge=0, description="Hour bucket since epoch")]
Label = Annotated[str, Field(min_length=1, max_length=MAX_LABEL_LENGTH)]
Source = "DataSource"


def ensure_utc(value: datetime) -> datetime:
    """Normalize datetimes to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def time_bucket_from_datetime(value: datetime) -> int:
    """Convert a UTC datetime into the canonical SN13 hour bucket."""
    return int(ensure_utc(value).timestamp() // 3600)


def datetime_from_time_bucket(bucket_id: int) -> datetime:
    """Convert an hour bucket back into the bucket start time in UTC."""
    return datetime.fromtimestamp(bucket_id * 3600, tz=timezone.utc)


def normalize_label(value: Optional[str]) -> Optional[str]:
    """Normalize labels to the stable form used by SN13-style storage."""
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None


def normalize_uri(value: str) -> str:
    """Best-effort URI normalization for internal consistency."""
    normalized = value.strip().replace("twitter.com", "x.com").replace(" ", "%20")
    parsed = urlparse(normalized)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, parsed.netloc.casefold(), path, "", "", ""))
    return normalized


class DataSource(str, Enum):
    """Supported data sources for SN13."""

    X = "X"
    REDDIT = "REDDIT"
    YOUTUBE = "YOUTUBE"


class DataEntity(BaseModel):
    """
    Canonical miner-facing data entity.

    This is the storage truth Jarvis should use to build buckets, indexes,
    validator responses, and downstream exports.
    """

    model_config = {"frozen": True}

    uri: str = Field(..., min_length=1)
    datetime: datetime
    source: DataSource
    label: Optional[Label] = None
    content: bytes = Field(..., min_length=1)
    content_size_bytes: Optional[int] = Field(default=None, ge=1)
    scraped_at: Optional[datetime] = None

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str) -> str:
        return normalize_uri(value)

    @field_validator("datetime", "scraped_at")
    @classmethod
    def validate_datetime_fields(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: bytes | str | dict[str, Any]) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode(DEFAULT_ENTITY_ENCODING)
        return json.dumps(value, sort_keys=True, ensure_ascii=False).encode(DEFAULT_ENTITY_ENCODING)

    @model_validator(mode="after")
    def validate_size(self) -> "DataEntity":
        actual_size = len(self.content)
        if self.content_size_bytes is None:
            object.__setattr__(self, "content_size_bytes", actual_size)
        elif self.content_size_bytes != actual_size:
            raise ValueError(
                f"content_size_bytes={self.content_size_bytes} does not match actual bytes={actual_size}"
            )
        return self

    @property
    def time_bucket(self) -> int:
        return time_bucket_from_datetime(self.datetime)

    @property
    def bucket_id(self) -> "DataEntityBucketId":
        return DataEntityBucketId(
            time_bucket=self.time_bucket,
            source=self.source,
            label=self.label,
        )

    @property
    def text_content(self) -> str:
        try:
            decoded = self.content.decode(DEFAULT_ENTITY_ENCODING)
        except UnicodeDecodeError:
            return ""

        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            return decoded

        if not isinstance(payload, dict):
            return decoded

        for key in ("text", "body", "title", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return decoded

    @property
    def decoded_content(self) -> Any:
        try:
            decoded = self.content.decode(DEFAULT_ENTITY_ENCODING)
        except UnicodeDecodeError:
            return self.content.hex()

        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            return decoded


class DataEntityBucketId(BaseModel):
    """Canonical identifier for a bucket."""

    model_config = {"frozen": True}

    time_bucket: TimeBucket
    source: DataSource
    label: Optional[Label] = None

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @property
    def key(self) -> str:
        label = self.label or "unlabeled"
        return f"{self.source.value}_{self.time_bucket}_{label}"


class DataEntityBucket(BaseModel):
    """Logical grouping of entities by source, bucket, and label."""

    model_config = {"frozen": True}

    id: DataEntityBucketId
    entities: list[DataEntity] = Field(default_factory=list)
    size_bytes: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_size(self) -> "DataEntityBucket":
        computed = sum(entity.content_size_bytes for entity in self.entities)
        if self.size_bytes is None:
            object.__setattr__(self, "size_bytes", computed)
        return self

    @property
    def bucket_id(self) -> str:
        return self.id.key

    @property
    def source(self) -> DataSource:
        return self.id.source

    @property
    def label(self) -> Optional[str]:
        return self.id.label

    @property
    def time_bucket(self) -> int:
        return self.id.time_bucket

    @property
    def count(self) -> int:
        return len(self.entities)

    @property
    def total_bytes(self) -> int:
        return self.size_bytes or 0


class DataEntityIndexEntry(BaseModel):
    """Summary of a single bucket present on the miner."""

    model_config = {"frozen": True}

    bucket: DataEntityBucketId
    size_bytes: int = Field(..., ge=0)
    item_count: int = Field(..., ge=0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("last_updated")
    @classmethod
    def validate_last_updated(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @property
    def bucket_id(self) -> str:
        return self.bucket.key

    @property
    def source(self) -> DataSource:
        return self.bucket.source

    @property
    def label(self) -> Optional[str]:
        return self.bucket.label

    @property
    def time_bucket(self) -> int:
        return self.bucket.time_bucket


class MinerIndex(BaseModel):
    """Summary of the miner's available buckets."""

    model_config = {"frozen": True}

    miner_id: str = Field(..., min_length=1, description="Miner hotkey SS58 address")
    blocks: list[DataEntityIndexEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetime_fields(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @property
    def total_data_items(self) -> int:
        return sum(block.item_count for block in self.blocks)

    @property
    def total_bytes(self) -> int:
        return sum(block.size_bytes for block in self.blocks)

    @property
    def sources(self) -> set[DataSource]:
        return {block.source for block in self.blocks}

    @property
    def labels(self) -> set[str]:
        return {block.label for block in self.blocks if block.label is not None}

    def to_compressed_index(self) -> dict[str, Any]:
        return {
            "compressed_index": {
                "buckets": [
                    {
                        "source": block.source.value,
                        "time_bucket": block.time_bucket,
                        "label": block.label,
                        "size_bytes": block.size_bytes,
                        "item_count": block.item_count,
                    }
                    for block in self.blocks
                ],
                "total_bytes": self.total_bytes,
                "total_items": self.total_data_items,
            }
        }


class DataQueryResponse(BaseModel):
    """Result of looking up a bucket from storage."""

    model_config = {"frozen": True}

    bucket: DataEntityBucketId
    entities: list[DataEntity]
    total_count: int = Field(..., ge=0)
    page: int = Field(default=0, ge=0)
    has_more: bool = False

    @property
    def bucket_id(self) -> str:
        return self.bucket.key

    @property
    def source(self) -> DataSource:
        return self.bucket.source

    @property
    def label(self) -> Optional[str]:
        return self.bucket.label

    @property
    def time_bucket(self) -> int:
        return self.bucket.time_bucket
