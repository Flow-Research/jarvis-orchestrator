from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.models import DataSource, time_bucket_from_datetime
from subnets.sn13.storage import SQLiteStorage


def test_operator_submission_converts_to_canonical_data_entity():
    submission = OperatorSubmission(
        operator_id="operator_7",
        source=DataSource.X,
        label="$BTC",
        uri="https://twitter.com/example/status/12345",
        source_created_at=datetime(2026, 4, 21, 12, 10, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 4, 21, 12, 12, tzinfo=timezone.utc),
        content={
            "tweet_id": "12345",
            "username": "example",
            "text": "hello world",
            "url": "https://twitter.com/example/status/12345",
            "timestamp": "2026-04-21T12:10:00Z",
        },
        provenance=SubmissionProvenance(
            scraper_id="x.custom.v1",
            query_type="label_search",
            query_value="$BTC",
        ),
    )

    entity = submission.to_data_entity()

    assert entity.source == DataSource.X
    assert entity.label == "$btc"
    assert entity.uri == "https://x.com/example/status/12345"
    assert entity.time_bucket == time_bucket_from_datetime(submission.source_created_at)
    assert entity.content_size_bytes == len(entity.content)


def test_operator_submission_rejects_naive_datetimes():
    with pytest.raises(ValidationError, match="timezone offset"):
        OperatorSubmission(
            operator_id="operator_7",
            source=DataSource.X,
            label="$BTC",
            uri="https://twitter.com/example/status/12345",
            source_created_at=datetime(2026, 4, 21, 12, 10),
            scraped_at=datetime(2026, 4, 21, 12, 12),
            content={
                "tweet_id": "12345",
                "username": "example",
                "text": "hello world",
                "url": "https://twitter.com/example/status/12345",
                "timestamp": "2026-04-21T12:10:00Z",
            },
            provenance=SubmissionProvenance(
                scraper_id="x.custom.v1",
                query_type="label_search",
                query_value="$BTC",
            ),
        )


def test_sqlite_storage_builds_index_and_query_from_canonical_entities(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(
        OperatorSubmission(
            operator_id="operator_1",
            source=DataSource.X,
            label="$BTC",
            uri="https://x.com/example/status/123456789",
            source_created_at=datetime(1970, 3, 18, 21, 0, tzinfo=timezone.utc),
            scraped_at=datetime(2026, 4, 21, 11, 30, tzinfo=timezone.utc),
            content={
                "tweet_id": "123456789",
                "username": "example",
                "text": "BTC just broke resistance",
                "url": "https://x.com/example/status/123456789",
                "timestamp": "1970-03-18T21:00:00Z",
            },
            provenance=SubmissionProvenance(
                scraper_id="x.custom.v1",
                query_type="label_search",
                query_value="$BTC",
            ),
        )
    )

    index = storage.get_index("miner_hotkey")

    assert len(index.blocks) == 1
    assert index.blocks[0].label == "$btc"
    assert index.blocks[0].item_count == 1
    assert index.blocks[0].size_bytes > 0

    bucket = storage.query_bucket(DataSource.X, "$BTC", 1845, limit=10)

    assert bucket.total_count == 1
    assert bucket.entities[0].uri == "https://x.com/example/status/123456789"
    assert bucket.entities[0].label == "$btc"
    assert bucket.entities[0].decoded_content["tweet_id"] == "123456789"


def test_sqlite_storage_normalizes_query_label_case(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(
        OperatorSubmission(
            operator_id="operator_2",
            source=DataSource.REDDIT,
            label="Bittensor",
            uri="https://reddit.com/r/Bittensor/comments/def456",
            source_created_at=datetime(1970, 3, 18, 21, 0, tzinfo=timezone.utc),
            scraped_at=datetime(2026, 4, 21, 11, 45, tzinfo=timezone.utc),
            content={
                "id": "def456",
                "username": "tao_holder",
                "body": "TAO is the future",
                "title": "TAO is the future",
                "url": "https://reddit.com/r/Bittensor/comments/def456",
                "createdAt": "1970-03-18T21:00:00Z",
            },
            provenance=SubmissionProvenance(
                scraper_id="reddit.custom.v1",
                query_type="subreddit_search",
                query_value="bittensor",
            ),
        )
    )

    bucket = storage.query_bucket(DataSource.REDDIT, "bittensor", 1845, limit=10)

    assert bucket.total_count == 1
    assert bucket.entities[0].label == "bittensor"
