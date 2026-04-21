"""Tests for the grouped CLI surface."""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli import cli  # noqa: E402
import cli.main as cli_main

# ── Helpers ──────────────────────────────────────────────────────────────


def _write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return path


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

    def Wallet(self, name: str):
        wallet = _FakeWallet(name)
        self.wallets.append(wallet)
        return wallet

    def Subtensor(self, network: str):
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

    def test_wallet_info_uses_configured_wallets(self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    def test_miner_stop_updates_state(self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

        result = runner.invoke(cli, ["network", "register", "--subnet", "13", "--wallet", "sn13miner"])
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
