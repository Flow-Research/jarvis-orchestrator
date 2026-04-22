from pathlib import Path

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
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert report.can(SN13Capability.INTAKE_OPERATOR_UPLOADS) is True
    assert report.can(SN13Capability.EXPORT_UPSTREAM_S3) is True
    assert not report.blockers


def test_unregistered_hotkey_blocks_validator_serving():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(hotkey_registered=False),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "hotkey_registered_on_subnet").status == ReadinessStatus.BLOCKED


def test_offline_listener_blocks_validator_serving():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(listener_running=False),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "listener_running_online").status == ReadinessStatus.BLOCKED


def test_disk_below_jarvis_blocker_floor_blocks_work():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(disk_free_gb=4),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "disk_above_blocker_floor").status == ReadinessStatus.BLOCKED


def test_disk_below_recommended_floor_warns_without_blocking():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(disk_free_gb=25),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert _check(report, "disk_below_recommended_floor").status == ReadinessStatus.WARN


def test_s3_export_requires_hotkey_signing_and_parquet_export():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(wallet_hotkey_can_sign=False, parquet_export_available=False),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert report.can(SN13Capability.EXPORT_UPSTREAM_S3) is False
    assert _check(report, "wallet_hotkey_can_sign").status == ReadinessStatus.BLOCKED
    assert _check(report, "parquet_export_available").status == ReadinessStatus.BLOCKED


def test_jarvis_archive_requires_archive_bucket_configuration():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(jarvis_archive_bucket_configured=False),
        env={},
    )

    assert report.can(SN13Capability.EXPORT_UPSTREAM_S3) is True
    assert report.can(SN13Capability.ARCHIVE_JARVIS_S3) is False
    assert _check(report, "jarvis_archive_bucket_configured").status == ReadinessStatus.WARN

    configured = evaluate_sn13_readiness(
        runtime=_ready_runtime(jarvis_archive_bucket_configured=True),
        env={},
    )

    assert configured.can(SN13Capability.ARCHIVE_JARVIS_S3) is True


def test_unhealthy_local_db_blocks_validator_serving_and_operator_intake():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(local_db_healthy=False),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert report.can(SN13Capability.INTAKE_OPERATOR_UPLOADS) is False
    assert _check(report, "local_db_healthy").status == ReadinessStatus.BLOCKED


def test_python_below_upstream_minimum_blocks():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(python_version="3.9"),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "python_at_or_above_minimum").status == ReadinessStatus.BLOCKED


def test_custom_requirement_profile_changes_economic_floor():
    requirements = SN13MinimumRequirements(disk_free_gb_blocker=100, disk_free_gb_recommended=250)

    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(disk_free_gb=64),
        env={},
        requirements=requirements,
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is False
    assert _check(report, "disk_above_blocker_floor").status == ReadinessStatus.BLOCKED


def test_missing_listener_captures_warn_without_blocking_runtime_capability():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(listener_capture_count=0, listener_query_types=()),
        env={},
    )

    assert report.can(SN13Capability.SERVE_VALIDATORS) is True
    assert _check(report, "listener_capture_evidence_present").status == ReadinessStatus.WARN
    assert _check(report, "listener_query_surface_observed").status == ReadinessStatus.WARN


def test_listener_capture_query_surface_passes_when_all_queries_are_observed():
    report = evaluate_sn13_readiness(
        runtime=_ready_runtime(
            listener_capture_count=12,
            listener_query_types=(
                "GetContentsByBuckets",
                "GetDataEntityBucket",
                "GetMinerIndex",
            ),
        ),
        env={},
    )

    assert _check(report, "listener_capture_evidence_present").status == ReadinessStatus.PASS
    assert _check(report, "listener_query_surface_observed").status == ReadinessStatus.PASS
