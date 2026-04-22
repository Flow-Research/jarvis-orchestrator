#!/usr/bin/env python3
"""
Local SN13 protocol synapse classes.

These classes mirror the confirmed upstream SN13 request names and response
fields that Jarvis currently depends on. They intentionally stay minimal and
only encode the fields already grounded in the assumption ledger and adapter
tests.
"""

from __future__ import annotations

from typing import Any

import bittensor as bt
from pydantic import Field

from .protocol_adapter import PROTOCOL_VERSION


class GetMinerIndex(bt.Synapse):
    """SN13 miner-index request/response."""

    version: int = PROTOCOL_VERSION
    compressed_index_serialized: str | None = None


class GetDataEntityBucket(bt.Synapse):
    """SN13 single-bucket request/response."""

    version: int = PROTOCOL_VERSION
    data_entity_bucket_id: dict[str, Any] = Field(default_factory=dict)
    data_entities: list[dict[str, Any]] = Field(default_factory=list)


class GetContentsByBuckets(bt.Synapse):
    """SN13 multi-bucket contents request/response."""

    version: int = PROTOCOL_VERSION
    data_entity_bucket_ids: list[dict[str, Any]] = Field(default_factory=list)
    bucket_ids_to_contents: list[tuple[dict[str, Any], list[bytes]]] = Field(default_factory=list)
