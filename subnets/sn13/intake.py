#!/usr/bin/env python3
"""
Operator intake models and normalization for SN13.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .models import (
    DataEntity,
    DataSource,
    ensure_utc,
    normalize_label,
    normalize_uri,
)

OperatorId = str


class SubmissionProvenance(BaseModel):
    """Internal audit metadata for a submission."""

    model_config = {"frozen": True}

    scraper_id: str = Field(..., min_length=1, max_length=128)
    query_type: str = Field(..., min_length=1, max_length=64)
    query_value: str | None = Field(default=None, max_length=256)
    job_id: str | None = Field(default=None, max_length=128)


class OperatorSubmission(BaseModel):
    """
    Operator-provided payload before Jarvis converts it into miner truth.
    """

    model_config = {"frozen": True}

    submission_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    operator_id: str = Field(..., min_length=1, max_length=64)
    source: DataSource
    label: str | None = Field(default=None, max_length=140)
    uri: str = Field(..., min_length=1)
    source_created_at: datetime
    scraped_at: datetime
    content: dict[str, Any] = Field(default_factory=dict)
    provenance: SubmissionProvenance

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str) -> str:
        return normalize_uri(value)

    @field_validator("source_created_at", "scraped_at")
    @classmethod
    def validate_datetimes(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("operator_id")
    @classmethod
    def validate_operator_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operator_id must be non-empty")
        return value.strip()

    def to_data_entity(self) -> DataEntity:
        return DataEntity(
            uri=self.uri,
            datetime=self.source_created_at,
            source=self.source,
            label=self.label,
            content=self.content,
            scraped_at=self.scraped_at,
        )
