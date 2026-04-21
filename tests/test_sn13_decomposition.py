"""Tests for SN13 validator task decomposition."""

from subnets.sn13.listener.sn13_decomposition import (
    BucketRequest,
    aggregate_operator_results,
    decompose_bucket_request,
    normalize_bucket_request,
)


def test_normalize_bucket_request_uses_expected_count_fields():
    bucket = normalize_bucket_request(
        {
            "source": "reddit",
            "time_bucket_id": 1845,
            "label": "bittensor",
            "estimated_count": 1250,
        }
    )

    assert bucket.source == "REDDIT"
    assert bucket.time_bucket_id == 1845
    assert bucket.label == "bittensor"
    assert bucket.expected_count == 1250


def test_decompose_bucket_request_keeps_small_bucket_on_single_operator():
    plan = decompose_bucket_request(
        BucketRequest(source="X", time_bucket_id=1845, label="$BTC", expected_count=320),
        operator_pool=["x_operator_1", "x_operator_2"],
    )

    assert plan.strategy == "single_operator"
    assert len(plan.tasks) == 1
    assert plan.tasks[0].operator_name == "x_operator_1"
    assert plan.tasks[0].limit == 320


def test_decompose_bucket_request_splits_large_bucket_across_operator_pool():
    plan = decompose_bucket_request(
        BucketRequest(source="X", time_bucket_id=1845, label="$BTC", expected_count=1200),
        operator_pool=["x_operator_1", "x_operator_2", "x_operator_3"],
    )

    assert plan.strategy == "chunk_by_offset"
    assert len(plan.tasks) == 3
    assert [task.offset for task in plan.tasks] == [0, 500, 1000]
    assert [task.limit for task in plan.tasks] == [500, 500, 200]
    assert [task.operator_name for task in plan.tasks] == [
        "x_operator_1",
        "x_operator_2",
        "x_operator_3",
    ]


def test_aggregate_operator_results_deduplicates_repeated_content():
    results = aggregate_operator_results(
        [
            [
                {
                    "source": "X",
                    "label": "$BTC",
                    "created_at": "2026-04-10T12:00:00Z",
                    "content": "same",
                }
            ],
            [
                {
                    "source": "X",
                    "label": "$BTC",
                    "created_at": "2026-04-10T12:00:00Z",
                    "content": "same",
                },
                {
                    "source": "X",
                    "label": "$BTC",
                    "created_at": "2026-04-10T12:00:01Z",
                    "content": "different",
                },
            ],
        ]
    )

    assert len(results) == 2
