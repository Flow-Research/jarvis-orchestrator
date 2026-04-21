"""Configuration loader — reads YAML config and resolves env vars."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AlertChannel,
    AlertConfig,
    DeregisterEntry,
    DiscordConfig,
    GlobalConfig,
    SubnetConfig,
    TelegramConfig,
    WalletConfig,
)

ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load environment variables from a .env file if it exists."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        # Don't override existing env vars
        if key and key not in os.environ:
            os.environ[key] = value


# Load .env on module import
_load_dotenv()


def _resolve_env(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(value, str):

        def replacer(match: re.Match) -> str:
            var = match.group(1)
            env_val = os.environ.get(var)
            if env_val is None:
                raise ValueError(f"Environment variable '{var}' is not set")
            return env_val

        return ENV_VAR_PATTERN.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def _parse_alert_config(data: dict, fallback: AlertConfig | None = None) -> AlertConfig:
    """Parse alert configuration from dict.

    If data is empty/missing, uses fallback (global alerts).
    If data has partial fields, merges with fallback.
    """
    # If no alert config at subnet level, use global fallback
    if not data:
        return fallback or AlertConfig()

    discord = None
    telegram = None

    # Parse Discord — use subnet-level if present, else inherit from global
    discord_raw = data.get("discord")
    if discord_raw:
        discord = DiscordConfig(
            webhook_url=discord_raw["webhook_url"],
            mention_role=discord_raw.get("mention_role"),
        )
    elif fallback and fallback.discord:
        discord = fallback.discord

    # Parse Telegram — use subnet-level if present, else inherit from global
    telegram_raw = data.get("telegram")
    if telegram_raw:
        telegram = TelegramConfig(
            bot_token=telegram_raw["bot_token"],
            chat_id=str(telegram_raw["chat_id"]),
            parse_mode=telegram_raw.get("parse_mode", "HTML"),
        )
    elif fallback and fallback.telegram:
        telegram = fallback.telegram

    # Parse channel preference
    channel_str = data.get("channel", "").lower()
    if channel_str:
        channel = {
            "discord": AlertChannel.DISCORD,
            "telegram": AlertChannel.TELEGRAM,
            "both": AlertChannel.BOTH,
            "none": AlertChannel.NONE,
        }.get(channel_str, AlertChannel.BOTH)
    elif fallback:
        channel = fallback.channel
    else:
        channel = AlertChannel.BOTH

    return AlertConfig(discord=discord, telegram=telegram, channel=channel)


def load_config(path: str | Path) -> tuple[GlobalConfig, list[SubnetConfig]]:
    """Load and validate configuration from a YAML file.

    Returns (global_config, subnet_configs).
    Environment variables are resolved from ${VAR_NAME} patterns.

    Alerts defined in global.alerts are inherited by all subnets.
    Per-subnet alert settings override the global defaults.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if not raw:
        raise ValueError(f"Config file is empty: {path}")

    raw = _resolve_env(raw)

    # Parse global config
    g = raw.get("global", {})

    # Parse wallet config
    wallet_raw = g.get("wallet", {})
    wallet_cfg = WalletConfig(
        name=wallet_raw.get("name", "default"),
        hotkey=wallet_raw.get("hotkey", "default"),
        path=wallet_raw.get("path", "~/.bittensor/wallets"),
    )

    global_cfg = GlobalConfig(
        subtensor_network=g.get("subtensor_network", "finney"),
        subtensor_endpoint=g.get("subtensor_endpoint"),
        taostats_api_key=g.get("taostats_api_key"),
        data_dir=Path(g.get("data_dir", "data")),
        log_level=g.get("log_level", "INFO"),
        max_history_days=g.get("max_history_days", 30),
        trend_window=g.get("trend_window", 6),
        discord_username=g.get("discord_username", "Jarvis Miner"),
        discord_avatar_url=g.get("discord_avatar_url", ""),
        alert_cooldown_seconds=g.get("alert_cooldown_seconds", 600),
        price_source=g.get("price_source", "sdk"),
        wallet=wallet_cfg,
    )

    # Parse global alerts (inherited by all subnets)
    global_alerts_raw = g.get("alerts", {})
    global_alerts = _parse_alert_config(global_alerts_raw)

    # Parse subnet configs
    subnets_raw = raw.get("subnets", [])
    if not subnets_raw:
        raise ValueError("No subnets defined in config")

    subnet_cfgs: list[SubnetConfig] = []
    seen_netuids: set[int] = set()

    for entry in subnets_raw:
        netuid = entry.get("netuid")
        if netuid is None:
            raise ValueError(f"Subnet entry missing 'netuid': {entry}")
        if netuid in seen_netuids:
            raise ValueError(f"Duplicate netuid: {netuid}")
        seen_netuids.add(netuid)

        # Parse subnet-level alerts (falls back to global)
        alerts_raw = entry.get("alerts", {})

        # Backward compat: support old-style alert_channel at top level
        if not alerts_raw and entry.get("alert_channel"):
            alerts_raw = {
                "discord": {
                    "webhook_url": entry["alert_channel"],
                    "mention_role": entry.get("mention_role"),
                }
            }

        alerts = _parse_alert_config(alerts_raw, fallback=global_alerts)

        # Parse deregister entries
        deregister_raw = entry.get("deregister", [])
        deregister_entries = []
        for de in deregister_raw:
            deregister_entries.append(
                DeregisterEntry(
                    hotkey_ss58=de["hotkey"],
                    label=de.get("label"),
                )
            )

        subnet_cfgs.append(
            SubnetConfig(
                netuid=netuid,
                price_threshold_tao=entry.get("price_threshold_tao", 0.5),
                alerts=alerts,
                poll_interval_seconds=entry.get("poll_interval_seconds", 300),
                min_poll_interval_seconds=entry.get("min_poll_interval_seconds", 60),
                max_spend_tao=entry.get("max_spend_tao"),
                auto_register=entry.get("auto_register", False),
                enabled=entry.get("enabled", True),
                nickname=entry.get("nickname"),
                floor_detection=entry.get("floor_detection", True),
                floor_window=entry.get("floor_window", 6),
                adaptive_polling=entry.get("adaptive_polling", True),
                near_threshold_multiplier=entry.get("near_threshold_multiplier", 1.5),
                signal_file=entry.get("signal_file"),
                deregister_entries=deregister_entries,
            )
        )

    return global_cfg, subnet_cfgs


def default_config_path() -> Path:
    """Return the default config file path."""
    env_path = os.environ.get("JARVIS_CONFIG")
    if env_path:
        return Path(env_path)
    # Default to config.yaml inside the miner_tools package
    package_dir = Path(__file__).parent
    return package_dir / "config" / "config.yaml"
