"""Shared test fixtures."""

import pytest

from jarvis_miner.models import (
    AlertConfig,
    DiscordConfig,
    GlobalConfig,
    SubnetConfig,
)


@pytest.fixture
def global_config():
    return GlobalConfig(
        subtensor_network="test",
        data_dir="/tmp/jarvis_test",
        trend_window=6,
    )


@pytest.fixture
def subnet_config():
    return SubnetConfig(
        netuid=13,
        price_threshold_tao=0.5,
        alerts=AlertConfig(discord=DiscordConfig(webhook_url="https://discord.test/123")),
        poll_interval_seconds=300,
    )


@pytest.fixture
def multi_subnet_configs():
    return [
        SubnetConfig(
            netuid=6,
            price_threshold_tao=0.5,
            alerts=AlertConfig(discord=DiscordConfig(webhook_url="https://discord.test/6")),
        ),
        SubnetConfig(
            netuid=13,
            price_threshold_tao=0.8,
            alerts=AlertConfig(discord=DiscordConfig(webhook_url="https://discord.test/13")),
        ),
        SubnetConfig(
            netuid=41,
            price_threshold_tao=0.2,
            alerts=AlertConfig(discord=DiscordConfig(webhook_url="https://discord.test/41")),
        ),
    ]
