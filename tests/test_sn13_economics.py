import pytest
from pydantic import ValidationError

from subnets.sn13.economics import (
    CostBreakdown,
    PayoutBasis,
    S3ArchiveCostInput,
    S3StorageMode,
    TaskEconomicsInput,
    calculate_payable_records,
    calculate_s3_archive_cost,
    evaluate_task_economics,
)
from subnets.sn13.models import DataSource


def _valid_task(**overrides) -> TaskEconomicsInput:
    values = {
        "source": DataSource.X,
        "label": "#bittensor",
        "desirability_job_id": "gravity_x_bittensor",
        "desirability_weight": 2.0,
        "quantity_target": 1000,
        "max_task_cost": 20.0,
        "expected_reward_value": 30.0,
        "expected_submitted_records": 1200,
        "expected_accepted_scorable_records": 900,
        "expected_duplicate_rate": 0.04,
        "expected_rejection_rate": 0.10,
        "validation_pass_probability": 0.95,
        "payout_basis": PayoutBasis.ACCEPTED_SCORABLE_RECORD,
        "costs": CostBreakdown(
            operator_payout=7.0,
            scraper_provider_cost=4.0,
            proxy_cost=1.0,
            compute_cost=0.5,
            local_storage_cost=0.1,
            export_staging_cost=0.1,
            upload_bandwidth_cost=0.1,
            retry_cost=0.2,
            risk_reserve=2.0,
        ),
    }
    values.update(overrides)
    return TaskEconomicsInput(**values)


def test_complete_positive_margin_task_can_be_taken():
    decision = evaluate_task_economics(_valid_task())

    assert decision.can_take_task is True
    assert decision.blockers == ()
    assert decision.total_task_cost == 15.0
    assert decision.accepted_scorable_unit_cost == pytest.approx(0.01666667)
    assert decision.quality_adjusted_unit_cost == pytest.approx(0.01754386)
    assert decision.expected_margin == 15.0
    assert decision.s3_storage_cost_owner == "upstream_destination_not_jarvis_bucket"


def test_missing_inputs_block_real_assignment():
    decision = evaluate_task_economics(
        TaskEconomicsInput(source=DataSource.REDDIT, label="r/bittensor")
    )

    assert decision.can_take_task is False
    assert "missing_desirability_job_id" in decision.blockers
    assert "missing_max_task_cost" in decision.blockers
    assert "missing_payout_basis" in decision.blockers


def test_cost_above_cap_and_negative_margin_block_assignment():
    decision = evaluate_task_economics(
        _valid_task(
            max_task_cost=10.0,
            expected_reward_value=12.0,
            costs=CostBreakdown(operator_payout=9.0, scraper_provider_cost=6.0),
        )
    )

    assert decision.can_take_task is False
    assert "total_task_cost_exceeds_max_task_cost" in decision.blockers
    assert "expected_margin_negative" in decision.blockers


def test_duplicate_rate_above_upstream_threshold_blocks_assignment():
    decision = evaluate_task_economics(_valid_task(expected_duplicate_rate=0.11))

    assert decision.can_take_task is False
    assert "expected_duplicate_rate_exceeds_sn13_threshold" in decision.blockers


def test_low_validation_probability_blocks_assignment():
    decision = evaluate_task_economics(_valid_task(validation_pass_probability=0.60))

    assert decision.can_take_task is False
    assert "validation_pass_probability_below_floor" in decision.blockers


def test_jarvis_archive_bucket_is_explicit_cost_owner():
    decision = evaluate_task_economics(
        _valid_task(
            s3_storage_mode=S3StorageMode.JARVIS_ARCHIVE,
            costs=CostBreakdown(operator_payout=7.0, jarvis_archive_bucket_cost=3.0),
        )
    )

    assert decision.can_take_task is True
    assert decision.total_task_cost == 10.0
    assert decision.s3_storage_cost_owner == "jarvis_owned_archive_bucket"


def test_dual_upload_tracks_upstream_and_jarvis_archive_cost_owner():
    decision = evaluate_task_economics(
        _valid_task(
            s3_storage_mode=S3StorageMode.UPSTREAM_AND_JARVIS_ARCHIVE,
            costs=CostBreakdown(
                operator_payout=7.0,
                upload_bandwidth_cost=1.0,
                jarvis_archive_bucket_cost=2.0,
            ),
        )
    )

    assert decision.can_take_task is True
    assert decision.total_task_cost == 10.0
    assert (
        decision.s3_storage_cost_owner
        == "upstream_presigned_destination_plus_jarvis_owned_archive_bucket"
    )


def test_payable_records_exclude_duplicates_rejections_and_failed_validation():
    assert (
        calculate_payable_records(
            accepted_scorable_records=100,
            duplicate_records=10,
            rejected_records=5,
        )
        == 85
    )
    assert calculate_payable_records(accepted_scorable_records=100, validation_failed=True) == 0
    assert (
        calculate_payable_records(
            accepted_scorable_records=10,
            duplicate_records=20,
            rejected_records=5,
        )
        == 0
    )


def test_label_or_keyword_is_required():
    with pytest.raises(ValidationError, match="label or keyword is required"):
        TaskEconomicsInput(source=DataSource.X)


def test_s3_archive_cost_uses_explicit_unit_prices():
    estimate = calculate_s3_archive_cost(
        S3ArchiveCostInput(
            storage_gb_month=100,
            storage_usd_per_gb_month=0.023,
            put_requests=10_000,
            put_usd_per_1000=0.005,
            get_requests=20_000,
            get_usd_per_1000=0.0004,
            retrieval_gb=5,
            retrieval_usd_per_gb=0.01,
            transfer_out_gb=7,
            transfer_out_usd_per_gb=0.09,
            lifecycle_transition_requests=1_000,
            lifecycle_transition_usd_per_1000=0.01,
            monitoring_object_count=50_000,
            monitoring_usd_per_1000_objects=0.0025,
        )
    )

    assert estimate.storage_cost == 2.3
    assert estimate.put_request_cost == 0.05
    assert estimate.get_request_cost == 0.008
    assert estimate.retrieval_cost == 0.05
    assert estimate.transfer_out_cost == 0.63
    assert estimate.lifecycle_transition_cost == 0.01
    assert estimate.monitoring_cost == 0.125
    assert estimate.total == 3.173
