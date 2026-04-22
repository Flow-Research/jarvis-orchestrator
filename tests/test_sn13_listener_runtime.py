from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.listener.protocol import (
    GetContentsByBuckets,
    GetDataEntityBucket,
    GetMinerIndex,
)
from subnets.sn13.listener.runtime import SN13ListenerRuntime
from subnets.sn13.models import DataSource

SOURCE_TIME = datetime(1970, 3, 18, 21, 0, tzinfo=timezone.utc)
SCRAPED_AT = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)


def _x_submission() -> OperatorSubmission:
    return OperatorSubmission(
        operator_id="operator_1",
        source=DataSource.X,
        label="$BTC",
        uri="https://x.com/example/status/123456789",
        source_created_at=SOURCE_TIME,
        scraped_at=SCRAPED_AT,
        content={
            "tweet_id": "123456789",
            "username": "example",
            "text": "BTC just broke resistance",
            "url": "https://x.com/example/status/123456789",
            "timestamp": SOURCE_TIME.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="x.custom.v1",
            query_type="label_search",
            query_value="$BTC",
        ),
    )


def _build_runtime(tmp_path: Path) -> SN13ListenerRuntime:
    runtime = SN13ListenerRuntime(
        db_path=tmp_path / "sn13.sqlite3",
        capture_dir=tmp_path / "captures",
        wallet_name="sn13miner",
        offline=True,
        miner_hotkey="miner_hotkey",
    )
    runtime.storage.store_submission(_x_submission())
    return runtime


def test_runtime_handles_get_miner_index_and_records_capture(tmp_path: Path) -> None:
    runtime = _build_runtime(tmp_path)
    synapse = GetMinerIndex()

    response = runtime.handle_get_miner_index(synapse)

    payload = json.loads(response.compressed_index_serialized)
    assert payload["sources"]["2"][0]["label"] == "$btc"

    summary = json.loads((tmp_path / "captures" / "summary.json").read_text())
    assert summary["counts_by_query_type"]["GetMinerIndex"] == 1


def test_runtime_handles_bucket_query_and_records_capture(tmp_path: Path) -> None:
    runtime = _build_runtime(tmp_path)
    synapse = GetDataEntityBucket(
        data_entity_bucket_id={
            "time_bucket": {"id": 1845},
            "source": 2,
            "label": {"value": "$BTC"},
        }
    )

    response = runtime.handle_get_data_entity_bucket(synapse)

    assert response.data_entities[0]["uri"] == "https://x.com/example/status/123456789"
    summary = json.loads((tmp_path / "captures" / "summary.json").read_text())
    assert summary["counts_by_query_type"]["GetDataEntityBucket"] == 1


def test_runtime_handles_contents_query_and_records_capture(tmp_path: Path) -> None:
    runtime = _build_runtime(tmp_path)
    synapse = GetContentsByBuckets(
        data_entity_bucket_ids=[
            {
                "time_bucket": {"id": 1845},
                "source": 2,
                "label": {"value": "$btc"},
            }
        ]
    )

    response = runtime.handle_get_contents_by_buckets(synapse)

    assert len(response.bucket_ids_to_contents) == 1
    assert isinstance(response.bucket_ids_to_contents[0][1][0], bytes)

    summary = json.loads((tmp_path / "captures" / "summary.json").read_text())
    assert summary["counts_by_query_type"]["GetContentsByBuckets"] == 1
