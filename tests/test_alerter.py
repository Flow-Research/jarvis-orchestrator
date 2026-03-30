"""Tests for alerter — alert building, Discord/Telegram payloads, signals."""

import json
from datetime import datetime, timezone
from pathlib import Path

from jarvis_miner.alerter import build_alert_event, write_signal
from jarvis_miner.models import (
    AlertConfig,
    AlertEvent,
    AlertLevel,
    DiscordConfig,
    FloorEvent,
    SubnetConfig,
    Trend,
)

# ── build_alert_event ────────────────────────────────────────────────────


class TestBuildAlertEvent:
    def _make_subnet(self, **kwargs):
        defaults = dict(
            netuid=13,
            price_threshold_tao=0.5,
            alerts=AlertConfig(
                discord=DiscordConfig(webhook_url="https://test", mention_role="123")
            ),
        )
        defaults.update(kwargs)
        return SubnetConfig(**defaults)

    def _make_reading(self, cost_tao: float):
        from jarvis_miner.models import PriceReading

        return PriceReading(
            netuid=13,
            cost_tao=cost_tao,
            timestamp=datetime.now(timezone.utc),
        )

    def test_excellent_price(self):
        subnet = self._make_subnet()
        reading = self._make_reading(0.1)  # 20% of threshold
        event = build_alert_event(subnet, reading, Trend.STABLE)
        assert event.level == AlertLevel.OK
        assert "Very Low" in event.title

    def test_good_price(self):
        subnet = self._make_subnet()
        reading = self._make_reading(0.4)  # 80% of threshold
        event = build_alert_event(subnet, reading, Trend.FALLING)
        assert event.level == AlertLevel.OK
        assert "Below Threshold" in event.title

    def test_fair_price(self):
        subnet = self._make_subnet()
        reading = self._make_reading(0.55)  # 110% of threshold
        event = build_alert_event(subnet, reading, Trend.STABLE)
        assert event.level == AlertLevel.INFO
        assert "Near Threshold" in event.title

    def test_warning_price(self):
        subnet = self._make_subnet()
        reading = self._make_reading(0.9)  # 180% of threshold
        event = build_alert_event(subnet, reading, Trend.RISING)
        assert event.level == AlertLevel.WARNING
        assert "Elevated" in event.title

    def test_critical_price(self):
        subnet = self._make_subnet()
        reading = self._make_reading(1.8)  # 360% of threshold
        event = build_alert_event(subnet, reading, Trend.RISING)
        assert event.level == AlertLevel.CRITICAL
        assert "Very High" in event.title

    def test_event_has_mention_role(self):
        subnet = self._make_subnet()
        reading = self._make_reading(0.4)
        event = build_alert_event(subnet, reading, Trend.STABLE)
        assert event.mention_role == "123"


# ── AlertEvent payloads ──────────────────────────────────────────────────


class TestAlertEventPayloads:
    def _make_event(self, level=AlertLevel.OK, floor=None):
        return AlertEvent(
            netuid=13,
            level=level,
            title="Test",
            message="Test message",
            cost_tao=0.4,
            threshold_tao=0.5,
            trend=Trend.STABLE,
            mention_role="123",
            floor_event=floor,
        )

    def test_discord_embed_structure(self):
        event = self._make_event()
        embed = event.to_discord_embed()
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "fields" in embed
        assert "timestamp" in embed
        assert "footer" in embed

    def test_discord_embed_fields_count(self):
        event = self._make_event()
        assert len(event.to_discord_embed()["fields"]) == 3

    def test_discord_embed_with_floor(self):
        floor = FloorEvent(
            netuid=13,
            floor_price=0.3,
            timestamp=datetime.now(timezone.utc),
            readings_before=3,
            current_rise_pct=5.0,
        )
        event = self._make_event(floor=floor)
        assert len(event.to_discord_embed()["fields"]) == 5

    def test_telegram_text_format(self):
        event = self._make_event()
        text = event.to_telegram_text()
        assert "<b>Test</b>" in text
        assert "0.4000 TAO" in text
        assert "0.5000 TAO" in text

    def test_telegram_text_with_floor(self):
        floor = FloorEvent(
            netuid=13,
            floor_price=0.3,
            timestamp=datetime.now(timezone.utc),
            readings_before=3,
            current_rise_pct=5.0,
        )
        event = self._make_event(floor=floor)
        text = event.to_telegram_text()
        assert "0.3000 TAO" in text
        assert "+5.0%" in text

    def test_signal_dict_ok_action(self):
        event = self._make_event(AlertLevel.OK)
        d = event.to_signal_dict()
        assert d["action"] == "register"
        assert d["netuid"] == 13
        assert d["level"] == "ok"

    def test_signal_dict_floor_action(self):
        event = self._make_event(AlertLevel.FLOOR)
        assert event.to_signal_dict()["action"] == "register"

    def test_signal_dict_warning_action(self):
        event = self._make_event(AlertLevel.WARNING)
        assert event.to_signal_dict()["action"] == "wait"

    def test_signal_dict_critical_action(self):
        event = self._make_event(AlertLevel.CRITICAL)
        assert event.to_signal_dict()["action"] == "wait"


# ── write_signal ─────────────────────────────────────────────────────────


class TestWriteSignal:
    def test_creates_file(self, tmp_path: Path):
        event = AlertEvent(
            netuid=13,
            level=AlertLevel.OK,
            title="Test",
            message="Test",
            cost_tao=0.4,
            threshold_tao=0.5,
            trend=Trend.STABLE,
        )
        signal_path = tmp_path / "signals" / "sn13.json"
        write_signal(event, signal_path)

        assert signal_path.exists()
        data = json.loads(signal_path.read_text())
        assert data["netuid"] == 13
        assert data["action"] == "register"

    def test_creates_parent_dirs(self, tmp_path: Path):
        event = AlertEvent(
            netuid=6,
            level=AlertLevel.FLOOR,
            title="Floor",
            message="Floor detected",
            cost_tao=0.3,
            threshold_tao=0.5,
            trend=Trend.RISING,
        )
        signal_path = tmp_path / "deep" / "nested" / "signals" / "sn6.json"
        write_signal(event, signal_path)
        assert signal_path.exists()


# ── Edge cases ───────────────────────────────────────────────────────────


class TestAlertEdgeCases:
    def test_zero_threshold(self):
        from jarvis_miner.models import PriceReading

        subnet = SubnetConfig(
            netuid=1,
            price_threshold_tao=0,
            alerts=AlertConfig(),
        )
        reading = PriceReading(
            netuid=1,
            cost_tao=0.5,
            timestamp=datetime.now(timezone.utc),
        )
        event = build_alert_event(subnet, reading, Trend.STABLE)
        # Cost > 0 with threshold = 0 should be critical
        assert event.level == AlertLevel.CRITICAL

    def test_exact_threshold(self):
        from jarvis_miner.models import PriceReading

        subnet = SubnetConfig(
            netuid=1,
            price_threshold_tao=0.5,
            alerts=AlertConfig(),
        )
        reading = PriceReading(
            netuid=1,
            cost_tao=0.5,
            timestamp=datetime.now(timezone.utc),
        )
        event = build_alert_event(subnet, reading, Trend.STABLE)
        assert event.level == AlertLevel.OK  # exactly at threshold = good
