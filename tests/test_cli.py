"""Tests for CLI — command parsing, output validation."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from jarvis_miner.cli import cli

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


# ── Version ──────────────────────────────────────────────────────────────


class TestVersion:
    def test_version_flag(self, runner: CliRunner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output


# ── Help ─────────────────────────────────────────────────────────────────


class TestHelp:
    def test_main_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Registration Price Monitor" in result.output

    def test_watch_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0

    def test_price_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["price", "--help"])
        assert result.exit_code == 0


# ── Validate command ─────────────────────────────────────────────────────


class TestValidate:
    def test_valid_config(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_invalid_config_path(self, runner: CliRunner):
        result = runner.invoke(cli, ["-c", "/nonexistent.yaml", "validate"])
        assert result.exit_code == 1

    def test_validate_shows_subnet_count(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "validate"])
        assert "1 subnet" in result.output


# ── Config show command ──────────────────────────────────────────────────


class TestConfigShow:
    def test_shows_global_settings(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "config-show"])
        assert result.exit_code == 0
        assert "Global Settings" in result.output
        assert "test" in result.output  # network

    def test_shows_subnets(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "config-show"])
        assert "Test Subnet" in result.output
        assert "0.5000" in result.output  # threshold


# ── Status command ───────────────────────────────────────────────────────


class TestStatus:
    def test_no_history(self, runner: CliRunner, config_path: Path):
        result = runner.invoke(cli, ["-c", str(config_path), "status"])
        assert result.exit_code == 0
        assert "No price history" in result.output

    def test_with_history(self, runner: CliRunner, tmp_path: Path):
        # Create data dir and state file
        import json
        from datetime import datetime, timezone

        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)

        # Write config pointing to this data_dir
        config_content = f"""
global:
  subtensor_network: test
  data_dir: {data_dir}
subnets:
  - netuid: 13
    nickname: "Test Subnet"
    price_threshold_tao: 0.5
    poll_interval_seconds: 300
    enabled: true
    alerts:
      channel: discord
      discord:
        webhook_url: "https://discord.com/api/webhooks/test/test"
"""
        config_path = _write_config(tmp_path, config_content)

        # Create fake state
        state = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "histories": {
                "13": {
                    "netuid": 13,
                    "readings": [
                        {
                            "netuid": 13,
                            "cost_tao": 0.5,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "trend": "stable",
                            "source": "sdk",
                        }
                    ],
                    "detected_floors": [],
                }
            },
            "last_alert_time": {},
            "last_floor_alert_time": {},
            "poll_counts": {"13": 5},
        }
        state_path = data_dir / "monitor_state.json"
        state_path.write_text(json.dumps(state))

        result = runner.invoke(cli, ["-c", str(config_path), "status"])
        assert result.exit_code == 0
        # Should show the subnet data (nickname)
        assert "Test Subnet" in result.output or "0.5" in result.output


# ── Missing config ───────────────────────────────────────────────────────


class TestMissingConfig:
    def test_missing_config_file(self, runner: CliRunner):
        result = runner.invoke(cli, ["-c", "/does/not/exist.yaml", "validate"])
        assert result.exit_code == 1
        assert "Config error" in result.output or "not found" in result.output
