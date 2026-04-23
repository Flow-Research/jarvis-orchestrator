from datetime import datetime, timedelta, timezone

from subnets.sn13.api_adapter import SN13OperatorIntakeAdapter, SN13OperatorStatsAdapter
from subnets.sn13.storage import SQLiteStorage
from subnets.sn13.tasks import SN13OperatorRuntime
from workstream.models import OperatorSubmissionEnvelope, WorkstreamTask, WorkstreamTaskStatus
from workstream.store import InMemoryWorkstream


def _open_task() -> WorkstreamTask:
    start = datetime(2026, 4, 22, 10, tzinfo=timezone.utc)
    return WorkstreamTask(
        task_id="task_1",
        route_key="sn13",
        source="X",
        status=WorkstreamTaskStatus.OPEN,
        acceptance_cap=2,
        contract={
            "task_id": "task_1",
            "demand_id": "demand_1",
            "source": "X",
            "label": "#bittensor",
            "acceptance": {
                "source_created_at_gte": start.isoformat(),
                "source_created_at_lt": (start + timedelta(hours=1)).isoformat(),
            },
            "delivery_limits": {
                "max_records": 2,
                "max_content_bytes_per_record": 1_000_000,
                "max_total_content_bytes": 2_000_000,
            },
            "source_requirements": {
                "provenance_query_type": "x_label_or_keyword_scrape",
            },
        },
    )


def _open_reddit_task() -> WorkstreamTask:
    start = datetime(2026, 4, 22, 10, tzinfo=timezone.utc)
    return WorkstreamTask(
        task_id="task_reddit_1",
        route_key="sn13",
        source="REDDIT",
        status=WorkstreamTaskStatus.OPEN,
        acceptance_cap=2,
        contract={
            "task_id": "task_reddit_1",
            "demand_id": "demand_reddit_1",
            "source": "REDDIT",
            "label": "r/bittensor_",
            "acceptance": {
                "source_created_at_gte": start.isoformat(),
                "source_created_at_lt": (start + timedelta(hours=1)).isoformat(),
            },
            "delivery_limits": {
                "max_records": 2,
                "max_content_bytes_per_record": 1_000_000,
                "max_total_content_bytes": 2_000_000,
            },
            "source_requirements": {
                "provenance_query_type": "reddit_label_or_keyword_scrape",
            },
        },
    )


def _envelope(*, uri: str = "https://x.com/example/status/1") -> OperatorSubmissionEnvelope:
    return OperatorSubmissionEnvelope(
        task_id="task_1",
        operator_id="operator_1",
        route_key="sn13",
        submitted_at=datetime(2026, 4, 22, 10, 5, tzinfo=timezone.utc),
        records=[
            {
                "uri": uri,
                "source_created_at": "2026-04-22T10:02:00+00:00",
                "content": {
                    "tweet_id": "1",
                    "username": "alice",
                    "text": "Bittensor subnet data #bittensor",
                    "url": uri,
                    "timestamp": "2026-04-22T10:02:00+00:00",
                },
            }
        ],
    )


def _reddit_envelope(
    *,
    task_id: str = "task_reddit_1",
    uri: str = "https://www.reddit.com/r/bittensor_/comments/abc123/demo",
    subreddit: str = "bittensor_",
) -> OperatorSubmissionEnvelope:
    return OperatorSubmissionEnvelope(
        task_id=task_id,
        operator_id="operator_1",
        route_key="sn13",
        submitted_at=datetime(2026, 4, 22, 10, 5, tzinfo=timezone.utc),
        records=[
            {
                "uri": uri,
                "source_created_at": "2026-04-22T10:02:00+00:00",
                "content": {
                    "id": "abc123",
                    "username": "alice",
                    "title": "Bittensor subnet data",
                    "body": "Fresh scrape for r/bittensor_",
                    "url": uri,
                    "createdAt": "2026-04-22T10:02:00+00:00",
                    "subreddit": subreddit,
                },
            }
        ],
    )


def _adapter(tmp_path) -> tuple[SN13OperatorIntakeAdapter, SQLiteStorage, InMemoryWorkstream]:
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    runtime = SN13OperatorRuntime(storage=storage)
    workstream = InMemoryWorkstream()
    workstream.publish(_open_task())
    return SN13OperatorIntakeAdapter(runtime=runtime, workstream=workstream), storage, workstream


def test_sn13_workstream_api_adapter_ingests_accepted_records(tmp_path):
    adapter, storage, _workstream = _adapter(tmp_path)

    receipt = adapter.submit(_envelope())
    stats = SN13OperatorStatsAdapter(storage=storage).get_operator_stats("operator_1")

    assert receipt.status == "accepted"
    assert receipt.accepted_count == 1
    assert receipt.rejected_count == 0
    assert stats.accepted_scorable == 1
    assert storage.uri_exists("https://x.com/example/status/1") is True


def test_sn13_workstream_api_adapter_rejects_completed_task(tmp_path):
    adapter, _storage, workstream = _adapter(tmp_path)
    workstream.publish(
        _open_task().model_copy(
            update={
                "status": WorkstreamTaskStatus.COMPLETED,
                "accepted_count": 2,
            }
        )
    )

    receipt = adapter.submit(_envelope())

    assert receipt.status == "rejected"
    assert receipt.accepted_count == 0
    assert receipt.rejected_count == 1
    assert receipt.reasons == ["task_acceptance_cap_reached"]


def test_sn13_workstream_api_adapter_rejects_duplicate_records(tmp_path):
    adapter, storage, _workstream = _adapter(tmp_path)

    first = adapter.submit(_envelope())
    second = adapter.submit(_envelope())
    stats = storage.get_operator_quality_stats("operator_1")

    assert first.accepted_count == 1
    assert second.status == "rejected"
    assert second.duplicate_count == 1
    assert second.rejected_count == 1
    assert "duplicate_entity" in second.reasons
    assert stats["accepted_scorable"] == 1
    assert stats["duplicate"] == 1
    assert stats["rejected"] == 1


def test_sn13_workstream_api_adapter_closes_task_at_acceptance_cap(tmp_path):
    adapter, _storage, workstream = _adapter(tmp_path)

    first = adapter.submit(_envelope(uri="https://x.com/example/status/1"))
    second = adapter.submit(_envelope(uri="https://x.com/example/status/2"))
    task = workstream.get("task_1")

    assert first.accepted_count == 1
    assert second.accepted_count == 1
    assert task is not None
    assert task.status == WorkstreamTaskStatus.COMPLETED
    assert task.accepted_count == 2


def test_sn13_workstream_api_adapter_rejects_x_records_that_miss_task_label(tmp_path):
    adapter, storage, _workstream = _adapter(tmp_path)

    receipt = adapter.submit(
        OperatorSubmissionEnvelope(
            task_id="task_1",
            operator_id="operator_1",
            route_key="sn13",
            submitted_at=datetime(2026, 4, 22, 10, 5, tzinfo=timezone.utc),
            records=[
                {
                    "uri": "https://x.com/example/status/99",
                    "source_created_at": "2026-04-22T10:02:00+00:00",
                    "content": {
                        "tweet_id": "99",
                        "username": "alice",
                        "text": "Talking about crypto without the requested hashtag",
                        "url": "https://x.com/example/status/99",
                        "timestamp": "2026-04-22T10:02:00+00:00",
                    },
                }
            ],
        )
    )

    stats = storage.get_operator_quality_stats("operator_1")

    assert receipt.status == "rejected"
    assert receipt.accepted_count == 0
    assert receipt.rejected_count == 1
    assert "acceptance:label_mismatch" in receipt.reasons
    assert stats["accepted_scorable"] == 0
    assert stats["rejected"] == 1


def test_sn13_workstream_api_adapter_rejects_reddit_records_for_wrong_subreddit(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    runtime = SN13OperatorRuntime(storage=storage)
    workstream = InMemoryWorkstream()
    workstream.publish(_open_reddit_task())
    adapter = SN13OperatorIntakeAdapter(runtime=runtime, workstream=workstream)

    receipt = adapter.submit(
        _reddit_envelope(
            uri="https://www.reddit.com/r/ethereum/comments/abc123/demo",
            subreddit="ethereum",
        )
    )

    stats = storage.get_operator_quality_stats("operator_1")

    assert receipt.status == "rejected"
    assert receipt.accepted_count == 0
    assert receipt.rejected_count == 1
    assert "acceptance:label_mismatch" in receipt.reasons
    assert stats["accepted_scorable"] == 0
    assert stats["rejected"] == 1
