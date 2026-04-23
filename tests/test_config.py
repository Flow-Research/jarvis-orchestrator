"""Tests for config — YAML loading, env var resolution, validation."""

from pathlib import Path

import pytest

from miner_tools.config import default_config_path, load_config

# ── Helpers ──────────────────────────────────────────────────────────────


def _write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return path


# ── Valid configs ────────────────────────────────────────────────────────


class TestLoadConfigValid:
    def test_minimal_config(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
global:
  subtensor_network: finney
subnets:
  - netuid: 13
    price_threshold_tao: 0.5
    alerts:
      discord:
        webhook_url: "https://discord.test"
""",
        )
        global_cfg, subnets = load_config(cfg_path)
        assert global_cfg.subtensor_network == "finney"
        assert len(subnets) == 1
        assert subnets[0].netuid == 13

    def test_multiple_subnets(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    price_threshold_tao: 0.5
    alerts:
      discord:
        webhook_url: "https://test1"
  - netuid: 6
    price_threshold_tao: 0.3
    alerts:
      telegram:
        bot_token: "123:abc"
        chat_id: "456"
""",
        )
        _, subnets = load_config(cfg_path)
        assert len(subnets) == 2
        assert subnets[0].alerts.discord is not None
        assert subnets[1].alerts.telegram is not None

    def test_all_subnet_options(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    nickname: "Test"
    price_threshold_tao: 0.5
    poll_interval_seconds: 120
    min_poll_interval_seconds: 30
    max_spend_tao: 1.0
    adaptive_polling: true
    floor_detection: true
    floor_window: 8
    signal_file: "data/signals/test.json"
    enabled: true
    alerts:
      channel: both
      discord:
        webhook_url: "https://test"
      telegram:
        bot_token: "123:abc"
        chat_id: "456"
""",
        )
        _, subnets = load_config(cfg_path)
        s = subnets[0]
        assert s.nickname == "Test"
        assert s.poll_interval_seconds == 120
        assert s.min_poll_interval_seconds == 30
        assert s.max_spend_tao == 1.0
        assert s.floor_window == 8
        assert s.signal_file == "data/signals/test.json"

    def test_global_options(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
global:
  subtensor_network: test
  subtensor_endpoint: "ws://localhost:9944"
  data_dir: "/tmp/data"
  log_level: DEBUG
  max_history_days: 60
  trend_window: 10
  alert_cooldown_seconds: 300
  price_source: api
  discord_username: "Test Bot"
subnets:
  - netuid: 1
    alerts:
      discord:
        webhook_url: "https://test"
""",
        )
        global_cfg, _ = load_config(cfg_path)
        assert global_cfg.subtensor_network == "test"
        assert global_cfg.subtensor_endpoint == "ws://localhost:9944"
        assert global_cfg.log_level == "DEBUG"
        assert global_cfg.trend_window == 10
        assert global_cfg.price_source == "api"
        assert global_cfg.discord_username == "Test Bot"

    def test_backward_compat_alert_channel(self, tmp_path: Path):
        """Old-style alert_channel at top level should still work."""
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    alert_channel: "https://discord.test"
""",
        )
        _, subnets = load_config(cfg_path)
        assert subnets[0].alerts.discord is not None
        assert subnets[0].alerts.discord.webhook_url == "https://discord.test"

    def test_disabled_subnet(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    enabled: false
    alerts:
      discord:
        webhook_url: "https://test"
""",
        )
        _, subnets = load_config(cfg_path)
        assert subnets[0].enabled is False

    def test_global_alerts_inherited(self, tmp_path: Path):
        """Subnets should inherit alerts from global config."""
        cfg_path = _write_config(
            tmp_path,
            """
global:
  alerts:
    channel: both
    discord:
      webhook_url: "https://global-discord"
    telegram:
      bot_token: "global-token"
      chat_id: "12345"
subnets:
  - netuid: 13
    price_threshold_tao: 0.5
  - netuid: 6
    price_threshold_tao: 0.3
""",
        )
        _, subnets = load_config(cfg_path)
        # Both subnets should have inherited global alerts
        assert subnets[0].alerts.discord.webhook_url == "https://global-discord"
        assert subnets[0].alerts.telegram.bot_token == "global-token"
        assert subnets[1].alerts.discord.webhook_url == "https://global-discord"
        assert subnets[1].alerts.telegram.chat_id == "12345"

    def test_subnet_alerts_override_global(self, tmp_path: Path):
        """Subnet-level alerts should override global alerts."""
        cfg_path = _write_config(
            tmp_path,
            """
global:
  alerts:
    discord:
      webhook_url: "https://global-discord"
subnets:
  - netuid: 13
    alerts:
      discord:
        webhook_url: "https://subnet-specific-discord"
  - netuid: 6
""",
        )
        _, subnets = load_config(cfg_path)
        # SN13 has custom webhook
        assert subnets[0].alerts.discord.webhook_url == "https://subnet-specific-discord"
        # SN6 inherits global
        assert subnets[1].alerts.discord.webhook_url == "https://global-discord"


# ── Env var resolution ───────────────────────────────────────────────────


class TestEnvVarResolution:
    def test_resolves_env_vars(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TEST_WEBHOOK", "https://discord.com/real")
        monkeypatch.setenv("TEST_TOKEN", "123:secret")
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    alerts:
      discord:
        webhook_url: "${TEST_WEBHOOK}"
      telegram:
        bot_token: "${TEST_TOKEN}"
        chat_id: "456"
""",
        )
        _, subnets = load_config(cfg_path)
        assert subnets[0].alerts.discord.webhook_url == "https://discord.com/real"
        assert subnets[0].alerts.telegram.bot_token == "123:secret"

    def test_resolves_env_vars_for_numeric_and_bool_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("TEST_THRESHOLD", "0.05")
        monkeypatch.setenv("TEST_MAX_SPEND", "0.10")
        monkeypatch.setenv("TEST_AUTO_REGISTER", "1")
        monkeypatch.setenv("TEST_ENABLED", "true")
        monkeypatch.setenv("TEST_POLL", "300")
        monkeypatch.setenv("TEST_MIN_POLL", "60")
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: "13"
    price_threshold_tao: "${TEST_THRESHOLD}"
    max_spend_tao: "${TEST_MAX_SPEND}"
    auto_register: "${TEST_AUTO_REGISTER}"
    enabled: "${TEST_ENABLED}"
    poll_interval_seconds: "${TEST_POLL}"
    min_poll_interval_seconds: "${TEST_MIN_POLL}"
    alerts:
      discord:
        webhook_url: "https://discord.test"
""",
        )
        _, subnets = load_config(cfg_path)
        subnet = subnets[0]
        assert subnet.netuid == 13
        assert subnet.price_threshold_tao == 0.05
        assert subnet.max_spend_tao == 0.10
        assert subnet.auto_register is True
        assert subnet.enabled is True
        assert subnet.poll_interval_seconds == 300
        assert subnet.min_poll_interval_seconds == 60

    def test_missing_env_var_raises(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    alerts:
      discord:
        webhook_url: "${NONEXISTENT_VAR_12345}"
""",
        )
        with pytest.raises(ValueError, match="NONEXISTENT_VAR_12345"):
            load_config(cfg_path)


# ── Invalid configs ──────────────────────────────────────────────────────


class TestLoadConfigInvalid:
    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_empty_file(self, tmp_path: Path):
        cfg_path = _write_config(tmp_path, "")
        with pytest.raises(ValueError, match="empty"):
            load_config(cfg_path)

    def test_no_subnets(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
global:
  subtensor_network: finney
""",
        )
        with pytest.raises(ValueError, match="No subnets"):
            load_config(cfg_path)

    def test_missing_netuid(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - price_threshold_tao: 0.5
""",
        )
        with pytest.raises(ValueError, match="missing 'netuid'"):
            load_config(cfg_path)

    def test_duplicate_netuid(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    alerts:
      discord:
        webhook_url: "https://test1"
  - netuid: 13
    alerts:
      discord:
        webhook_url: "https://test2"
""",
        )
        with pytest.raises(ValueError, match="Duplicate netuid"):
            load_config(cfg_path)

    def test_invalid_threshold_validation(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    price_threshold_tao: -1
    alerts:
      discord:
        webhook_url: "https://test"
""",
        )
        with pytest.raises(ValueError):
            load_config(cfg_path)

    def test_invalid_poll_interval(self, tmp_path: Path):
        cfg_path = _write_config(
            tmp_path,
            """
subnets:
  - netuid: 13
    poll_interval_seconds: 5
    alerts:
      discord:
        webhook_url: "https://test"
""",
        )
        with pytest.raises(ValueError):
            load_config(cfg_path)


# ── default_config_path ──────────────────────────────────────────────────


class TestDefaultConfigPath:
    def test_default(self):
        path = default_config_path()
        # Config is inside the miner_tools package
        assert path.name == "config.yaml"
        assert "miner_tools" in str(path)

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CONFIG", "/custom/path.yaml")
        path = default_config_path()
        assert path == Path("/custom/path.yaml")
