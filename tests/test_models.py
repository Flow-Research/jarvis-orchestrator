"""Tests for models — data structures, validation, persistence."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis_miner.models import (
    AlertChannel,
    AlertConfig,
    AlertEvent,
    AlertLevel,
    DiscordConfig,
    FloorEvent,
    GlobalConfig,
    MonitorState,
    PriceHistory,
    PriceReading,
    SubnetConfig,
    TelegramConfig,
    Trend,
)

# ── Trend ────────────────────────────────────────────────────────────────


class TestTrend:
    def test_values(self):
        assert Trend.RISING.value == "rising"
        assert Trend.STABLE.value == "stable"
        assert Trend.FALLING.value == "falling"
        assert Trend.UNKNOWN.value == "unknown"

    def test_from_string(self):
        assert Trend("rising") == Trend.RISING
        assert Trend("unknown") == Trend.UNKNOWN


# ── AlertLevel ───────────────────────────────────────────────────────────


class TestAlertLevel:
    def test_values(self):
        assert AlertLevel.OK.value == "ok"
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.CRITICAL.value == "critical"
        assert AlertLevel.FLOOR.value == "floor"


# ── SubnetConfig ─────────────────────────────────────────────────────────


class TestSubnetConfig:
    def _make_config(self, **kwargs):
        defaults = dict(
            netuid=13,
            price_threshold_tao=0.5,
            alerts=AlertConfig(),
            poll_interval_seconds=300,
        )
        defaults.update(kwargs)
        return SubnetConfig(**defaults)

    def test_valid_config(self):
        cfg = self._make_config()
        assert cfg.netuid == 13
        assert cfg.price_threshold_tao == 0.5
        assert cfg.label == "Subnet 13"

    def test_label_with_nickname(self):
        cfg = self._make_config(nickname="My Subnet")
        assert cfg.label == "My Subnet"

    def test_invalid_netuid(self):
        with pytest.raises(ValueError, match="netuid must be >= 0"):
            self._make_config(netuid=-1)

    def test_invalid_threshold(self):
        with pytest.raises(ValueError, match="price_threshold_tao must be >= 0"):
            self._make_config(price_threshold_tao=-0.1)

    def test_invalid_poll_interval(self):
        with pytest.raises(ValueError, match="poll_interval_seconds must be >= 30"):
            self._make_config(poll_interval_seconds=10)

    def test_invalid_max_spend(self):
        with pytest.raises(ValueError, match="max_spend_tao must be >= 0"):
            self._make_config(max_spend_tao=-1)

    def test_defaults(self):
        cfg = self._make_config()
        assert cfg.min_poll_interval_seconds == 60
        assert cfg.adaptive_polling is True
        assert cfg.floor_detection is True
        assert cfg.floor_window == 6
        assert cfg.signal_file is None
        assert cfg.enabled is True


# ── AlertConfig ──────────────────────────────────────────────────────────


class TestAlertConfig:
    def test_default_channel(self):
        cfg = AlertConfig()
        assert cfg.channel == AlertChannel.BOTH
        assert cfg.has_any is False

    def test_discord_only(self):
        cfg = AlertConfig(
            discord=DiscordConfig(webhook_url="https://discord.test"),
            channel=AlertChannel.DISCORD,
        )
        assert cfg.has_any is True
        assert cfg.channel == AlertChannel.DISCORD

    def test_telegram_only(self):
        cfg = AlertConfig(
            telegram=TelegramConfig(bot_token="123:abc", chat_id="456"),
            channel=AlertChannel.TELEGRAM,
        )
        assert cfg.has_any is True

    def test_both_channels(self):
        cfg = AlertConfig(
            discord=DiscordConfig(webhook_url="https://discord.test"),
            telegram=TelegramConfig(bot_token="123:abc", chat_id="456"),
        )
        assert cfg.has_any is True
        assert cfg.channel == AlertChannel.BOTH


# ── PriceReading ─────────────────────────────────────────────────────────


class TestPriceReading:
    def test_creation(self):
        reading = PriceReading(
            netuid=13,
            cost_tao=0.42,
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.netuid == 13
        assert reading.cost_tao == 0.42
        assert reading.source == "sdk"

    def test_to_dict(self):
        ts = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        reading = PriceReading(netuid=13, cost_tao=0.5, timestamp=ts, trend=Trend.RISING)
        d = reading.to_dict()
        assert d["netuid"] == 13
        assert d["cost_tao"] == 0.5
        assert d["trend"] == "rising"
        assert "2026-03-25" in d["timestamp"]

    def test_from_dict(self):
        d = {
            "netuid": 13,
            "cost_tao": 0.5,
            "timestamp": "2026-03-25T12:00:00+00:00",
            "trend": "stable",
            "source": "api",
        }
        reading = PriceReading.from_dict(d)
        assert reading.netuid == 13
        assert reading.source == "api"
        assert reading.trend == Trend.STABLE


# ── PriceHistory ─────────────────────────────────────────────────────────


class TestPriceHistory:
    def _make_history(self, prices: list[float]) -> PriceHistory:
        history = PriceHistory(netuid=13)
        for p in prices:
            history.add(
                PriceReading(
                    netuid=13,
                    cost_tao=p,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        return history

    def test_add_and_count(self):
        history = self._make_history([0.5, 0.6, 0.7])
        assert len(history.readings) == 3

    def test_recent(self):
        history = self._make_history([0.1, 0.2, 0.3, 0.4, 0.5])
        recent = history.recent(3)
        assert len(recent) == 3
        assert recent[0].cost_tao == 0.3

    def test_min_max_avg(self):
        history = self._make_history([0.5, 0.3, 0.8, 0.2, 0.6])
        assert history.min_price() == 0.2
        assert history.max_price() == 0.8
        assert abs(history.avg_price() - 0.48) < 0.001

    def test_min_max_empty(self):
        history = PriceHistory(netuid=13)
        assert history.min_price() is None
        assert history.max_price() is None
        assert history.avg_price() is None

    def test_trend_rising(self):
        history = self._make_history([0.3, 0.35, 0.4, 0.45, 0.5, 0.55])
        assert history.compute_trend(6) == Trend.RISING

    def test_trend_falling(self):
        history = self._make_history([0.6, 0.55, 0.5, 0.45, 0.4, 0.35])
        assert history.compute_trend(6) == Trend.FALLING

    def test_trend_stable(self):
        history = self._make_history([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        assert history.compute_trend(6) == Trend.STABLE

    def test_trend_unknown_insufficient_data(self):
        history = self._make_history([0.5, 0.5])
        assert history.compute_trend(6) == Trend.UNKNOWN

    def test_sparkline(self):
        history = self._make_history([0.1, 0.5, 0.3, 0.8, 0.2])
        spark = history.sparkline(10)
        assert len(spark) == 5
        assert isinstance(spark, str)

    def test_sparkline_single_reading(self):
        history = self._make_history([0.5])
        spark = history.sparkline(10)
        assert spark == "─" * 10

    def test_sparkline_empty(self):
        history = PriceHistory(netuid=13)
        spark = history.sparkline(10)
        assert spark == "─" * 10

    def test_floor_detection_decline_then_rise(self):
        # Prices decline, hit floor, then rise slightly
        prices = [0.8, 0.7, 0.6, 0.5, 0.42, 0.38, 0.39, 0.40]
        history = self._make_history(prices)
        floor = history.detect_floor(6)
        assert floor is not None
        assert floor.floor_price == 0.38
        assert floor.current_rise_pct < 10

    def test_floor_detection_no_floor_rising(self):
        prices = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55]
        history = self._make_history(prices)
        assert history.detect_floor(6) is None

    def test_floor_detection_no_floor_falling(self):
        prices = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        history = self._make_history(prices)
        assert history.detect_floor(6) is None

    def test_floor_detection_rise_too_large(self):
        # Floor detected but rise is > 10%
        prices = [0.8, 0.7, 0.6, 0.5, 0.38, 0.45]
        history = self._make_history(prices)
        floor = history.detect_floor(6)
        # rise from 0.38 to 0.45 is ~18%, should be rejected
        assert floor is None

    def test_floor_detection_insufficient_data(self):
        prices = [0.5, 0.4, 0.3]
        history = self._make_history(prices)
        assert history.detect_floor(6) is None

    def test_to_from_dict(self):
        history = self._make_history([0.5, 0.6, 0.7])
        d = history.to_dict()
        restored = PriceHistory.from_dict(d)
        assert restored.netuid == 13
        assert len(restored.readings) == 3
        assert restored.readings[0].cost_tao == 0.5


# ── MonitorState ─────────────────────────────────────────────────────────


class TestMonitorState:
    def test_empty_state(self):
        state = MonitorState()
        assert state.histories == {}
        assert state.started_at is None

    def test_get_history_creates(self):
        state = MonitorState()
        h = state.get_history(13)
        assert h.netuid == 13
        assert 13 in state.histories

    def test_save_and_load(self, tmp_path: Path):
        state = MonitorState()
        state.started_at = datetime.now(timezone.utc)
        history = state.get_history(13)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.5,
                timestamp=datetime.now(timezone.utc),
            )
        )
        state.poll_counts[13] = 42

        path = tmp_path / "state.json"
        state.save(path)

        loaded = MonitorState.load(path)
        assert loaded.started_at is not None
        assert len(loaded.histories) == 1
        assert loaded.poll_counts[13] == 42
        assert loaded.get_history(13).readings[0].cost_tao == 0.5

    def test_load_nonexistent(self, tmp_path: Path):
        state = MonitorState.load(tmp_path / "nonexistent.json")
        assert state.histories == {}


# ── AlertEvent ───────────────────────────────────────────────────────────


class TestAlertEvent:
    def _make_event(self, level=AlertLevel.OK, **kwargs):
        defaults = dict(
            netuid=13,
            level=level,
            title="Test Alert",
            message="Test message",
            cost_tao=0.4,
            threshold_tao=0.5,
            trend=Trend.STABLE,
        )
        defaults.update(kwargs)
        return AlertEvent(**defaults)

    def test_color_mapping(self):
        assert self._make_event(AlertLevel.OK).color == 0x2ECC71
        assert self._make_event(AlertLevel.CRITICAL).color == 0xE74C3C
        assert self._make_event(AlertLevel.FLOOR).color == 0x9B59B6

    def test_emoji(self):
        assert self._make_event(AlertLevel.OK).emoji == "🟢"
        assert self._make_event(AlertLevel.FLOOR).emoji == "🔵"

    def test_telegram_emoji(self):
        assert self._make_event(AlertLevel.OK).telegram_emoji == "✅"
        assert self._make_event(AlertLevel.FLOOR).telegram_emoji == "💎"

    def test_discord_embed(self):
        event = self._make_event()
        embed = event.to_discord_embed()
        assert "title" in embed
        assert "fields" in embed
        assert len(embed["fields"]) == 3

    def test_discord_embed_with_floor(self):
        event = self._make_event(
            level=AlertLevel.FLOOR,
            floor_event=FloorEvent(
                netuid=13,
                floor_price=0.3,
                timestamp=datetime.now(timezone.utc),
                readings_before=3,
                current_rise_pct=5.0,
            ),
        )
        embed = event.to_discord_embed()
        assert len(embed["fields"]) == 5  # +2 floor fields

    def test_telegram_text(self):
        event = self._make_event()
        text = event.to_telegram_text()
        assert "Test Alert" in text
        assert "0.4000 TAO" in text

    def test_signal_dict(self):
        event = self._make_event(AlertLevel.OK)
        d = event.to_signal_dict()
        assert d["action"] == "register"
        assert d["cost_tao"] == 0.4
        assert d["level"] == "ok"

    def test_signal_dict_wait(self):
        event = self._make_event(AlertLevel.WARNING)
        d = event.to_signal_dict()
        assert d["action"] == "wait"

    def test_signal_dict_floor(self):
        event = self._make_event(AlertLevel.FLOOR)
        d = event.to_signal_dict()
        assert d["action"] == "register"


# ── GlobalConfig ─────────────────────────────────────────────────────────


class TestGlobalConfig:
    def test_defaults(self):
        cfg = GlobalConfig()
        assert cfg.subtensor_network == "finney"
        assert cfg.trend_window == 6
        assert cfg.price_source == "sdk"

    def test_data_dir_from_string(self):
        cfg = GlobalConfig(data_dir="/tmp/data")
        assert isinstance(cfg.data_dir, Path)
        assert str(cfg.data_dir) == "/tmp/data"

    def test_invalid_trend_window(self):
        with pytest.raises(ValueError, match="trend_window must be >= 3"):
            GlobalConfig(trend_window=2)
