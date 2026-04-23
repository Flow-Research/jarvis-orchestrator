import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.listener.protocol_adapter import (
    PROTOCOL_VERSION,
    UnsupportedProtocolSourceError,
    bind_get_contents_by_buckets_response,
    bind_get_data_entity_bucket_response,
    bind_get_miner_index_response,
    bucket_id_from_synapse,
    data_entity_to_upstream_dict,
    miner_index_to_upstream_compressed,
    upstream_source_id,
)
from subnets.sn13.models import DataSource
from subnets.sn13.storage import SQLiteStorage

SOURCE_TIME = datetime(1970, 3, 18, 21, 0, tzinfo=timezone.utc)
SCRAPED_AT = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)


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


def _reddit_submission() -> OperatorSubmission:
    return OperatorSubmission(
        operator_id="operator_2",
        source=DataSource.REDDIT,
        label="Bittensor",
        uri="https://www.reddit.com/r/Bittensor/comments/abc1234/example",
        source_created_at=SOURCE_TIME,
        scraped_at=SCRAPED_AT,
        content={
            "id": "abc1234",
            "username": "tao_holder",
            "body": "TAO is the future",
            "title": "TAO is the future",
            "url": "https://www.reddit.com/r/Bittensor/comments/abc1234/example",
            "createdAt": SOURCE_TIME.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="reddit.custom.v1",
            query_type="subreddit_search",
            query_value="bittensor",
        ),
    )


def test_miner_index_compression_matches_upstream_shape(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_x_submission())
    storage.store_submission(_reddit_submission())

    compressed = miner_index_to_upstream_compressed(storage.get_index("miner_hotkey"))

    assert set(compressed) == {"sources"}
    assert set(compressed["sources"]) == {"1", "2"}
    assert compressed["sources"]["1"][0]["label"] == "bittensor"
    assert compressed["sources"]["1"][0]["time_bucket_ids"] == [1845]
    assert compressed["sources"]["2"][0]["label"] == "$btc"
    assert compressed["sources"]["2"][0]["time_bucket_ids"] == [1845]


def test_bind_get_miner_index_sets_compressed_index_serialized_and_version(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_x_submission())
    synapse = SimpleNamespace(version=4, compressed_index_serialized=None)

    bind_get_miner_index_response(synapse, storage=storage, miner_hotkey="miner_hotkey")

    payload = json.loads(synapse.compressed_index_serialized)
    assert synapse.version == PROTOCOL_VERSION
    assert payload["sources"]["2"][0]["label"] == "$btc"
    assert payload["sources"]["2"][0]["sizes_bytes"][0] > 0


def test_bind_get_data_entity_bucket_sets_upstream_data_entities(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_x_submission())
    synapse = SimpleNamespace(
        version=4,
        data_entity_bucket_id={
            "time_bucket": {"id": 1845},
            "source": 2,
            "label": {"value": "$BTC"},
        },
        data_entities=[],
    )

    data_entities = bind_get_data_entity_bucket_response(synapse, storage=storage)

    assert synapse.version == PROTOCOL_VERSION
    assert synapse.data_entities == data_entities
    assert data_entities[0]["uri"] == "https://x.com/example/status/123456789"
    assert data_entities[0]["source"] == 2
    assert data_entities[0]["label"] == {"value": "$btc"}
    assert (
        data_entities[0]["content"]
        == storage.query_bucket(DataSource.X, "$BTC", 1845).entities[0].content
    )


def test_bind_get_contents_by_buckets_sets_flattened_bucket_content_pairs(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_x_submission())
    synapse = SimpleNamespace(
        version=4,
        data_entity_bucket_ids=[
            {
                "time_bucket": {"id": 1845},
                "source": 2,
                "label": {"value": "$btc"},
            }
        ],
        bucket_ids_to_contents=[],
    )

    pairs = bind_get_contents_by_buckets_response(synapse, storage=storage)

    assert synapse.version == PROTOCOL_VERSION
    assert synapse.bucket_ids_to_contents == pairs
    assert pairs[0][0] == {
        "time_bucket": {"id": 1845},
        "source": 2,
        "label": {"value": "$btc"},
    }
    assert len(pairs[0][1]) == 1
    assert isinstance(pairs[0][1][0], bytes)


def test_contents_request_over_bulk_limit_is_left_unbound(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    synapse = SimpleNamespace(
        version=4,
        data_entity_bucket_ids=[
            {"time_bucket": {"id": 1845}, "source": 2, "label": {"value": "$btc"}}
            for _ in range(101)
        ],
        bucket_ids_to_contents=[],
    )

    result = bind_get_contents_by_buckets_response(synapse, storage=storage)

    assert result == []
    assert synapse.bucket_ids_to_contents == []


def test_bucket_id_parser_accepts_local_and_upstream_shapes():
    upstream = bucket_id_from_synapse(
        {
            "time_bucket": {"id": 1845},
            "source": 1,
            "label": {"value": "r/Bittensor"},
        }
    )
    local = bucket_id_from_synapse(
        {
            "time_bucket_id": 1845,
            "source": "X",
            "label": "$BTC",
        }
    )

    assert upstream.source == DataSource.REDDIT
    assert upstream.label == "r/bittensor"
    assert local.source == DataSource.X
    assert local.label == "$btc"


def test_entity_conversion_uses_confirmed_upstream_source_ids(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    entity = storage.store_submission(_x_submission())

    payload = data_entity_to_upstream_dict(entity)

    assert payload["source"] == 2
    assert payload["label"] == {"value": "$btc"}
    assert payload["content_size_bytes"] == len(payload["content"])


def test_youtube_protocol_source_id_is_blocked_until_confirmed():
    with pytest.raises(UnsupportedProtocolSourceError):
        upstream_source_id(DataSource.YOUTUBE)
