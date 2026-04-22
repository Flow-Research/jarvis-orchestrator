from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_engineering_gates_cover_required_disciplines():
    text = (ROOT / "docs" / "ENGINEERING_GATES.md").read_text().casefold()

    for required in [
        "testing gate",
        "economics gate",
        "architecture gate",
        "no new feature",
        "rollback path",
        "archive",
    ]:
        assert required in text


def test_sn13_economics_covers_s3_and_operator_unit_economics():
    text = (ROOT / "subnets" / "sn13" / "docs" / "ECONOMICS.md").read_text().casefold()

    for required in [
        "direct answers",
        "presigned",
        "who owns/pays",
        "revenue timing",
        "cli cost commands",
        "unit economics",
        "operator payout",
        "cannot-take-task",
        "s3 cost modeling",
        "validation failure",
        "jarvis archive",
        "local retention policy",
        "production blocker ledger",
    ]:
        assert required in text


def test_obsolete_sn13_prototypes_and_vendored_docs_are_removed():
    obsolete_paths = [
        "docs/bittensor-basics",
        "tests/sn13",
        "tests/test_sn13_decomposition.py",
        "subnets/sn13/decomposition.py",
        "subnets/sn13/monitor.py",
        "subnets/sn13/listener/sn13_decomposition.py",
        "subnets/sn13/listener/sn13_miner_listener.py",
        "tests/helpers.py",
        "tests/test_mock.py",
    ]

    for relative_path in obsolete_paths:
        assert not (ROOT / relative_path).exists(), relative_path


def test_sn13_listener_runtime_entrypoint_exists():
    for relative_path in [
        "subnets/sn13/listener/listener.py",
        "subnets/sn13/listener/runtime.py",
        "subnets/sn13/listener/protocol.py",
    ]:
        assert (ROOT / relative_path).exists(), relative_path


def test_sn13_contract_uses_workstream_publish_and_intake_enforcement():
    text = (ROOT / "subnets" / "sn13" / "docs" / "OPERATOR_CONTRACT.md").read_text().casefold()

    for required in [
        "jarvis publishes `operatortaskcontract` payloads to the workstream",
        "operators do not infer desired topics from validator traffic",
        "intake enforces the requirements",
        "no unlimited upload path",
    ]:
        assert required in text


def test_workstream_architecture_is_subnet_agnostic():
    text = (ROOT / "docs" / "WORKSTREAM_ARCHITECTURE.md").read_text().casefold()

    for required in [
        "one workstream http api",
        "one workstream interface",
        "many subnet adapters",
        "there is no sn13-specific public api route",
        "subnet-specific contracts travel inside generic workstream tasks",
        "sqliteworkstream",
        "sn13 plan publish",
    ]:
        assert required in text


def test_cli_docs_are_admin_only():
    text = (ROOT / "cli" / "README.md").read_text().casefold()

    for required in [
        "admin/control-plane entrypoint",
        "personal operators do not use this cli",
        "personal operators use the workstream http api",
    ]:
        assert required in text


def test_mainnet_readiness_doc_covers_costs_deployment_and_operator_split():
    text = (ROOT / "docs" / "JARVIS_MAINNET_READINESS.md").read_text().casefold()

    for required in [
        "live cost snapshot",
        "jarvis-owned requirements",
        "personal operator requirements",
        "why jarvis maintains its own archive s3",
        "dockerfile",
        "compose.yaml",
        "registration-monitor",
        "workstream-api",
        "sn13-scheduler",
        "mainnet blockers still open",
    ]:
        assert required in text


def test_mainnet_deployment_files_exist_and_match_current_services():
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "compose.yaml").exists()
    assert (ROOT / "deploy" / "jarvis.mainnet.env").exists()
    assert (ROOT / "deploy" / "monitor.mainnet.yaml").exists()
    assert (ROOT / "scripts" / "run_sn13_scheduler.sh").exists()

    compose_text = (ROOT / "compose.yaml").read_text().casefold()
    for required in [
        "registration-monitor",
        "workstream-api",
        "sn13-scheduler",
        "jarvis-admin",
    ]:
        assert required in compose_text
