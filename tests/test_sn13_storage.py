from datetime import datetime, timedelta, timezone

from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.models import DataSource, time_bucket_from_datetime
from subnets.sn13.storage import SQLiteStorage


BASE_TIME = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)


def _submission(
    *,
    uri: str,
    source: DataSource = DataSource.X,
    label: str = "#macrocosmos",
    created_at: datetime = BASE_TIME,
    operator_id: str = "operator_1",
) -> OperatorSubmission:
    if source == DataSource.REDDIT:
        content = {
            "id": uri.rstrip("/").rsplit("/", 1)[-1],
            "username": "reddit_user",
            "body": "subnet 13 storage test",
            "title": "storage",
            "url": uri,
            "createdAt": created_at.isoformat(),
        }
        query_type = "subreddit_search"
    else:
        content = {
            "tweet_id": uri.rstrip("/").rsplit("/", 1)[-1],
            "username": "macro",
            "text": "subnet 13 storage test",
            "url": uri,
            "timestamp": created_at.isoformat(),
        }
        query_type = "label_search"

    return OperatorSubmission(
        operator_id=operator_id,
        source=source,
        label=label,
        uri=uri,
        source_created_at=created_at,
        scraped_at=created_at + timedelta(minutes=1),
        content=content,
        provenance=SubmissionProvenance(
            scraper_id="test.scraper",
            query_type=query_type,
            query_value=label,
        ),
    )


def test_list_entities_filters_by_source_label_bucket_and_limit(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(
        _submission(uri="https://x.com/macro/status/1", label="#Macrocosmos")
    )
    storage.store_submission(
        _submission(uri="https://x.com/macro/status/2", label="#macrocosmos")
    )
    storage.store_submission(
        _submission(
            uri="https://www.reddit.com/r/Bittensor/comments/abc1234/example",
            source=DataSource.REDDIT,
            label="Bittensor",
        )
    )

    bucket = time_bucket_from_datetime(BASE_TIME)
    entities = storage.list_entities(
        source=DataSource.X,
        label="#MACROCOSMOS",
        start_time_bucket=bucket,
        end_time_bucket=bucket,
        limit=1,
    )

    assert len(entities) == 1
    assert entities[0].source == DataSource.X
    assert entities[0].label == "#macrocosmos"


def test_list_entities_orders_by_datetime_then_uri(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    later = BASE_TIME + timedelta(hours=1)
    storage.store_submission(_submission(uri="https://x.com/macro/status/3", created_at=later))
    storage.store_submission(_submission(uri="https://x.com/macro/status/1", created_at=BASE_TIME))
    storage.store_submission(_submission(uri="https://x.com/macro/status/2", created_at=BASE_TIME))

    entities = storage.list_entities(source=DataSource.X)

    assert [entity.uri for entity in entities] == [
        "https://x.com/macro/status/1",
        "https://x.com/macro/status/2",
        "https://x.com/macro/status/3",
    ]


def test_rejected_submission_does_not_enter_list_entities_or_index(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    rejected = _submission(uri="https://x.com/macro/status/rejected")

    storage.record_rejection(rejected, ["missing_source_field:url"])

    assert storage.list_entities() == []
    assert storage.get_index("miner").total_data_items == 0
    stats = storage.get_operator_quality_stats("operator_1")
    assert stats["rejected"] == 1
