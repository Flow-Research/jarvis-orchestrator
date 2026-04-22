"""Tests for the grouped CLI surface."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import cli.main as cli_main
from cli import cli  # noqa: E402
from workstream.sqlite_store import SQLiteWorkstream

# ── Helpers ──────────────────────────────────────────────────────────────


def _write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return path


def _publication_economics_args() -> list[str]:
    return [
        "--max-task-cost",
        "20",
        "--expected-reward",
        "30",
        "--expected-submitted",
        "1200",
        "--expected-accepted",
        "900",
        "--duplicate-rate",
        "0.04",
        "--rejection-rate",
        "0.10",
        "--validation-pass-probability",
        "0.95",
        "--payout-basis",
        "accepted_scorable_record",
        "--operator-payout",
        "7",
        "--scraper-provider-cost",
        "4",
        "--proxy-cost",
        "1",
        "--compute-cost",
        "0.5",
        "--risk-reserve",
        "2",
    ]


VALID_CONFIG = """
global:
  subtensor_network: test
  data_dir: {data_dir}
subnets:
  - netuid: 13
    nickname: "Test Subnet"
    price_threshold_tao: 0.5
    poll_interval_seconds: 300
    adaptive_polling: true
    floor_detection: true
    signal_file: "{data_dir}/signals/sn13.json"
    enabled: true
    alerts:
      channel: discord
      discord:
        webhook_url: "https://discord.com/api/webhooks/test/test"
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    content = VALID_CONFIG.format(data_dir=data_dir)
    return _write_config(tmp_path, content)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class _FakeProcess:
    def __init__(self, pid: int = 4242):
        self.pid = pid


class _FakeWallet:
    def __init__(self, name: str):
        self.name = name
        self.coldkeypub = type("Cold", (), {"ss58_address": f"{name}_cold"})()
        self.hotkeypub = type("Hot", (), {"ss58_address": f"{name}_hot"})()
        self.created_hotkey_name = None

    def create_new_coldkey(self, **kwargs):
        self.created_coldkey = kwargs

    def create_new_hotkey(self, **kwargs):
        self.created_hotkey_name = kwargs.get("hotkey_name", "default")


class _FakeMetagraph:
    def __init__(self, hotkeys=None, stakes=None, n=256, emission=0.15):
        self.hotkeys = hotkeys or []
        self.stake = stakes or []
        self.n = n
        self.emission = emission


class _FakeSubtensor:
    def __init__(self, network: str):
        self.network = network
        self.register_calls = []

    def get_balance(self, address: str):
        return 12.5

    def metagraph(self, netuid: int):
        if netuid == 13:
            return _FakeMetagraph(
                hotkeys=["sn13miner_hot", "jarvis_hot"],
                stakes=[3.0, 1.0],
                n=256,
                emission=0.17,
            )
        return _FakeMetagraph(hotkeys=[], stakes=[], n=256, emission=0.0)

    def register(self, wallet, netuid: int):
        self.register_calls.append((wallet.name, netuid))
        return True

    def get_subnet_burn_cost(self):
        return 7.25

    def run_faucet(self, wallet):
        return None


class _FakeBT:
    def __init__(self):
        self.wallets = []
        self.subtensors = []

    def Wallet(self, name: str):  # noqa: N802
        wallet = _FakeWallet(name)
        self.wallets.append(wallet)
        return wallet

    def Subtensor(self, network: str):  # noqa: N802
        subtensor = _FakeSubtensor(network)
        self.subtensors.append(subtensor)
        return subtensor


# ── Version ──────────────────────────────────────────────────────────────


class TestVersion:
    def test_version_flag(self, runner: CliRunner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output


# ── Help ─────────────────────────────────────────────────────────────────


class TestHelp:
    def test_root_without_command_shows_help(self, runner: CliRunner):
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "Jarvis-Miner" in result.output
        assert "O R C H E S T R A T O R" in result.output

    def test_main_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "wallet" in result.output
        assert "miner" in result.output
        assert "network" in result.output

    def test_miner_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["miner", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "status" in result.output

    def test_network_price_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["network", "price", "--help"])
        assert result.exit_code == 0

    def test_monitor_help_and_legacy_aliases_are_visible(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "monitor" in result.output
        assert "workstream" in result.output
        assert "watch" in result.output
        assert "deregister-check" in result.output

        monitor_result = runner.invoke(cli, ["monitor", "--help"])
        assert monitor_result.exit_code == 0
        assert "price" in monitor_result.output
        assert "register" in monitor_result.output
        assert "deregister-check" in monitor_result.output

    def test_workstream_help_is_admin_facing(self, runner: CliRunner):
        result = runner.invoke(cli, ["workstream", "serve", "--help"])

        assert result.exit_code == 0
        assert "Serve the workstream HTTP boundary" in result.output
        assert "--host" in result.output
        assert "--port" in result.output

        root_help = runner.invoke(cli, ["workstream", "--help"])
        assert root_help.exit_code == 0
        assert "serve" in root_help.output
        assert "status" in root_help.output
        assert "tasks" in root_help.output

    def test_workstream_serve_fails_cleanly_without_auth_config(self, runner: CliRunner):
        result = runner.invoke(cli, ["workstream", "serve"])

        assert result.exit_code == 1
        assert "workstream api auth is required" in result.output.lower()
        assert "jarvis_workstream_operator_secrets_json" in result.output.lower()


# ── Validate command ─────────────────────────────────────────────────────


class TestValidate:
    def test_valid_config(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_invalid_config_path(self, runner: CliRunner):
        result = runner.invoke(cli, ["-c", "/nonexistent.yaml", "config", "validate"])
        assert result.exit_code == 1

    def test_validate_shows_subnet_count(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "config", "validate"])
        assert "1 subnet" in result.output.lower()


# ── Config show command ──────────────────────────────────────────────────


class TestConfigShow:
    def test_shows_global_settings(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "config", "show"])
        assert result.exit_code == 0
        assert "Global Settings" in result.output
        assert "test" in result.output  # network

    def test_shows_subnets(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "config", "show"])
        assert "Test Subnet" in result.output
        assert "0.5000" in result.output  # threshold


# ── Miner status command ────────────────────────────────────────────────


class TestMinerStatus:
    def test_status_without_state_file(self, runner: CliRunner):
        result = runner.invoke(cli, ["miner", "status", "--subnet", "999"])
        assert result.exit_code == 0
        assert "No state file" in result.output


class TestNetwork:
    def test_network_price_help_supports_subnet_context(self, runner: CliRunner):
        result = runner.invoke(cli, ["network", "price", "--help"])
        assert result.exit_code == 0
        assert "--subnet" in result.output


# ── Missing config ───────────────────────────────────────────────────────


class TestMissingConfig:
    def test_missing_config_file(self, runner: CliRunner):
        result = runner.invoke(cli, ["-c", "/does/not/exist.yaml", "config", "validate"])
        assert result.exit_code == 1
        assert "Config error" in result.output or "not found" in result.output


class TestWalletCommands:
    def test_wallet_create(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
        fake_bt = _FakeBT()
        monkeypatch.setattr(cli_main, "get_bittensor", lambda: fake_bt)
        monkeypatch.setattr(cli_main.Path, "home", lambda: Path("/tmp/nonexistent-home"))

        result = runner.invoke(cli, ["wallet", "create", "--name", "jarvis"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()
        assert fake_bt.wallets[0].name == "jarvis"

    def test_wallet_info_uses_configured_wallets(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake_bt = _FakeBT()
        monkeypatch.setattr(cli_main, "get_bittensor", lambda: fake_bt)

        home = tmp_path / "home"
        wallets_dir = home / ".bittensor" / "wallets"
        for wallet_name in ["sn13miner", "sn6miner", "randomwallet"]:
            (wallets_dir / wallet_name).mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(cli_main.Path, "home", lambda: home)

        result = runner.invoke(cli, ["wallet", "info"])
        assert result.exit_code == 0
        assert "sn13miner" in result.output
        assert "randomwallet" not in result.output

    def test_wallet_balances(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
        fake_bt = _FakeBT()
        monkeypatch.setattr(cli_main, "get_bittensor", lambda: fake_bt)

        result = runner.invoke(cli, ["wallet", "balances", "--wallet", "sn13miner"])
        assert result.exit_code == 0
        assert "sn13miner" in result.output
        assert "τ12.5000" in result.output


class TestMinerCommands:
    def test_miner_start_creates_state_and_uses_listener_capture_dir(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        subnet_dir = project_root / "subnets" / "sn13" / "listener"
        subnet_dir.mkdir(parents=True)
        (subnet_dir / "listener.py").write_text("print('listener')")
        (project_root / "miner_tools" / "config").mkdir(parents=True)

        process_calls = []

        def fake_popen(cmd, stdout=None, stderr=None, env=None, start_new_session=False):
            process_calls.append(
                {
                    "cmd": cmd,
                    "env": env,
                    "start_new_session": start_new_session,
                }
            )
            return _FakeProcess(pid=9999)

        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)

        result = runner.invoke(cli, ["miner", "start", "--subnet", "13", "--network", "testnet"])
        assert result.exit_code == 0
        assert "started" in result.output.lower()
        assert "--capture-dir" in process_calls[0]["cmd"]
        assert "-u" in process_calls[0]["cmd"]
        assert process_calls[0]["env"]["ARROW_USER_SIMD_LEVEL"] == "NONE"
        assert process_calls[0]["start_new_session"] is True

        state = json.loads((project_root / "subnets" / "sn13" / "state.json").read_text())
        assert state["pid"] == 9999
        assert state["wallet"] == "sn13miner"

    def test_miner_start_falls_back_to_miner_py_for_non_listener_subnet(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        subnet_dir = project_root / "subnets" / "sn6"
        subnet_dir.mkdir(parents=True)
        (subnet_dir / "miner.py").write_text("print('miner')")
        (project_root / "miner_tools" / "config").mkdir(parents=True)

        process_calls = []

        def fake_popen(cmd, stdout=None, stderr=None, env=None, start_new_session=False):
            process_calls.append(
                {
                    "cmd": cmd,
                    "env": env,
                    "start_new_session": start_new_session,
                }
            )
            return _FakeProcess(pid=555)

        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)

        result = runner.invoke(cli, ["miner", "start", "--subnet", "6"])
        assert result.exit_code == 0
        assert str(subnet_dir / "miner.py") in process_calls[0]["cmd"]
        assert "--capture-dir" not in process_calls[0]["cmd"]
        assert process_calls[0]["env"]["ARROW_USER_SIMD_LEVEL"] == "NONE"
        assert process_calls[0]["start_new_session"] is True

    def test_miner_stop_updates_state(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        subnet_dir = project_root / "subnets" / "sn13"
        subnet_dir.mkdir(parents=True)
        (subnet_dir / "state.json").write_text(json.dumps({"pid": 1234, "running": True}))

        killed = []
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cli_main.os, "kill", lambda pid, sig: killed.append((pid, sig)))

        result = runner.invoke(cli, ["miner", "stop", "--subnet", "13"])
        assert result.exit_code == 0
        assert killed[0][0] == 1234
        state = json.loads((subnet_dir / "state.json").read_text())
        assert state["running"] is False

    def test_miner_logs(self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        project_root = tmp_path / "repo"
        subnet_dir = project_root / "subnets" / "sn13"
        subnet_dir.mkdir(parents=True)
        (subnet_dir / "listener.log").write_text("one\ntwo\nthree\n")
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(cli, ["miner", "logs", "--subnet", "13", "--lines", "2"])
        assert result.exit_code == 0
        assert "two" in result.output
        assert "three" in result.output


class TestNetworkCommands:
    def test_network_register(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
        fake_bt = _FakeBT()
        monkeypatch.setattr(cli_main, "get_bittensor", lambda: fake_bt)

        result = runner.invoke(
            cli,
            ["network", "register", "--subnet", "13", "--wallet", "sn13miner"],
        )
        assert result.exit_code == 0
        assert "registered successfully" in result.output.lower()
        assert fake_bt.subtensors[0].register_calls == [("sn13miner", 13)]

    def test_network_info(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
        fake_bt = _FakeBT()
        monkeypatch.setattr(cli_main, "get_bittensor", lambda: fake_bt)

        result = runner.invoke(cli, ["network", "info", "--subnet", "13", "--network", "testnet"])
        assert result.exit_code == 0
        assert "SN13" in result.output
        assert "Miners" in result.output

    def test_network_price(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
        fake_bt = _FakeBT()
        monkeypatch.setattr(cli_main, "get_bittensor", lambda: fake_bt)

        result = runner.invoke(cli, ["network", "price", "--network", "testnet", "--subnet", "13"])
        assert result.exit_code == 0
        assert "context SN13" in result.output
        assert "τ7.250000" in result.output


class TestMonitorCommands:
    def test_monitor_watch_uses_modern_quiet_dashboard(
        self, runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import miner_tools.deregister as deregister_module
        import miner_tools.monitor as monitor_module

        class FakeMonitor:
            def __init__(self, global_cfg, subnets):
                self.global_cfg = global_cfg
                self.subnets = subnets
                history_type = type("History", (), {"readings": []})
                state_type = type(
                    "State",
                    (),
                    {
                        "get_history": lambda self, netuid: history_type(),
                        "poll_counts": {},
                    },
                )
                self.state = state_type()
                self.last_registration_result = {}
                self.last_poll_error = {}
                self.last_poll_time = {}

            async def start(self):
                return None

        class FakeDeregisterMonitor:
            has_entries = False

            def __init__(self, global_cfg, subnets):
                self.global_cfg = global_cfg
                self.subnets = subnets
                self.last_status = {}
                self.last_error = {}

            async def start(self):
                return None

        monkeypatch.setattr(monitor_module, "Monitor", FakeMonitor)
        monkeypatch.setattr(deregister_module, "DeregisterMonitor", FakeDeregisterMonitor)

        result = runner.invoke(cli, ["-c", str(config_path), "monitor", "watch"])

        assert result.exit_code == 0
        assert "JARVIS ORCHESTRATOR" in result.output
        assert "Registration Watch" in result.output
        assert "Running quiet live dashboard" in result.output
        assert "Polling every" not in result.output

    def test_monitor_price_uses_configured_thresholds(
        self, runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import miner_tools.fetcher as fetcher

        async def fake_fetch_burn_cost(*args, **kwargs):
            return type("Reading", (), {"cost_tao": 0.25})()

        monkeypatch.setattr(fetcher, "fetch_burn_cost", fake_fetch_burn_cost)
        monkeypatch.setattr(fetcher, "close_subtensor", lambda: None)

        result = runner.invoke(cli, ["-c", str(config_path), "monitor", "price", "13"])

        assert result.exit_code == 0
        assert "Registration Burn Cost" in result.output
        assert "0.250000" in result.output
        assert "EXCELLENT" in result.output

    def test_legacy_price_alias_still_works(
        self, runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import miner_tools.fetcher as fetcher

        async def fake_fetch_burn_cost(*args, **kwargs):
            return type("Reading", (), {"cost_tao": 0.75})()

        monkeypatch.setattr(fetcher, "fetch_burn_cost", fake_fetch_burn_cost)
        monkeypatch.setattr(fetcher, "close_subtensor", lambda: None)

        result = runner.invoke(cli, ["-c", str(config_path), "price", "13"])

        assert result.exit_code == 0
        assert "0.750000" in result.output
        assert "FAIR" in result.output

    def test_monitor_register_dry_run_uses_config_wallet_without_burning(
        self, runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import miner_tools.fetcher as fetcher

        async def fake_fetch_burn_cost(*args, **kwargs):
            return type("Reading", (), {"cost_tao": 0.1})()

        burned_calls = []
        monkeypatch.setattr(fetcher, "fetch_burn_cost", fake_fetch_burn_cost)
        monkeypatch.setattr(fetcher, "close_subtensor", lambda: None)
        monkeypatch.setattr(
            fetcher,
            "burned_register_sdk",
            lambda *args, **kwargs: burned_calls.append((args, kwargs)),
        )

        result = runner.invoke(
            cli,
            [
                "-c",
                str(config_path),
                "monitor",
                "register",
                "13",
                "--wallet",
                "jarvis",
                "--hotkey",
                "hot",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "wallet=jarvis" in result.output
        assert burned_calls == []

    def test_deregister_check_reports_missing_config_entries(
        self, runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import miner_tools.deregister as deregister_module
        import miner_tools.fetcher as fetcher

        monkeypatch.setattr(fetcher, "close_subtensor", lambda: None)
        monkeypatch.setattr(deregister_module, "get_wallet_hotkey_ss58", lambda wallet_cfg: "hk1")

        result = runner.invoke(cli, ["-c", str(config_path), "deregister-check"])

        assert result.exit_code == 0
        assert "No deregister watches are active" in result.output

    def test_deregister_check_uses_auto_register_wallet_when_enabled(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import miner_tools.deregister as deregister_module
        import miner_tools.fetcher as fetcher

        config_path = _write_config(
            tmp_path,
            """
global:
  subtensor_network: test
subnets:
  - netuid: 13
    price_threshold_tao: 0.5
    auto_register: true
    alerts:
      discord:
        webhook_url: "https://discord.test"
""",
        )

        monkeypatch.setattr(fetcher, "close_subtensor", lambda: None)
        monkeypatch.setattr(fetcher, "is_registered_sdk", lambda *args, **kwargs: True)
        monkeypatch.setattr(deregister_module, "get_wallet_hotkey_ss58", lambda wallet_cfg: "hk1")

        result = runner.invoke(cli, ["-c", str(config_path), "deregister-check"])

        assert result.exit_code == 0
        assert "Deregister Monitor Status" in result.output
        assert "REGISTERED" in result.output


class TestSN13Commands:
    def test_sn13_dd_show_requires_real_cache_by_default(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(cli, ["sn13", "dd", "show"])

        assert result.exit_code == 1
        assert "Run `jarvis-miner sn13 dd refresh`" in result.output

    def test_sn13_dd_show_can_use_sample_desirability(self, runner: CliRunner):
        result = runner.invoke(cli, ["sn13", "dd", "show", "--sample-dd"])

        assert result.exit_code == 0
        assert "Dynamic Desirability Jobs" in result.output
        assert "#bittensor" in result.output
        assert "built-in simulator sample" in result.output

    def test_sn13_dd_refresh_writes_real_cache(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        from subnets.sn13 import gravity

        monkeypatch.setattr(
            gravity,
            "fetch_gravity_records",
            lambda **kwargs: [
                {
                    "id": "gravity_x",
                    "weight": 2.0,
                    "params": {
                        "keyword": None,
                        "platform": "x",
                        "label": "#macrocosmos",
                        "post_start_datetime": None,
                        "post_end_datetime": None,
                    },
                }
            ],
        )

        result = runner.invoke(cli, ["sn13", "dd", "refresh", "--json-output"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["record_count"] == 1
        assert Path(payload["cache_path"]).exists()

    def test_sn13_plan_tasks_outputs_json(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "tasks",
                "--db-path",
                str(db_path),
                "--target-items",
                "2",
                "--max-tasks",
                "1",
                "--sample-dd",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["desirability_jobs"] == 2
        assert len(payload["tasks"]) == 1
        assert payload["tasks"][0]["task_id"].startswith("task_")

    def test_sn13_plan_tasks_uses_env_db_path_by_default(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        env_db_path = tmp_path / "custom-sn13.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "tasks",
                "--target-items",
                "2",
                "--max-tasks",
                "1",
                "--sample-dd",
                "--json-output",
            ],
            env={"JARVIS_SN13_DB_PATH": str(env_db_path)},
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["db_path"] == str(env_db_path)

    def test_sn13_plan_publish_writes_durable_workstream(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        workstream_db_path = project_root / "data" / "workstream.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "publish",
                "--db-path",
                str(db_path),
                "--workstream-db-path",
                str(workstream_db_path),
                "--target-items",
                "2",
                "--max-tasks",
                "2",
                "--sample-dd",
                "--json-output",
                *_publication_economics_args(),
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["published_tasks"] == 2
        assert payload["refused_tasks"] == 0
        assert payload["publication_mode"] == "open_competitive_intake"

        second = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "publish",
                "--db-path",
                str(db_path),
                "--workstream-db-path",
                str(workstream_db_path),
                "--target-items",
                "2",
                "--max-tasks",
                "2",
                "--sample-dd",
                "--json-output",
                *_publication_economics_args(),
            ],
        )

        assert second.exit_code == 0
        workstream = SQLiteWorkstream(workstream_db_path)
        available = workstream.list_available(subnet="sn13")
        assert len(available) == 2
        assert all(task.contract["task_id"] == task.task_id for task in available)

    def test_sn13_plan_publish_refuses_tasks_with_missing_economics(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        workstream_db_path = project_root / "data" / "workstream.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "publish",
                "--db-path",
                str(db_path),
                "--workstream-db-path",
                str(workstream_db_path),
                "--target-items",
                "2",
                "--max-tasks",
                "2",
                "--sample-dd",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["planned_tasks"] == 2
        assert payload["published_tasks"] == 0
        assert payload["refused_tasks"] == 2
        assert "missing_max_task_cost" in payload["refusals"][0]["blockers"]
        workstream = SQLiteWorkstream(workstream_db_path)
        assert workstream.list_available(subnet="sn13") == []

    def test_sn13_plan_publish_console_entrypoint_works_end_to_end(self, tmp_path: Path):
        db_path = tmp_path / "sn13.sqlite3"
        workstream_db_path = tmp_path / "workstream.sqlite3"
        command = [
            sys.executable,
            "-m",
            "cli.main",
            "sn13",
            "plan",
            "publish",
            "--db-path",
            str(db_path),
            "--workstream-db-path",
            str(workstream_db_path),
            "--target-items",
            "2",
            "--max-tasks",
            "2",
            "--sample-dd",
            "--json-output",
            *_publication_economics_args(),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

        result = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["published_tasks"] == 2
        assert payload["refused_tasks"] == 0

    def test_sn13_scheduler_run_refreshes_and_publishes_once(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        workstream_db_path = project_root / "data" / "workstream.sqlite3"
        cache_dir = project_root / "subnets" / "sn13" / "cache" / "gravity"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        from subnets.sn13 import gravity

        def _fake_refresh_gravity_cache(*, cache_dir, timeout_seconds=30, url=None):
            return gravity.write_gravity_cache(
                [
                    {
                        "id": "gravity_x",
                        "weight": 4.0,
                        "params": {"platform": "x", "label": "#macrocosmos"},
                    }
                ],
                cache_dir=cache_dir,
                source_url="https://example.test/total.json",
            )

        monkeypatch.setattr(gravity, "refresh_gravity_cache", _fake_refresh_gravity_cache)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "scheduler",
                "run",
                "--once",
                "--cache-dir",
                str(cache_dir),
                "--db-path",
                str(db_path),
                "--workstream-db-path",
                str(workstream_db_path),
                "--json-output",
                *_publication_economics_args(),
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["desirability_jobs"] == 1
        assert payload["planned_tasks"] == 1
        assert payload["published_tasks"] == 1

    def test_sn13_economics_estimate_outputs_take_decision(self, runner: CliRunner):
        result = runner.invoke(
            cli,
            [
                "sn13",
                "economics",
                "estimate",
                "--source",
                "X",
                "--label",
                "#bittensor",
                "--desirability-job-id",
                "gravity_x",
                "--desirability-weight",
                "2",
                "--quantity-target",
                "1000",
                "--max-task-cost",
                "20",
                "--expected-reward",
                "30",
                "--expected-submitted",
                "1200",
                "--expected-accepted",
                "900",
                "--duplicate-rate",
                "0.04",
                "--rejection-rate",
                "0.10",
                "--validation-pass-probability",
                "0.95",
                "--payout-basis",
                "accepted_scorable_record",
                "--operator-payout",
                "7",
                "--scraper-provider-cost",
                "4",
                "--proxy-cost",
                "1",
                "--compute-cost",
                "0.5",
                "--risk-reserve",
                "2",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["can_take_task"] is True
        assert payload["total_task_cost"] == 14.5
        assert payload["expected_margin"] == 15.5
        assert payload["s3_storage_cost_owner"] == "upstream_destination_not_jarvis_bucket"

    def test_sn13_economics_estimate_blocks_missing_inputs(self, runner: CliRunner):
        result = runner.invoke(
            cli,
            [
                "sn13",
                "economics",
                "estimate",
                "--source",
                "REDDIT",
                "--label",
                "r/bittensor",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["can_take_task"] is False
        assert "missing_max_task_cost" in payload["blockers"]
        assert "missing_payout_basis" in payload["blockers"]

    def test_sn13_economics_s3_cost_calculates_archive_cost(self, runner: CliRunner):
        result = runner.invoke(
            cli,
            [
                "sn13",
                "economics",
                "s3-cost",
                "--storage-gb-month",
                "100",
                "--storage-usd-per-gb-month",
                "0.023",
                "--put-requests",
                "10000",
                "--put-usd-per-1000",
                "0.005",
                "--transfer-out-gb",
                "7",
                "--transfer-out-usd-per-gb",
                "0.09",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["storage_cost"] == 2.3
        assert payload["put_request_cost"] == 0.05
        assert payload["transfer_out_cost"] == 0.63
        assert payload["total"] == 2.98
        assert "Jarvis-owned archive cost only" in payload["note"]

    def test_sn13_readiness_reports_capabilities(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        subnet_dir = project_root / "subnets" / "sn13"
        subnet_dir.mkdir(parents=True)
        capture_dir = subnet_dir / "listener" / "captures"
        capture_dir.mkdir(parents=True)
        (subnet_dir / "state.json").write_text(
            json.dumps({"pid": 1234, "running": True, "network": "testnet", "wallet": "sn13miner"})
        )
        (capture_dir / "summary.json").write_text(
            json.dumps(
                {
                    "capture_dir": str(capture_dir),
                    "total_queries": 3,
                    "counts_by_query_type": {
                        "GetMinerIndex": 1,
                        "GetDataEntityBucket": 1,
                        "GetContentsByBuckets": 1,
                    },
                    "counts_by_validator": {"validator_hotkey": 3},
                    "recent_queries": [],
                }
            )
        )

        home = tmp_path / "home"
        (home / ".bittensor" / "wallets" / "sn13miner" / "hotkeys").mkdir(parents=True)
        (home / ".bittensor" / "wallets" / "sn13miner" / "hotkeys" / "default").write_text("hotkey")

        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cli_main.Path, "home", lambda: home)
        monkeypatch.setattr(cli_main.os, "kill", lambda pid, sig: None)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "readiness",
                "--skip-chain",
                "--registered",
            ],
        )

        assert result.exit_code == 0
        assert "SN13 Readiness" in result.output
        assert "can_serve_validators" in result.output
        assert "Intake personal-operator uploads" in result.output
        assert "Listener captures" in result.output

        json_result = runner.invoke(
            cli,
            [
                "sn13",
                "readiness",
                "--skip-chain",
                "--registered",
                "--json",
            ],
        )

        assert json_result.exit_code == 0
        payload = json.loads(json_result.output)
        assert payload["capabilities"]["can_serve_validators"] is True
        assert payload["capabilities"]["jarvis_can_intake_operator_uploads"] is True
        assert payload["runtime"]["listener_capture_count"] == 3
        assert payload["runtime"]["listener_query_types"] == [
            "GetContentsByBuckets",
            "GetDataEntityBucket",
            "GetMinerIndex",
        ]

    def test_sn13_listener_status_reads_capture_summary(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        capture_dir = project_root / "subnets" / "sn13" / "listener" / "captures"
        capture_dir.mkdir(parents=True)
        (project_root / "subnets" / "sn13" / "state.json").write_text(
            json.dumps({"pid": 7777, "running": True, "network": "testnet", "wallet": "sn13miner"})
        )
        (capture_dir / "summary.json").write_text(
            json.dumps(
                {
                    "capture_dir": str(capture_dir),
                    "total_queries": 4,
                    "counts_by_query_type": {"GetMinerIndex": 2, "GetDataEntityBucket": 2},
                    "counts_by_validator": {"v1": 4},
                    "recent_queries": [],
                }
            )
        )

        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cli_main.os, "kill", lambda pid, sig: None)

        result = runner.invoke(cli, ["sn13", "listener", "status", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["running"] is True
        assert payload["capture_summary"]["total_queries"] == 4

    def test_sn13_listener_verify_fails_when_query_surface_is_incomplete(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        capture_dir = project_root / "subnets" / "sn13" / "listener" / "captures"
        capture_dir.mkdir(parents=True)
        (capture_dir / "summary.json").write_text(
            json.dumps(
                {
                    "capture_dir": str(capture_dir),
                    "total_queries": 2,
                    "counts_by_query_type": {"GetMinerIndex": 2},
                    "counts_by_validator": {"v1": 2},
                    "recent_queries": [],
                }
            )
        )

        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(cli, ["sn13", "listener", "verify", "--json"])

        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["verified"] is False
        assert payload["missing_query_types"] == [
            "GetContentsByBuckets",
            "GetDataEntityBucket",
        ]

    def test_sn13_listener_verify_passes_when_all_queries_are_present(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        capture_dir = project_root / "subnets" / "sn13" / "listener" / "captures"
        capture_dir.mkdir(parents=True)
        (capture_dir / "summary.json").write_text(
            json.dumps(
                {
                    "capture_dir": str(capture_dir),
                    "total_queries": 6,
                    "counts_by_query_type": {
                        "GetContentsByBuckets": 2,
                        "GetDataEntityBucket": 2,
                        "GetMinerIndex": 2,
                    },
                    "counts_by_validator": {"v1": 6},
                    "recent_queries": [],
                }
            )
        )

        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(cli, ["sn13", "listener", "verify", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["verified"] is True

    def test_sn13_operator_and_validator_simulation_share_storage(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        operator_result = runner.invoke(
            cli,
            [
                "sn13",
                "simulate",
                "operator",
                "--db-path",
                str(db_path),
                "--source",
                "X",
                "--label",
                "#bittensor",
                "--count",
                "2",
            ],
        )

        assert operator_result.exit_code == 0
        assert "Stored 2 simulated X submission" in operator_result.output

        validator_result = runner.invoke(
            cli,
            [
                "sn13",
                "simulate",
                "validator",
                "--db-path",
                str(db_path),
                "--query",
                "bucket",
                "--source",
                "X",
                "--label",
                "#bittensor",
                "--limit",
                "5",
                "--json-output",
            ],
        )

        assert validator_result.exit_code == 0
        payload = json.loads(validator_result.output)
        assert payload["summary"]["query"] == "GetDataEntityBucket"
        assert payload["summary"]["entities"] == 2

    def test_workstream_status_reports_runtime_and_store_counts(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        workstream_db_path = project_root / "data" / "workstream.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        publish = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "publish",
                "--db-path",
                str(db_path),
                "--workstream-db-path",
                str(workstream_db_path),
                "--target-items",
                "2",
                "--max-tasks",
                "2",
                "--sample-dd",
                "--json-output",
                *_publication_economics_args(),
            ],
        )
        assert publish.exit_code == 0

        workstream = SQLiteWorkstream(workstream_db_path)
        tasks = workstream.list_tasks(limit=10)
        workstream.record_acceptance(tasks[0].task_id, accepted_count=2)

        simulate = runner.invoke(
            cli,
            [
                "sn13",
                "simulate",
                "operator",
                "--db-path",
                str(db_path),
                "--source",
                "X",
                "--label",
                "#bittensor",
                "--count",
                "1",
            ],
        )
        assert simulate.exit_code == 0

        result = runner.invoke(
            cli,
            [
                "workstream",
                "status",
                "--workstream-db-path",
                str(workstream_db_path),
                "--sn13-db-path",
                str(db_path),
                "--json-output",
            ],
            env={
                "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON": '{"operator_1":"secret"}',
            },
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["auth_required"] is True
        assert payload["configured_operator_count"] == 1
        assert payload["total_tasks"] == 2
        assert payload["open_tasks"] == 1
        assert payload["completed_tasks"] == 1
        assert payload["canonical_entities"] == 1
        assert payload["accepted_submissions"] == 1

        alias_result = runner.invoke(
            cli,
            [
                "workstream",
                "status",
                "--workstream-db-path",
                str(workstream_db_path),
                "--sn13-db-path",
                str(db_path),
                "--json",
            ],
            env={
                "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON": '{"operator_1":"secret"}',
            },
        )

        assert alias_result.exit_code == 0
        assert json.loads(alias_result.output)["total_tasks"] == 2

    def test_workstream_tasks_lists_filtered_durable_tasks(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        workstream_db_path = project_root / "data" / "workstream.sqlite3"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        publish = runner.invoke(
            cli,
            [
                "sn13",
                "plan",
                "publish",
                "--db-path",
                str(db_path),
                "--workstream-db-path",
                str(workstream_db_path),
                "--target-items",
                "2",
                "--max-tasks",
                "2",
                "--sample-dd",
                "--json-output",
                *_publication_economics_args(),
            ],
        )
        assert publish.exit_code == 0

        workstream = SQLiteWorkstream(workstream_db_path)
        tasks = workstream.list_tasks(limit=10)
        workstream.record_acceptance(tasks[0].task_id, accepted_count=1)

        result = runner.invoke(
            cli,
            [
                "workstream",
                "tasks",
                "--workstream-db-path",
                str(workstream_db_path),
                "--status",
                "open",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["task_count"] == 2
        assert payload["tasks"][0]["status"] == "open"
        assert payload["tasks"][0]["accepted_count"] == 1

    def test_sn13_cycle_simulation_outputs_summary(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "repo"
        db_path = project_root / "subnets" / "sn13" / "data" / "sn13.sqlite3"
        export_root = project_root / "subnets" / "sn13" / "exports"
        monkeypatch.setattr(cli_main, "PROJECT_ROOT", project_root)

        result = runner.invoke(
            cli,
            [
                "sn13",
                "simulate",
                "cycle",
                "--db-path",
                str(db_path),
                "--export-root",
                str(export_root),
                "--target-items",
                "2",
                "--max-tasks",
                "2",
                "--sample-dd",
                "--json-output",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["summary"]["desirability_jobs"] == 2
        assert payload["summary"]["planned_tasks"] == 2
        assert payload["summary"]["accepted_submissions"] == 4
        assert payload["summary"]["validator_bucket_entities"] == 2
