"""Deregistration monitor — tracks hotkeys and alerts on deregistration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from .alerter import send_alert
from .fetcher import get_metagraph_hotkeys, get_wallet_hotkey_ss58
from .models import (
    AlertEvent,
    AlertLevel,
    DeregisterEntry,
    DeregisterEvent,
    GlobalConfig,
    SubnetConfig,
    Trend,
)

logger = logging.getLogger(__name__)


class DeregisterMonitor:
    """Monitors hotkeys on subnets and alerts when deregistration is detected."""

    def __init__(
        self,
        global_cfg: GlobalConfig,
        subnets: list[SubnetConfig],
    ):
        self.global_cfg = global_cfg
        self.subnets = self._prepare_subnets(subnets)
        self._stop_event = asyncio.Event()
        self._session: aiohttp.ClientSession | None = None
        # Track which hotkeys were known to be registered
        # {netuid: {hotkey_ss58: was_registered}}
        self._registered: dict[int, dict[str, bool]] = {}
        self._first_check: dict[int, bool] = {}
        self.last_status: dict[int, dict[str, bool]] = {}
        self.last_checked_at: dict[int, datetime] = {}
        self.last_error: dict[int, str] = {}

    def _prepare_subnets(self, subnets: list[SubnetConfig]) -> list[SubnetConfig]:
        """Attach Jarvis wallet deregister tracking to auto-register subnets."""
        tracked = [s for s in subnets if s.enabled]
        if not tracked:
            return []

        try:
            wallet_hotkey = get_wallet_hotkey_ss58(self.global_cfg.wallet)
        except Exception:
            wallet_hotkey = None

        prepared: list[SubnetConfig] = []
        for subnet in tracked:
            entries = list(subnet.deregister_entries)
            if subnet.auto_register and wallet_hotkey and not entries:
                entries.append(
                    DeregisterEntry(
                        hotkey_ss58=wallet_hotkey,
                        label=f"{self.global_cfg.wallet.name}/{self.global_cfg.wallet.hotkey}",
                    )
                )
            if entries:
                subnet.deregister_entries = entries
                prepared.append(subnet)
        return prepared

    @property
    def has_entries(self) -> bool:
        return len(self.subnets) > 0

    async def start(self) -> None:
        """Start the deregistration monitoring loop."""
        if not self.has_entries:
            logger.info("No deregister entries configured, skipping deregister monitor")
            return
        try:
            await self._run()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        except Exception:
            logger.exception("Deregister monitor failed with exception")

    async def _run(self) -> None:
        self._session = aiohttp.ClientSession()

        total_entries = sum(len(s.deregister_entries) for s in self.subnets)
        logger.info(
            f"Starting deregister monitor — {total_entries} hotkey(s) "
            f"across {len(self.subnets)} subnet(s)"
        )

        # Initialize tracking state
        for subnet in self.subnets:
            self._registered[subnet.netuid] = {}
            self._first_check[subnet.netuid] = True

        while not self._stop_event.is_set():
            for subnet in self.subnets:
                if self._stop_event.is_set():
                    break
                try:
                    await self._check_subnet(subnet)
                except Exception:
                    self.last_error[subnet.netuid] = "deregister_check_failed"
                    logger.exception(f"[{subnet.label}] Deregister check failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=120)
                break
            except asyncio.TimeoutError:
                pass

        if self._session:
            await self._session.close()
        logger.info("Deregister monitor stopped.")

    def stop(self) -> None:
        self._stop_event.set()

    async def _check_subnet(self, subnet: SubnetConfig) -> None:
        """Check all tracked hotkeys on a subnet for deregistration."""
        hotkeys_on_chain = await get_metagraph_hotkeys(
            subnet.netuid,
            self.global_cfg.subtensor_network,
            self.global_cfg.subtensor_endpoint,
        )
        hotkeys_set = set(hotkeys_on_chain)
        self.last_status[subnet.netuid] = {}

        for entry in subnet.deregister_entries:
            is_registered = entry.hotkey_ss58 in hotkeys_set
            was_registered = self._registered[subnet.netuid].get(entry.hotkey_ss58, True)
            self.last_status[subnet.netuid][entry.hotkey_ss58] = is_registered

            if self._first_check[subnet.netuid]:
                # On first check, just record the state
                self._registered[subnet.netuid][entry.hotkey_ss58] = is_registered
                if not is_registered:
                    logger.warning(
                        f"[{subnet.label}] {entry.display_name} is NOT registered "
                        f"on SN{subnet.netuid}"
                    )
                continue

            # Detect deregistration (was registered, now not)
            if was_registered and not is_registered:
                logger.warning(
                    f"[{subnet.label}] DEREGISTRATION DETECTED: "
                    f"{entry.display_name} ({entry.hotkey_ss58})"
                )
                event = DeregisterEvent(
                    netuid=subnet.netuid,
                    hotkey_ss58=entry.hotkey_ss58,
                    label=entry.label,
                )
                await self._send_deregister_alert(subnet, event)

            # Detect re-registration (was deregistered, now registered)
            if not was_registered and is_registered:
                logger.info(
                    f"[{subnet.label}] RE-REGISTRATION detected: "
                    f"{entry.display_name} ({entry.hotkey_ss58})"
                )

            self._registered[subnet.netuid][entry.hotkey_ss58] = is_registered

        self._first_check[subnet.netuid] = False
        self.last_checked_at[subnet.netuid] = datetime.now(timezone.utc)
        self.last_error.pop(subnet.netuid, None)

    async def _send_deregister_alert(self, subnet: SubnetConfig, event: DeregisterEvent) -> None:
        """Send a deregistration alert."""
        alert = AlertEvent(
            netuid=subnet.netuid,
            level=AlertLevel.DEREGISTERED,
            title=f"Deregistration Detected — {subnet.label}",
            message=(
                f"Hotkey {event.display_name} was deregistered from "
                f"SN{subnet.netuid} ({subnet.label}).\n"
                f"Address: {event.hotkey_ss58}"
            ),
            cost_tao=0,
            threshold_tao=subnet.price_threshold_tao,
            trend=Trend.UNKNOWN,
            mention_role=(subnet.alerts.discord.mention_role if subnet.alerts.discord else None),
        )

        if self._session:
            results = await send_alert(alert, subnet, self.global_cfg, self._session)
            if any(results.values()):
                logger.info(
                    f"[{subnet.label}] Deregister alert sent for {event.display_name} ({results})"
                )

        # Write signal file
        if subnet.signal_file:
            from .alerter import write_signal

            sig_path = Path(subnet.signal_file).parent / f"dereg_sn{subnet.netuid}.json"
            write_signal(alert, sig_path)
