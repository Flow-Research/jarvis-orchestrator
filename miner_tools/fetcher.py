"""Price fetcher — retrieves burn cost from bittensor SDK."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .models import PriceReading, RegistrationResult, SubnetConfig, WalletConfig

logger = logging.getLogger(__name__)

_subtensor_cache: dict[str, Any] = {}

BITTENSOR_INSTALL_MSG = (
    "bittensor SDK is required for price fetching.\nInstall with: uv pip install bittensor"
)


# ── Bittensor SDK ────────────────────────────────────────────────────────


def _import_bittensor():
    try:
        import bittensor as bt

        return bt
    except ImportError:
        raise ImportError(BITTENSOR_INSTALL_MSG)


def _get_subtensor(network: str = "finney", endpoint: str | None = None):
    """Get or create a cached subtensor connection."""
    bt = _import_bittensor()
    cache_key = endpoint or network
    if cache_key not in _subtensor_cache:
        if endpoint:
            _subtensor_cache[cache_key] = bt.Subtensor(network=endpoint)
        else:
            _subtensor_cache[cache_key] = bt.Subtensor(network=network)
    return _subtensor_cache[cache_key]


def fetch_burn_cost_sdk(
    subnet: SubnetConfig,
    network: str = "finney",
    endpoint: str | None = None,
) -> PriceReading:
    """Fetch burn cost via bittensor SDK.

    Uses the recycle() method (bittensor v10+).
    """
    subtensor = _get_subtensor(network, endpoint)
    burn_cost = subtensor.recycle(subnet.netuid)

    if burn_cost is None:
        raise RuntimeError(f"Could not get burn cost for subnet {subnet.netuid}")

    cost_tao = float(burn_cost.tao)

    return PriceReading(
        netuid=subnet.netuid,
        cost_tao=cost_tao,
        timestamp=datetime.now(timezone.utc),
        source="sdk",
    )


# ── Unified fetcher ──────────────────────────────────────────────────────


async def fetch_burn_cost(
    subnet: SubnetConfig,
    network: str = "finney",
    endpoint: str | None = None,
    api_key: str | None = None,
    source: str = "auto",
    session: aiohttp.ClientSession | None = None,
) -> PriceReading:
    """Fetch burn cost from bittensor SDK.

    Raises ImportError if bittensor is not installed.
    Raises RuntimeError if the chain query fails.
    """
    return await asyncio.to_thread(fetch_burn_cost_sdk, subnet, network, endpoint)


# ── Subnet info ──────────────────────────────────────────────────────────


def fetch_subnet_info(
    netuid: int,
    network: str = "finney",
    endpoint: str | None = None,
) -> dict:
    """Fetch extended subnet info from the chain.

    In bittensor v10+, uses DynamicInfo which has different attributes
    than the old SubnetInfo.
    """
    subtensor = _get_subtensor(network, endpoint)

    try:
        subnet_info = subtensor.subnet(netuid)
        if subnet_info is None:
            return {"netuid": netuid}

        result = {"netuid": netuid}

        # DynamicInfo attributes (bittensor v10+)
        if hasattr(subnet_info, "subnet_name"):
            result["name"] = subnet_info.subnet_name
        if hasattr(subnet_info, "tempo"):
            result["tempo"] = int(subnet_info.tempo)
        if hasattr(subnet_info, "price"):
            result["price"] = float(subnet_info.price.tao) if subnet_info.price else None
        if hasattr(subnet_info, "moving_price"):
            result["moving_price"] = float(subnet_info.moving_price)
        if hasattr(subnet_info, "owner_coldkey"):
            result["owner"] = str(subnet_info.owner_coldkey)
        if hasattr(subnet_info, "tao_in"):
            result["tao_in"] = float(subnet_info.tao_in.tao) if subnet_info.tao_in else None
        if hasattr(subnet_info, "alpha_in"):
            result["alpha_in"] = str(subnet_info.alpha_in)
        if hasattr(subnet_info, "emission"):
            result["emission"] = str(subnet_info.emission)
        if hasattr(subnet_info, "symbol"):
            result["symbol"] = subnet_info.symbol

        # Recycle/burn cost
        try:
            burn = subtensor.recycle(netuid)
            result["burn"] = float(burn.tao) if burn else None
        except Exception:
            result["burn"] = None

        return result
    except Exception:
        logger.exception(f"Failed to fetch subnet info for {netuid}")
        return {"netuid": netuid}


def close_subtensor():
    """Close all cached subtensor connections."""
    for key, st in _subtensor_cache.items():
        try:
            st.close()
        except Exception:
            pass
    _subtensor_cache.clear()


def get_wallet_hotkey_ss58(wallet_cfg: WalletConfig) -> str:
    """Resolve the configured wallet hotkey SS58 address."""
    bt = _import_bittensor()
    wallet = bt.Wallet(
        name=wallet_cfg.name,
        hotkey=wallet_cfg.hotkey,
        path=wallet_cfg.path,
    )
    return wallet.hotkeypub.ss58_address


# ── Auto-Registration ───────────────────────────────────────────────────


def burned_register_sdk(
    netuid: int,
    wallet_cfg: WalletConfig,
    network: str = "finney",
    endpoint: str | None = None,
) -> RegistrationResult:
    """Register a wallet on a subnet by burning TAO.

    Uses bittensor v10+ burned_register method.
    Runs synchronously — wrap with asyncio.to_thread for async use.
    """
    bt = _import_bittensor()
    subtensor = _get_subtensor(network, endpoint)

    wallet = bt.Wallet(
        name=wallet_cfg.name,
        hotkey=wallet_cfg.hotkey,
        path=wallet_cfg.path,
    )

    hotkey_ss58 = wallet.hotkeypub.ss58_address

    # Check if already registered
    if subtensor.is_hotkey_registered_on_subnet(hotkey_ss58, netuid):
        return RegistrationResult(
            netuid=netuid,
            success=True,
            cost_tao=0,
            hotkey=hotkey_ss58,
            error="already_registered",
        )

    # Get burn cost before registration
    burn = subtensor.recycle(netuid)
    cost_tao = float(burn.tao) if burn else 0

    # Perform registration
    result = subtensor.burned_register(
        wallet=wallet,
        netuid=netuid,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    if result and result.is_success:
        return RegistrationResult(
            netuid=netuid,
            success=True,
            cost_tao=cost_tao,
            hotkey=hotkey_ss58,
            tx_hash=str(result) if result else None,
        )
    else:
        error_msg = str(result) if result else "unknown error"
        return RegistrationResult(
            netuid=netuid,
            success=False,
            cost_tao=cost_tao,
            hotkey=hotkey_ss58,
            error=error_msg,
        )


async def burned_register(
    netuid: int,
    wallet_cfg: WalletConfig,
    network: str = "finney",
    endpoint: str | None = None,
) -> RegistrationResult:
    """Async wrapper for burned_register_sdk."""
    return await asyncio.to_thread(burned_register_sdk, netuid, wallet_cfg, network, endpoint)


def is_registered_sdk(
    hotkey_ss58: str,
    netuid: int,
    network: str = "finney",
    endpoint: str | None = None,
) -> bool:
    """Check if a hotkey is registered on a subnet."""
    subtensor = _get_subtensor(network, endpoint)
    return subtensor.is_hotkey_registered_on_subnet(hotkey_ss58, netuid)


async def is_registered(
    hotkey_ss58: str,
    netuid: int,
    network: str = "finney",
    endpoint: str | None = None,
) -> bool:
    """Async wrapper for is_registered_sdk."""
    return await asyncio.to_thread(is_registered_sdk, hotkey_ss58, netuid, network, endpoint)


# ── Metagraph / Deregistration ──────────────────────────────────────────


def get_metagraph_hotkeys_sdk(
    netuid: int,
    network: str = "finney",
    endpoint: str | None = None,
) -> list[str]:
    """Fetch all registered hotkeys for a subnet."""
    subtensor = _get_subtensor(network, endpoint)
    meta = subtensor.metagraph(netuid)
    return list(meta.hotkeys)


async def get_metagraph_hotkeys(
    netuid: int,
    network: str = "finney",
    endpoint: str | None = None,
) -> list[str]:
    """Async wrapper for get_metagraph_hotkeys_sdk."""
    return await asyncio.to_thread(get_metagraph_hotkeys_sdk, netuid, network, endpoint)


# ── Wallet Info ─────────────────────────────────────────────────────────


def get_wallet_info_sdk(
    wallet_cfg: WalletConfig,
    network: str = "finney",
    endpoint: str | None = None,
) -> dict:
    """Get wallet info: coldkey address, hotkey address, balance, registration status.

    Returns dict with keys:
      - name, hotkey, path
      - coldkey_exists, hotkey_exists
      - coldkey_ss58, hotkey_ss58
      - balance_tao
      - registered_on: list of netuids the hotkey is registered on
    """
    bt = _import_bittensor()
    subtensor = _get_subtensor(network, endpoint)

    wallet = bt.Wallet(
        name=wallet_cfg.name,
        hotkey=wallet_cfg.hotkey,
        path=wallet_cfg.path,
    )

    result = {
        "name": wallet_cfg.name,
        "hotkey": wallet_cfg.hotkey,
        "path": wallet_cfg.path,
        "coldkey_exists": False,
        "hotkey_exists": False,
        "coldkey_ss58": None,
        "hotkey_ss58": None,
        "balance_tao": None,
        "registered_on": [],
    }

    # Check coldkey
    try:
        coldkeypub = wallet.coldkeypub
        result["coldkey_exists"] = True
        result["coldkey_ss58"] = coldkeypub.ss58_address

        balance = subtensor.get_balance(coldkeypub.ss58_address)
        result["balance_tao"] = float(balance.tao)
    except Exception:
        pass

    # Check hotkey
    try:
        hotkeypub = wallet.hotkeypub
        result["hotkey_exists"] = True
        result["hotkey_ss58"] = hotkeypub.ss58_address

        for netuid in range(1, 55):
            try:
                if subtensor.is_hotkey_registered_on_subnet(hotkeypub.ss58_address, netuid):
                    result["registered_on"].append(netuid)
            except Exception:
                continue
    except Exception:
        pass

    return result


async def get_wallet_info(
    wallet_cfg: WalletConfig,
    network: str = "finney",
    endpoint: str | None = None,
) -> dict:
    """Async wrapper for get_wallet_info_sdk."""
    return await asyncio.to_thread(get_wallet_info_sdk, wallet_cfg, network, endpoint)
