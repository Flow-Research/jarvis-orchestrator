from pathlib import Path

from subnets.sn13.models import DataSource
from subnets.sn13.readiness import (
    DEFAULT_MINIMUM_REQUIREMENTS_PATH,
    ReadinessStatus,
    SN13Capability,
    SN13MinimumRequirements,
    SN13RuntimeState,
    evaluate_sn13_readiness,
    load_minimum_requirements,
)


def _ready_runtime(**overrides) -> SN13RuntimeState:
    values = {
        "python_version": "3.12",
        "wallet_name": "sn13miner",
        "wallet_hotkey": "default",
        "hotkey_registered": True,
        "listener_running": True,
        "local_db_healthy": True,
        "disk_free_gb": 64,
        "wallet_hotkey_can_sign": True,
        "parquet_export_available": True,
        "operator_cost_budget_available": True,
        "operator_quality_score": 0.92,
        "operator_daily_capacity_items": 500,
    }
    values.update(overrides)
    return SN13RuntimeState(**values)


def _check(report, name: str):
    return next(check for check in report.checks if check.name == name)


def test_loads_default_minimum_requirements_profile():
    assert Path(DEFAULT_MINIMUM_REQUIREMENTS_PATH).exists()

    requirements = load_minimum_requirements()

    assert requirements.python_min_version == "3.10"
    assert requirements.disk_free_gb_blocker == 10
    assert requirements.disk_free_gb_recommended == 50
    assert requirements.s3_auth_url_default == "https://data-universe-api.api.macrocosmos.ai"


def test_registered_online_miner_can_serve_validators():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert report.can(SN13Capability.INTAKE_OPERATOR_UPLOADS) is True
    assert report.can(SN13Capability.PUBLISH_X_OPERATOR_TASKS) is True
    assert report.can(SN13Capability.PUBLISH_REDDIT_OPERATOR_TASKS) is True
    assert report.can(SN13Capability.EXPORT_UPSTREAM_S3) is True
    assert not report.blockers


def test_unregistered_hotkey_blocks_validator_serving():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(hotkey_registered=False),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "hotkey_registered_on_subnet").status == ReadinessStatus.BLOCKED


def test_offline_listener_blocks_validator_serving():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(listener_running=False),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "listener_running_online").status == ReadinessStatus.BLOCKED


def test_disk_below_jarvis_blocker_floor_blocks_work():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(disk_free_gb=4),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "disk_above_blocker_floor").status == ReadinessStatus.BLOCKED


def test_disk_below_recommended_floor_warns_without_blocking():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(disk_free_gb=25),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert _check(report, "disk_below_recommended_floor").status == ReadinessStatus.WARN


def test_x_tasks_require_apify_or_jarvis_operator_endpoint():
    report = evaluate_sn13_readiness(runtime=_ready_runtime(), env={})

    assert report.can(SN13Capability.PUBLISH_X_OPERATOR_TASKS) is False
    assert _check(report, "x_source_access_configured").status == ReadinessStatus.BLOCKED


def test_x_tasks_can_use_jarvis_external_operator_endpoint():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(),
        env={"JARVIS_SN13_X_OPERATOR_ENDPOINT": "https://operators.internal/x"},
    )

    assert report.can(SN13Capability.PUBLISH_X_OPERATOR_TASKS) is True
    x_access = next(source for source in report.source_access if source.source == DataSource.X)
    assert x_access.path == "JARVIS_SN13_X_OPERATOR_ENDPOINT"


def test_reddit_tasks_can_use_free_reddit_oauth_path():
    env = {
        "REDDIT_CLIENT_ID": "client",
        "REDDIT_CLIENT_SECRET": "secret",
        "REDDIT_USERNAME": "user",
        "REDDIT_PASSWORD": "password",
    }

    report = evaluate_sn13_readiness(runtime=_ready_runtime(), env=env)

    assert report.can(SN13Capability.PUBLISH_REDDIT_OPERATOR_TASKS) is True
    reddit_access = next(
        source for source in report.source_access if source.source == DataSource.REDDIT
    )
    assert reddit_access.path == "reddit_oauth_env_group"


def test_operator_budget_blocks_source_task_assignment():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(operator_cost_budget_available=False),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert report.can(SN13Capability.PUBLISH_X_OPERATOR_TASKS) is False
    assert report.can(SN13Capability.PUBLISH_REDDIT_OPERATOR_TASKS) is False
    assert _check(report, "operator_cost_budget_available").status == ReadinessStatus.BLOCKED


def test_operator_quality_and_capacity_block_source_task_assignment():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(operator_quality_score=0.4, operator_daily_capacity_items=25),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert report.can(SN13Capability.PUBLISH_X_OPERATOR_TASKS) is False
    assert report.can(SN13Capability.PUBLISH_REDDIT_OPERATOR_TASKS) is False
    assert _check(report, "operator_quality_floor").status == ReadinessStatus.BLOCKED
    assert _check(report, "operator_daily_capacity_floor").status == ReadinessStatus.BLOCKED


def test_s3_export_requires_hotkey_signing_and_parquet_export():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(wallet_hotkey_can_sign=False, parquet_export_available=False),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert report.can(SN13Capability.EXPORT_UPSTREAM_S3) is False
    assert _check(report, "wallet_hotkey_can_sign").status == ReadinessStatus.BLOCKED
    assert _check(report, "parquet_export_available").status == ReadinessStatus.BLOCKED


def test_jarvis_archive_requires_archive_bucket_configuration():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(jarvis_archive_bucket_configured=False),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.EXPORT_UPSTREAM_S3) is True
    assert report.can(SN13Capability.ARCHIVE_JARVIS_S3) is False
    assert _check(report, "jarvis_archive_bucket_configured").status == ReadinessStatus.WARN

    configured = evaluate_sn13_readiness(
        runtime=_ready_runtime(jarvis_archive_bucket_configured=True),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert configured.can(SN13Capability.ARCHIVE_JARVIS_S3) is True


def test_unhealthy_local_db_blocks_validator_serving_and_operator_intake():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(local_db_healthy=False),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert report.can(SN13Capability.INTAKE_OPERATOR_UPLOADS) is False
    assert _check(report, "local_db_healthy").status == ReadinessStatus.BLOCKED


def test_python_below_upstream_minimum_blocks():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(python_version="3.9"),
        env={"APIFY_API_TOKEN": "token"},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "python_at_or_above_minimum").status == ReadinessStatus.BLOCKED


def test_custom_requirement_profile_changes_economic_floor():
    requirements = SN13MinimumRequirements(disk_free_gb_blocker=100, disk_free_gb_recommended=250)

    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(disk_free_gb=64),
        env={"APIFY_API_TOKEN": "token"},
        requirements=requirements,
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "disk_above_blocker_floor").status == ReadinessStatus.BLOCKED
