"""Data models for the Jarvis Miner CLI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class Trend(Enum):
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    INFO = "info"
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    FLOOR = "floor"  # price floor detected
    REGISTERED = "registered"  # auto-registration succeeded
    DEREGISTERED = "deregistered"  # deregistration detected


class AlertChannel(Enum):
    DISCORD = "discord"
    TELEGRAM = "telegram"
    BOTH = "both"
    NONE = "none"


@dataclass
class DiscordConfig:
    """Discord webhook settings."""

    webhook_url: str
    mention_role: str | None = None


@dataclass
class TelegramConfig:
    """Telegram bot settings."""

    bot_token: str
    chat_id: str
    parse_mode: str = "HTML"


@dataclass
class AlertConfig:
    """Alert routing for a subnet."""

    discord: DiscordConfig | None = None
    telegram: TelegramConfig | None = None
    channel: AlertChannel = AlertChannel.BOTH

    @property
    def has_any(self) -> bool:
        return self.discord is not None or self.telegram is not None


@dataclass
class SubnetConfig:
    """Configuration for a single subnet to monitor."""

    netuid: int
    price_threshold_tao: float
    alerts: AlertConfig
    poll_interval_seconds: int = 300
    min_poll_interval_seconds: int = 60  # fastest poll when adaptive
    max_spend_tao: float | None = None
    auto_register: bool = False
    enabled: bool = True
    nickname: str | None = None
    # Floor detection
    floor_detection: bool = True
    floor_window: int = 6  # readings to detect a floor
    # Adaptive polling
    adaptive_polling: bool = True
    near_threshold_multiplier: float = 1.5  # poll faster within this range
    # Signal file for R-02 integration
    signal_file: str | None = None  # e.g. "data/signals/sn13.json"
    # Deregistration monitoring
    deregister_entries: list[DeregisterEntry] = field(default_factory=list)

    def __post_init__(self):
        if self.netuid < 0:
            raise ValueError(f"netuid must be >= 0, got {self.netuid}")
        if self.price_threshold_tao < 0:
            raise ValueError(f"price_threshold_tao must be >= 0, got {self.price_threshold_tao}")
        if self.poll_interval_seconds < 30:
            raise ValueError("poll_interval_seconds must be >= 30")
        if self.min_poll_interval_seconds < 15:
            raise ValueError("min_poll_interval_seconds must be >= 15")
        if self.max_spend_tao is not None and self.max_spend_tao < 0:
            raise ValueError(f"max_spend_tao must be >= 0, got {self.max_spend_tao}")

    @property
    def label(self) -> str:
        return self.nickname or f"Subnet {self.netuid}"


# ── Wallet & Auto-Registration ──────────────────────────────────────────


@dataclass
class WalletConfig:
    """Bittensor wallet settings for auto-registration."""

    name: str = "default"
    hotkey: str = "default"
    path: str = "~/.bittensor/wallets"

    @property
    def wallet_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass
class GlobalConfig:
    """Global configuration for the monitor."""

    subtensor_network: str = "finney"
    subtensor_endpoint: str | None = None
    taostats_api_key: str | None = None  # for API fallback
    data_dir: Path = Path("data")
    log_level: str = "INFO"
    max_history_days: int = 30
    trend_window: int = 6
    discord_username: str = "Jarvis Miner"
    discord_avatar_url: str = ""
    # Alert cooldown
    alert_cooldown_seconds: int = 600
    # Price source preference
    price_source: str = "sdk"  # "sdk", "api", "auto" (auto = sdk first, api fallback)
    # Wallet for auto-registration
    wallet: WalletConfig = field(default_factory=WalletConfig)

    def __post_init__(self):
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        if self.trend_window < 3:
            raise ValueError("trend_window must be >= 3")


@dataclass
class PriceReading:
    """A single price observation."""

    netuid: int
    cost_tao: float
    timestamp: datetime
    trend: Trend = Trend.UNKNOWN
    source: str = "sdk"  # "sdk" or "api"

    def to_dict(self) -> dict:
        return {
            "netuid": self.netuid,
            "cost_tao": self.cost_tao,
            "timestamp": self.timestamp.isoformat(),
            "trend": self.trend.value,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PriceReading:
        return cls(
            netuid=data["netuid"],
            cost_tao=data["cost_tao"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            trend=Trend(data.get("trend", "unknown")),
            source=data.get("source", "sdk"),
        )


@dataclass
class FloorEvent:
    """Detected price floor event."""

    netuid: int
    floor_price: float
    timestamp: datetime
    readings_before: int  # how many readings of decline before floor
    current_rise_pct: float  # how much price rose from floor

    def to_dict(self) -> dict:
        return {
            "netuid": self.netuid,
            "floor_price": self.floor_price,
            "timestamp": self.timestamp.isoformat(),
            "readings_before": self.readings_before,
            "current_rise_pct": self.current_rise_pct,
        }


@dataclass
class PriceHistory:
    """Persistent price history for a subnet."""

    netuid: int
    readings: list[PriceReading] = field(default_factory=list)
    detected_floors: list[FloorEvent] = field(default_factory=list)

    def add(self, reading: PriceReading) -> None:
        self.readings.append(reading)

    def recent(self, n: int) -> list[PriceReading]:
        return self.readings[-n:]

    def compute_trend(self, window: int) -> Trend:
        """Compute price trend over the last `window` readings."""
        recent = self.recent(window)
        if len(recent) < 3:
            return Trend.UNKNOWN

        prices = [r.cost_tao for r in recent]
        mid = len(prices) // 2
        first_half = sum(prices[:mid]) / mid
        second_half = sum(prices[mid:]) / (len(prices) - mid)

        pct_change = ((second_half - first_half) / first_half) * 100 if first_half > 0 else 0

        if pct_change > 5:
            return Trend.RISING
        elif pct_change < -5:
            return Trend.FALLING
        return Trend.STABLE

    def detect_floor(self, window: int) -> FloorEvent | None:
        """Detect if a price floor just occurred.

        A floor is detected when:
        - Price declined for N-1 consecutive readings
        - The last reading is higher than the minimum
        - The minimum is within a reasonable range (not 0)
        """
        if len(self.readings) < window:
            return None

        recent = self.recent(window)
        prices = [r.cost_tao for r in recent]

        # Find the minimum price index
        min_idx = prices.index(min(prices))

        # Floor is valid only if:
        # 1. Minimum is not at the edges (it's a local min)
        # 2. Price is now rising after the minimum
        if min_idx == 0 or min_idx == len(prices) - 1:
            return None

        # Check if prices declined before the min
        declined_before = all(prices[i] >= prices[i + 1] for i in range(0, min_idx))

        # Check if prices rose after the min
        rose_after = all(prices[i] <= prices[i + 1] for i in range(min_idx, len(prices) - 1))

        if not (declined_before and rose_after):
            return None

        floor_price = prices[min_idx]
        current_price = prices[-1]
        rise_pct = ((current_price - floor_price) / floor_price) * 100 if floor_price > 0 else 0

        # Only report if price is still close to floor (< 10% above)
        if rise_pct > 10:
            return None

        return FloorEvent(
            netuid=self.netuid,
            floor_price=floor_price,
            timestamp=recent[min_idx].timestamp,
            readings_before=min_idx,
            current_rise_pct=rise_pct,
        )

    def min_price(self) -> float | None:
        """Return the lowest price ever recorded."""
        if not self.readings:
            return None
        return min(r.cost_tao for r in self.readings)

    def max_price(self) -> float | None:
        """Return the highest price ever recorded."""
        if not self.readings:
            return None
        return max(r.cost_tao for r in self.readings)

    def avg_price(self, last_n: int = 0) -> float | None:
        """Return average price over last N readings (or all if 0)."""
        readings = self.recent(last_n) if last_n > 0 else self.readings
        if not readings:
            return None
        return sum(r.cost_tao for r in readings) / len(readings)

    def sparkline(self, width: int = 30) -> str:
        """Generate an ASCII sparkline of recent prices."""
        if len(self.readings) < 2:
            return "─" * width

        readings = self.recent(width)
        prices = [r.cost_tao for r in readings]

        if len(set(prices)) == 1:
            return "─" * len(prices)

        min_p = min(prices)
        max_p = max(prices)
        chars = " ▁▂▃▄▅▆▇█"

        result = []
        for p in prices:
            if max_p == min_p:
                idx = 4
            else:
                idx = int((p - min_p) / (max_p - min_p) * (len(chars) - 1))
            result.append(chars[idx])

        return "".join(result)

    def to_dict(self) -> dict:
        return {
            "netuid": self.netuid,
            "readings": [r.to_dict() for r in self.readings],
            "detected_floors": [f.to_dict() for f in self.detected_floors],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PriceHistory:
        floors = []
        for f in data.get("detected_floors", []):
            floors.append(
                FloorEvent(
                    netuid=f["netuid"],
                    floor_price=f["floor_price"],
                    timestamp=datetime.fromisoformat(f["timestamp"]),
                    readings_before=f["readings_before"],
                    current_rise_pct=f["current_rise_pct"],
                )
            )
        return cls(
            netuid=data["netuid"],
            readings=[PriceReading.from_dict(r) for r in data.get("readings", [])],
            detected_floors=floors,
        )


@dataclass
class MonitorState:
    """Full state of the monitor across all subnets."""

    histories: dict[int, PriceHistory] = field(default_factory=dict)
    last_alert_time: dict[int, datetime] = field(default_factory=dict)
    last_floor_alert_time: dict[int, datetime] = field(default_factory=dict)
    started_at: datetime | None = None
    poll_counts: dict[int, int] = field(default_factory=dict)

    def get_history(self, netuid: int) -> PriceHistory:
        if netuid not in self.histories:
            self.histories[netuid] = PriceHistory(netuid=netuid)
        return self.histories[netuid]

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "histories": {str(k): v.to_dict() for k, v in self.histories.items()},
            "last_alert_time": {str(k): v.isoformat() for k, v in self.last_alert_time.items()},
            "last_floor_alert_time": {
                str(k): v.isoformat() for k, v in self.last_floor_alert_time.items()
            },
            "poll_counts": {str(k): v for k, v in self.poll_counts.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> MonitorState:
        return cls(
            histories={
                int(k): PriceHistory.from_dict(v) for k, v in data.get("histories", {}).items()
            },
            last_alert_time={
                int(k): datetime.fromisoformat(v)
                for k, v in data.get("last_alert_time", {}).items()
            },
            last_floor_alert_time={
                int(k): datetime.fromisoformat(v)
                for k, v in data.get("last_floor_alert_time", {}).items()
            },
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            poll_counts={int(k): v for k, v in data.get("poll_counts", {}).items()},
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> MonitorState:
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))


@dataclass
class AlertEvent:
    """An alert to be dispatched."""

    netuid: int
    level: AlertLevel
    title: str
    message: str
    cost_tao: float
    threshold_tao: float
    trend: Trend
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    mention_role: str | None = None
    floor_event: FloorEvent | None = None

    @property
    def color(self) -> int:
        return {
            AlertLevel.OK: 0x2ECC71,
            AlertLevel.INFO: 0x3498DB,
            AlertLevel.WARNING: 0xF39C12,
            AlertLevel.CRITICAL: 0xE74C3C,
            AlertLevel.FLOOR: 0x9B59B6,
            AlertLevel.REGISTERED: 0x27AE60,
            AlertLevel.DEREGISTERED: 0xE67E22,
        }[self.level]

    @property
    def emoji(self) -> str:
        return {
            AlertLevel.OK: "\U0001f7e2",
            AlertLevel.INFO: "\U0001f535",
            AlertLevel.WARNING: "\U0001f7e0",
            AlertLevel.CRITICAL: "\U0001f534",
            AlertLevel.FLOOR: "\U0001f535",
            AlertLevel.REGISTERED: "\u2705",
            AlertLevel.DEREGISTERED: "\u26a0\ufe0f",
        }[self.level]

    @property
    def telegram_emoji(self) -> str:
        return {
            AlertLevel.OK: "\u2705",
            AlertLevel.INFO: "\U0001f4a1",
            AlertLevel.WARNING: "\u26a0\ufe0f",
            AlertLevel.CRITICAL: "\U0001f6a8",
            AlertLevel.FLOOR: "\U0001f48e",
            AlertLevel.REGISTERED: "\u2705",
            AlertLevel.DEREGISTERED: "\U0001f6a8",
        }[self.level]

    def to_discord_embed(self) -> dict:
        fields = [
            {"name": "Cost", "value": f"{self.cost_tao:.4f} TAO", "inline": True},
            {"name": "Threshold", "value": f"{self.threshold_tao:.4f} TAO", "inline": True},
            {"name": "Trend", "value": self.trend.value.capitalize(), "inline": True},
        ]
        if self.floor_event:
            fields.append(
                {
                    "name": "Floor Price",
                    "value": f"{self.floor_event.floor_price:.4f} TAO",
                    "inline": True,
                }
            )
            fields.append(
                {
                    "name": "Rise from Floor",
                    "value": f"+{self.floor_event.current_rise_pct:.1f}%",
                    "inline": True,
                }
            )
        return {
            "title": f"{self.emoji} {self.title}",
            "description": self.message,
            "color": self.color,
            "fields": fields,
            "timestamp": self.timestamp.isoformat(),
            "footer": {"text": "Jarvis Miner"},
        }

    def to_telegram_text(self) -> str:
        lines = [
            f"{self.telegram_emoji} <b>{self.title}</b>",
            "",
            self.message,
            "",
            f"\U0001f4b0 Cost: <b>{self.cost_tao:.4f} TAO</b>",
            f"\U0001f3af Threshold: {self.threshold_tao:.4f} TAO",
            f"\U0001f4c8 Trend: {self.trend.value.capitalize()}",
        ]
        if self.floor_event:
            lines.append(
                f"\U0001f48e Floor: {self.floor_event.floor_price:.4f} TAO "
                f"(+{self.floor_event.current_rise_pct:.1f}%)"
            )
        return "\n".join(lines)

    def to_signal_dict(self) -> dict:
        """Output for signal file (R-02 integration)."""
        return {
            "netuid": self.netuid,
            "level": self.level.value,
            "cost_tao": self.cost_tao,
            "threshold_tao": self.threshold_tao,
            "trend": self.trend.value,
            "timestamp": self.timestamp.isoformat(),
            "action": "register" if self.level in (AlertLevel.OK, AlertLevel.FLOOR) else "wait",
        }


# ── Registration Result ────────────────────────────────────────────────


@dataclass
class RegistrationResult:
    """Result of an auto-registration attempt."""

    netuid: int
    success: bool
    cost_tao: float
    hotkey: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    tx_hash: str | None = None

    def to_dict(self) -> dict:
        return {
            "netuid": self.netuid,
            "success": self.success,
            "cost_tao": self.cost_tao,
            "hotkey": self.hotkey,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "tx_hash": self.tx_hash,
        }


# ── Deregistration Monitoring ───────────────────────────────────────────


@dataclass
class DeregisterEntry:
    """A hotkey to monitor for deregistration on a subnet."""

    hotkey_ss58: str
    label: str | None = None  # friendly name

    @property
    def display_name(self) -> str:
        return self.label or f"{self.hotkey_ss58[:8]}...{self.hotkey_ss58[-4:]}"


@dataclass
class DeregisterEvent:
    """Detected deregistration event."""

    netuid: int
    hotkey_ss58: str
    label: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "netuid": self.netuid,
            "hotkey_ss58": self.hotkey_ss58,
            "label": self.label,
            "timestamp": self.timestamp.isoformat(),
        }
