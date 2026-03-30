"""Alerting — Discord webhooks + Telegram bot, unified dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import aiohttp

from .models import (
    AlertChannel,
    AlertEvent,
    AlertLevel,
    GlobalConfig,
    SubnetConfig,
    Trend,
)

logger = logging.getLogger(__name__)


# ── Discord ──────────────────────────────────────────────────────────────


def _discord_payload(event: AlertEvent, global_cfg: GlobalConfig) -> dict:
    payload: dict = {
        "username": global_cfg.discord_username,
        "embeds": [event.to_discord_embed()],
    }
    if global_cfg.discord_avatar_url:
        payload["avatar_url"] = global_cfg.discord_avatar_url
    if event.mention_role and event.level in (
        AlertLevel.WARNING,
        AlertLevel.CRITICAL,
        AlertLevel.FLOOR,
    ):
        payload["content"] = f"<@&{event.mention_role}>"
    return payload


async def _send_discord(
    event: AlertEvent,
    webhook_url: str,
    global_cfg: GlobalConfig,
    session: aiohttp.ClientSession,
) -> bool:
    payload = _discord_payload(event, global_cfg)
    try:
        async with session.post(
            webhook_url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 429:
                data = await resp.json()
                retry_after = data.get("retry_after", 5)
                logger.warning(f"Discord rate limited, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                async with session.post(webhook_url, json=payload) as r2:
                    return r2.status in (200, 204)
            if resp.status not in (200, 204):
                text = await resp.text()
                logger.error(f"Discord webhook failed ({resp.status}): {text}")
                return False
            return True
    except asyncio.TimeoutError:
        logger.error("Discord webhook timed out")
        return False
    except Exception:
        logger.exception("Discord webhook error")
        return False


# ── Telegram ─────────────────────────────────────────────────────────────


async def _send_telegram(
    event: AlertEvent,
    bot_token: str,
    chat_id: str,
    parse_mode: str,
    session: aiohttp.ClientSession,
) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    text = event.to_telegram_text()
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 429:
                data = await resp.json()
                retry_after = data.get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Telegram rate limited, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                async with session.post(url, json=payload) as r2:
                    return r2.status == 200
            if resp.status != 200:
                text_resp = await resp.text()
                logger.error(f"Telegram API failed ({resp.status}): {text_resp}")
                return False
            return True
    except asyncio.TimeoutError:
        logger.error("Telegram API timed out")
        return False
    except Exception:
        logger.exception("Telegram API error")
        return False


# ── Unified dispatch ─────────────────────────────────────────────────────


async def send_alert(
    event: AlertEvent,
    subnet: SubnetConfig,
    global_cfg: GlobalConfig,
    session: aiohttp.ClientSession,
) -> dict[str, bool]:
    """Send alert to all configured channels. Returns {channel: success}."""
    results: dict[str, bool] = {}
    channel = subnet.alerts.channel

    if channel == AlertChannel.NONE:
        return results

    # Discord
    if channel in (AlertChannel.DISCORD, AlertChannel.BOTH):
        if subnet.alerts.discord:
            results["discord"] = await _send_discord(
                event,
                subnet.alerts.discord.webhook_url,
                global_cfg,
                session,
            )

    # Telegram
    if channel in (AlertChannel.TELEGRAM, AlertChannel.BOTH):
        if subnet.alerts.telegram:
            results["telegram"] = await _send_telegram(
                event,
                subnet.alerts.telegram.bot_token,
                subnet.alerts.telegram.chat_id,
                subnet.alerts.telegram.parse_mode,
                session,
            )

    return results


async def validate_webhooks(
    subnets: list[SubnetConfig],
    session: aiohttp.ClientSession,
) -> dict[int, dict[str, bool]]:
    """Validate that all configured webhooks are reachable.

    Returns {netuid: {channel: is_valid}}.
    """
    results: dict[int, dict[str, bool]] = {}

    for subnet in subnets:
        results[subnet.netuid] = {}

        # Test Discord webhook
        if subnet.alerts.discord:
            try:
                async with session.get(
                    subnet.alerts.discord.webhook_url,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    # Discord returns 405 for GET on valid webhooks
                    results[subnet.netuid]["discord"] = resp.status in (
                        200,
                        405,
                        401,
                    )
            except Exception:
                results[subnet.netuid]["discord"] = False

        # Test Telegram bot
        if subnet.alerts.telegram:
            try:
                url = f"https://api.telegram.org/bot{subnet.alerts.telegram.bot_token}/getMe"
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    data = await resp.json()
                    results[subnet.netuid]["telegram"] = data.get("ok", False)
            except Exception:
                results[subnet.netuid]["telegram"] = False

    return results


# ── Alert event builder ──────────────────────────────────────────────────


def build_alert_event(
    subnet: SubnetConfig,
    reading,
    trend: Trend,
) -> AlertEvent:
    """Determine alert level and build an AlertEvent based on price vs threshold."""
    cost = reading.cost_tao
    threshold = subnet.price_threshold_tao

    # Handle zero threshold edge case
    if threshold <= 0:
        level = AlertLevel.CRITICAL if cost > 0 else AlertLevel.OK
        title = f"Price Check \u2014 {subnet.label}"
        msg = f"Registration cost is {cost:.4f} TAO."
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


# ── Signal file writer (R-02 integration) ────────────────────────────────


def write_signal(event: AlertEvent, signal_path: Path) -> None:
    """Write a signal file for R-02 to consume."""
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal_path.write_text(json.dumps(event.to_signal_dict(), indent=2))
    logger.info(f"Signal written: {signal_path}")
