"""Monitor engine — async loop with adaptive polling, floor detection, signals."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from .alerter import send_alert, write_signal
from .fetcher import burned_register_sdk, close_subtensor, fetch_burn_cost
from .models import (
    AlertEvent,
    AlertLevel,
    GlobalConfig,
    MonitorState,
    SubnetConfig,
    Trend,
)

logger = logging.getLogger(__name__)


class Monitor:
    """Core monitoring engine with adaptive polling and floor detection."""

    def __init__(
        self,
        global_cfg: GlobalConfig,
        subnets: list[SubnetConfig],
    ):
        self.global_cfg = global_cfg
        self.subnets = [s for s in subnets if s.enabled]
        self.state = MonitorState()
        self._stop_event = asyncio.Event()
        self._session: aiohttp.ClientSession | None = None
        self._tasks: list[asyncio.Task] = []
        self._bittensor_initialized = False
        self._bittensor_lock = asyncio.Lock()
        # Track subnets we've auto-registered on (avoid re-registering every cycle)
        self._registered_subnets: set[int] = set()

    @property
    def state_path(self) -> Path:
        return self.global_cfg.data_dir / "monitor_state.json"

    async def start(self) -> None:
        """Start the monitoring loop."""
        try:
            await self._run()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        except Exception:
            logger.exception("Monitor failed with exception")

    async def _run(self) -> None:
        """Internal run method."""
        self.state = MonitorState.load(self.state_path)
        self.state.started_at = datetime.now(timezone.utc)
        self._session = aiohttp.ClientSession()

        logger.info(
            f"Starting monitor \u2014 {len(self.subnets)} subnet(s), "
            f"network={self.global_cfg.subtensor_network}"
        )

        # Create poll tasks for each subnet - don't pre-init
        # The first poll will handle bittensor initialization
        for subnet in self.subnets:
            self.state.poll_counts[subnet.netuid] = 0
            task = asyncio.create_task(
                self._poll_loop(subnet),
                name=f"monitor-sn{subnet.netuid}",
            )
            self._tasks.append(task)

        self._tasks.append(asyncio.create_task(self._save_loop(), name="state-save"))

        await self._stop_event.wait()

        logger.info("Shutting down monitor...")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.state.save(self.state_path)
        close_subtensor()
        if self._session:
            await self._session.close()
        logger.info("Monitor stopped.")

    def stop(self) -> None:
        self._stop_event.set()

    # ── Polling ──────────────────────────────────────────────────────────

    async def _poll_loop(self, subnet: SubnetConfig) -> None:
        label = subnet.label
        logger.info(
            f"[{label}] Polling every {subnet.poll_interval_seconds}s "
            f"(adaptive={subnet.adaptive_polling})"
        )

        while not self._stop_event.is_set():
            interval = self._compute_interval(subnet)

            try:
                await self._poll_subnet(subnet)
            except ImportError as e:
                logger.error(f"[{label}] {e}")
                logger.error("Install bittensor: uv pip install bittensor")
                self.stop()
                return
            except Exception:
                logger.exception(f"[{label}] Poll cycle failed")
                logger.error(f"[{label}] Will retry in {subnet.poll_interval_seconds}s")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

    def _compute_interval(self, subnet: SubnetConfig) -> int:
        """Compute adaptive polling interval."""
        if not subnet.adaptive_polling:
            return subnet.poll_interval_seconds

        history = self.state.get_history(subnet.netuid)
        if not history.readings:
            return subnet.poll_interval_seconds

        last_price = history.readings[-1].cost_tao
        threshold = subnet.price_threshold_tao

        # If price is within the "near threshold" zone, poll faster
        if last_price <= threshold * subnet.near_threshold_multiplier:
            return subnet.min_poll_interval_seconds

        return subnet.poll_interval_seconds

    async def _poll_subnet(self, subnet: SubnetConfig) -> None:
        """Execute one poll cycle for a subnet."""
        label = subnet.label

        # Log bittensor initialization on first poll
        if not self._bittensor_initialized:
            logger.info("Initializing bittensor connection (first poll may take ~15s)...")
            self._bittensor_initialized = True

        # Run bittensor SDK in a thread to avoid blocking the event loop
        # This is necessary because bittensor uses synchronous websocket calls
        # Use lock to prevent concurrent websocket recv errors
        async with self._bittensor_lock:
            reading = await fetch_burn_cost(
                subnet,
                self.global_cfg.subtensor_network,
                self.global_cfg.subtensor_endpoint,
                self.global_cfg.taostats_api_key,
                source=self.global_cfg.price_source,
                session=self._session,
            )

        # Update state
        history = self.state.get_history(subnet.netuid)
        history.add(reading)
        self.state.poll_counts[subnet.netuid] = self.state.poll_counts.get(subnet.netuid, 0) + 1

        trend = history.compute_trend(self.global_cfg.trend_window)
        reading.trend = trend

        logger.info(
            f"[{label}] {reading.cost_tao:.6f} TAO | "
            f"threshold={subnet.price_threshold_tao:.6f} | "
            f"trend={trend.value} | source={reading.source}"
        )

        # Check threshold alerts
        if self._should_alert(subnet, reading, trend):
            await self._handle_threshold_alert(subnet, reading, trend)

        # Check floor detection
        if subnet.floor_detection:
            await self._check_floor(subnet)

    # ── Threshold alerts ─────────────────────────────────────────────────

    def _should_alert(self, subnet: SubnetConfig, reading, trend: Trend) -> bool:
        last_alert = self.state.last_alert_time.get(subnet.netuid)
        if last_alert:
            elapsed = (reading.timestamp - last_alert).total_seconds()
            if elapsed < self.global_cfg.alert_cooldown_seconds:
                return False

        if reading.cost_tao <= subnet.price_threshold_tao:
            return True
        if reading.cost_tao >= subnet.price_threshold_tao * 3:
            return True

        history = self.state.get_history(subnet.netuid)
        if len(history.readings) > 1:
            prev_trend = history.readings[-2].trend
            if prev_trend != trend and trend != Trend.UNKNOWN:
                return True

        return False

    async def _handle_threshold_alert(self, subnet: SubnetConfig, reading, trend: Trend) -> None:
        event = self._build_threshold_event(subnet, reading, trend)

        # Send alerts
        if self._session and event.level in (AlertLevel.OK, AlertLevel.CRITICAL):
            results = await send_alert(event, subnet, self.global_cfg, self._session)
            if any(results.values()):
                self.state.last_alert_time[subnet.netuid] = reading.timestamp
                logger.info(f"[{subnet.label}] Alert sent: {event.title} ({results})")

        # Write signal file
        if subnet.signal_file:
            write_signal(event, Path(subnet.signal_file))

        # Auto-registration: if price is below threshold and auto_register is enabled
        if (
            subnet.auto_register
            and reading.cost_tao <= subnet.price_threshold_tao
            and subnet.netuid not in self._registered_subnets
        ):
            await self._try_auto_register(subnet, reading)

    def _build_threshold_event(self, subnet: SubnetConfig, reading, trend: Trend) -> AlertEvent:
        cost = reading.cost_tao
        threshold = subnet.price_threshold_tao

        if cost <= threshold * 0.5:
            level = AlertLevel.OK
            title = f"Price Very Low \u2014 {subnet.label}"
            msg = (
                f"Registration cost is {cost:.4f} TAO \u2014 well below your "
                f"threshold of {threshold:.4f} TAO. Excellent window!"
            )
        elif cost <= threshold:
            level = AlertLevel.OK
            title = f"Price Below Threshold \u2014 {subnet.label}"
            msg = (
                f"Registration cost is {cost:.4f} TAO \u2014 within your "
                f"threshold of {threshold:.4f} TAO. Good time to register."
            )
        elif cost <= threshold * 1.5:
            level = AlertLevel.INFO
            title = f"Price Near Threshold \u2014 {subnet.label}"
            msg = (
                f"Registration cost is {cost:.4f} TAO \u2014 approaching your "
                f"threshold of {threshold:.4f} TAO. Trend: {trend.value}."
            )
        elif cost <= threshold * 3:
            level = AlertLevel.WARNING
            title = f"Price Elevated \u2014 {subnet.label}"
            msg = (
                f"Registration cost is {cost:.4f} TAO \u2014 "
                f"{cost / threshold:.1f}x your threshold. Consider waiting."
            )
        else:
            level = AlertLevel.CRITICAL
            title = f"Price Very High \u2014 {subnet.label}"
            msg = (
                f"Registration cost is {cost:.4f} TAO \u2014 "
                f"{cost / threshold:.1f}x your threshold. Do NOT register."
            )

        return AlertEvent(
            netuid=subnet.netuid,
            level=level,
            title=title,
            message=msg,
            cost_tao=cost,
            threshold_tao=threshold,
            trend=trend,
            mention_role=subnet.alerts.discord.mention_role if subnet.alerts.discord else None,
        )

    # ── Auto-registration ─────────────────────────────────────────────────

    async def _try_auto_register(self, subnet: SubnetConfig, reading) -> None:
        """Attempt auto-registration when price is below threshold."""
        wallet = self.global_cfg.wallet
        label = subnet.label

        logger.info(
            f"[{label}] Price {reading.cost_tao:.6f} TAO <= threshold "
            f"{subnet.price_threshold_tao:.6f} TAO — attempting auto-register "
            f"with wallet={wallet.name}, hotkey={wallet.hotkey}"
        )

        try:
            async with self._bittensor_lock:
                result = await asyncio.to_thread(
                    burned_register_sdk,
                    subnet.netuid,
                    wallet,
                    self.global_cfg.subtensor_network,
                    self.global_cfg.subtensor_endpoint,
                )

            if result.error == "already_registered":
                logger.info(
                    f"[{label}] Wallet {result.hotkey[:12]}... "
                    f"already registered on SN{subnet.netuid}"
                )
                self._registered_subnets.add(subnet.netuid)
                return

            if result.success:
                logger.info(
                    f"[{label}] AUTO-REGISTERED on SN{subnet.netuid}! "
                    f"Cost: {result.cost_tao:.6f} TAO, Hotkey: {result.hotkey[:12]}..."
                )
                self._registered_subnets.add(subnet.netuid)

                # Send registration success alert
                reg_event = AlertEvent(
                    netuid=subnet.netuid,
                    level=AlertLevel.REGISTERED,
                    title=f"Auto-Registered — {subnet.label}",
                    message=(
                        f"Successfully registered on SN{subnet.netuid} ({subnet.label}) "
                        f"at {result.cost_tao:.6f} TAO.\n"
                        f"Hotkey: {result.hotkey}"
                    ),
                    cost_tao=result.cost_tao,
                    threshold_tao=subnet.price_threshold_tao,
                    trend=Trend.UNKNOWN,
                    mention_role=(
                        subnet.alerts.discord.mention_role if subnet.alerts.discord else None
                    ),
                )

                if self._session:
                    await send_alert(reg_event, subnet, self.global_cfg, self._session)

                if subnet.signal_file:
                    sig_path = Path(subnet.signal_file).parent / f"reg_sn{subnet.netuid}.json"
                    write_signal(reg_event, sig_path)
            else:
                logger.error(
                    f"[{label}] Auto-registration FAILED on SN{subnet.netuid}: {result.error}"
                )
        except Exception:
            logger.exception(f"[{label}] Auto-registration error on SN{subnet.netuid}")

    # ── Floor detection ──────────────────────────────────────────────────

    async def _check_floor(self, subnet: SubnetConfig) -> None:
        history = self.state.get_history(subnet.netuid)
        floor = history.detect_floor(subnet.floor_window)

        if floor is None:
            return

        # Check cooldown for floor alerts
        last_floor_alert = self.state.last_floor_alert_time.get(subnet.netuid)
        if last_floor_alert:
            elapsed = (datetime.now(timezone.utc) - last_floor_alert).total_seconds()
            if elapsed < self.global_cfg.alert_cooldown_seconds:
                return

        trend = history.compute_trend(self.global_cfg.trend_window)

        event = AlertEvent(
            netuid=subnet.netuid,
            level=AlertLevel.FLOOR,
            title=f"Price Floor Detected \u2014 {subnet.label}",
            message=(
                f"Price bottomed at {floor.floor_price:.4f} TAO and is now "
                f"rising (+{floor.current_rise_pct:.1f}%). This may be your "
                f"best window to register!"
            ),
            cost_tao=floor.floor_price,
            threshold_tao=subnet.price_threshold_tao,
            trend=trend,
            mention_role=(subnet.alerts.discord.mention_role if subnet.alerts.discord else None),
            floor_event=floor,
        )

        history.detected_floors.append(floor)

        if self._session:
            results = await send_alert(event, subnet, self.global_cfg, self._session)
            if any(results.values()):
                self.state.last_floor_alert_time[subnet.netuid] = datetime.now(timezone.utc)
                logger.info(
                    f"[{subnet.label}] Floor alert sent: {floor.floor_price:.4f} TAO ({results})"
                )

        if subnet.signal_file:
            write_signal(event, Path(subnet.signal_file))

    # ── State persistence ────────────────────────────────────────────────

    async def _save_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)
                break
            except asyncio.TimeoutError:
                self.state.save(self.state_path)
