"""Tests for monitor — adaptive polling, interval computation, alert logic."""

from datetime import datetime, timezone
from pathlib import Path

from jarvis_miner.models import (
    AlertConfig,
    AlertLevel,
    DiscordConfig,
    GlobalConfig,
    PriceReading,
    SubnetConfig,
    Trend,
)
from jarvis_miner.monitor import Monitor

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_subnet(netuid=13, threshold=0.5, adaptive=True, **kwargs) -> SubnetConfig:
    return SubnetConfig(
        netuid=netuid,
        price_threshold_tao=threshold,
        alerts=AlertConfig(discord=DiscordConfig(webhook_url="https://test")),
        adaptive_polling=adaptive,
        min_poll_interval_seconds=60,
        poll_interval_seconds=300,
        **kwargs,
    )


def _make_monitor(subnets: list[SubnetConfig] | None = None) -> Monitor:
    global_cfg = GlobalConfig(data_dir=Path("/tmp/test"))
    if subnets is None:
        subnets = [_make_subnet()]
    return Monitor(global_cfg, subnets)


# ── Adaptive polling ─────────────────────────────────────────────────────


class TestAdaptivePolling:
    def test_no_history_uses_default(self):
        monitor = _make_monitor()
        interval = monitor._compute_interval(monitor.subnets[0])
        assert interval == 300  # default poll_interval

    def test_near_threshold_uses_fast_interval(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        # Add price near threshold
        history = monitor.state.get_history(subnet.netuid)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.6,  # within 1.5x of 0.5 threshold
                timestamp=datetime.now(timezone.utc),
            )
        )
        interval = monitor._compute_interval(subnet)
        assert interval == 60  # min_poll_interval

    def test_far_from_threshold_uses_default(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        history = monitor.state.get_history(subnet.netuid)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=2.0,  # far above 1.5x threshold
                timestamp=datetime.now(timezone.utc),
            )
        )
        interval = monitor._compute_interval(subnet)
        assert interval == 300

    def test_adaptive_disabled(self):
        monitor = _make_monitor([_make_subnet(adaptive=False)])
        subnet = monitor.subnets[0]
        history = monitor.state.get_history(subnet.netuid)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.5,
                timestamp=datetime.now(timezone.utc),
            )
        )
        interval = monitor._compute_interval(subnet)
        assert interval == 300  # always default when adaptive off

    def test_below_threshold_is_near(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        history = monitor.state.get_history(subnet.netuid)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.3,  # below threshold
                timestamp=datetime.now(timezone.utc),
            )
        )
        interval = monitor._compute_interval(subnet)
        assert interval == 60  # fast polling


# ── Should alert logic ───────────────────────────────────────────────────


class TestShouldAlert:
    def test_below_threshold_should_alert(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        reading = PriceReading(
            netuid=13,
            cost_tao=0.4,
            timestamp=datetime.now(timezone.utc),
        )
        assert monitor._should_alert(subnet, reading, Trend.STABLE) is True

    def test_above_threshold_no_alert(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        reading = PriceReading(
            netuid=13,
            cost_tao=0.6,
            timestamp=datetime.now(timezone.utc),
        )
        assert monitor._should_alert(subnet, reading, Trend.STABLE) is False

    def test_critical_price_always_alerts(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        reading = PriceReading(
            netuid=13,
            cost_tao=2.0,  # 4x threshold
            timestamp=datetime.now(timezone.utc),
        )
        assert monitor._should_alert(subnet, reading, Trend.STABLE) is True

    def test_cooldown_prevents_alert(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        now = datetime.now(timezone.utc)
        # Set recent alert time
        monitor.state.last_alert_time[13] = now
        reading = PriceReading(
            netuid=13,
            cost_tao=0.3,
            timestamp=now,
        )
        assert monitor._should_alert(subnet, reading, Trend.STABLE) is False

    def test_cooldown_expired_allows_alert(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        from datetime import timedelta

        old_time = datetime.now(timezone.utc) - timedelta(seconds=1000)
        monitor.state.last_alert_time[13] = old_time
        reading = PriceReading(
            netuid=13,
            cost_tao=0.3,
            timestamp=datetime.now(timezone.utc),
        )
        assert monitor._should_alert(subnet, reading, Trend.STABLE) is True

    def test_trend_change_triggers_alert(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        # Add 2 readings to history so len > 1
        history = monitor.state.get_history(13)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.6,
                timestamp=datetime.now(timezone.utc),
                trend=Trend.FALLING,
            )
        )
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.58,
                timestamp=datetime.now(timezone.utc),
                trend=Trend.FALLING,
            )
        )
        reading = PriceReading(
            netuid=13,
            cost_tao=0.55,
            timestamp=datetime.now(timezone.utc),
        )
        # Previous trend was FALLING, new is RISING — should alert
        assert monitor._should_alert(subnet, reading, Trend.RISING) is True

    def test_same_trend_no_extra_alert(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        history = monitor.state.get_history(13)
        history.add(
            PriceReading(
                netuid=13,
                cost_tao=0.6,
                timestamp=datetime.now(timezone.utc),
                trend=Trend.STABLE,
            )
        )
        reading = PriceReading(
            netuid=13,
            cost_tao=0.58,
            timestamp=datetime.now(timezone.utc),
        )
        # Same trend, price above threshold
        assert monitor._should_alert(subnet, reading, Trend.STABLE) is False


# ── Threshold event building ─────────────────────────────────────────────


class TestBuildThresholdEvent:
    def test_excellent(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        from jarvis_miner.models import PriceReading

        reading = PriceReading(netuid=13, cost_tao=0.2, timestamp=datetime.now(timezone.utc))
        event = monitor._build_threshold_event(subnet, reading, Trend.STABLE)
        assert event.level == AlertLevel.OK
        assert "Very Low" in event.title

    def test_good(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        reading = PriceReading(netuid=13, cost_tao=0.4, timestamp=datetime.now(timezone.utc))
        event = monitor._build_threshold_event(subnet, reading, Trend.FALLING)
        assert event.level == AlertLevel.OK
        assert "Below Threshold" in event.title

    def test_warning(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        reading = PriceReading(netuid=13, cost_tao=0.8, timestamp=datetime.now(timezone.utc))
        event = monitor._build_threshold_event(subnet, reading, Trend.RISING)
        assert event.level == AlertLevel.WARNING

    def test_critical(self):
        monitor = _make_monitor()
        subnet = monitor.subnets[0]
        reading = PriceReading(netuid=13, cost_tao=2.0, timestamp=datetime.now(timezone.utc))
        event = monitor._build_threshold_event(subnet, reading, Trend.RISING)
        assert event.level == AlertLevel.CRITICAL


# ── Monitor state integration ────────────────────────────────────────────


class TestMonitorStateIntegration:
    def test_poll_count_tracking(self):
        monitor = _make_monitor()
        monitor.state.poll_counts[13] = 0
        monitor.state.poll_counts[13] += 1
        assert monitor.state.poll_counts[13] == 1

    def test_disabled_subnets_excluded(self):
        subnets = [
            _make_subnet(netuid=13),
            _make_subnet(netuid=6, enabled=False),
        ]
        monitor = _make_monitor(subnets)
        assert len(monitor.subnets) == 1
        assert monitor.subnets[0].netuid == 13

    def test_multiple_subnets(self):
        subnets = [
            _make_subnet(netuid=13),
            _make_subnet(netuid=6),
            _make_subnet(netuid=9),
        ]
        monitor = _make_monitor(subnets)
        assert len(monitor.subnets) == 3
