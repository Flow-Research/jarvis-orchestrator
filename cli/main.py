#!/usr/bin/env python3
"""
Jarvis-Miner CLI — Advanced unified interface for all miner operations.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ============================================================================
# CRITICAL: Filter bittensor CLI args BEFORE any bittensor import
# ============================================================================

for arg in list(sys.argv):
    if (
        arg.startswith("--logging.")
        or arg.startswith("--config")
        or arg == "--strict"
        or arg == "--no_version_checking"
    ):
        sys.argv.remove(arg)

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "miner_tools" / "config" / "config.yaml"
GB = 1024 ** 3
JARVIS_BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝

        O R C H E S T R A T O R
"""

# ============================================================================
# CLI Entry Point
# ============================================================================
# Lazy bittensor
# ============================================================================


def get_bittensor():
    """Lazy load bittensor to avoid CLI args."""
    return __import__("bittensor")


# ============================================================================
# CLI Entry Point
# ============================================================================


def _load_yaml_config_file(config_path: Path) -> dict:
    """Load raw YAML config for display-oriented commands."""
    import yaml

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = yaml.safe_load(config_path.read_text())
    if not data:
        raise ValueError(f"Config file is empty: {config_path}")
    return data


def _load_raw_config(config_path: Path) -> dict[str, Any]:
    """Load raw config, returning an empty structure on missing/invalid files."""
    try:
        data = _load_yaml_config_file(config_path)
    except (FileNotFoundError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _subnet_settings(raw_config: dict[str, Any], subnet: int) -> dict[str, Any]:
    """Return raw config for a subnet if present."""
    for entry in raw_config.get("subnets", []):
        if int(entry.get("netuid", -1)) == subnet:
            return entry
    return {}


def _resolve_network(raw_config: dict[str, Any], network: str | None) -> str:
    """Resolve CLI network choice against config defaults."""
    if network:
        return network

    configured = raw_config.get("global", {}).get("subtensor_network", "test")
    if configured in {"test", "testnet"}:
        return "testnet"
    return "mainnet"


def _resolve_wallet_name(raw_config: dict[str, Any], subnet: int, wallet: str | None) -> str:
    """Resolve wallet name using subnet-specific config if available."""
    if wallet:
        return wallet

    subnet_cfg = _subnet_settings(raw_config, subnet)
    wallet_cfg = subnet_cfg.get("wallet", {})
    return (
        wallet_cfg.get("name")
        or raw_config.get("global", {}).get("wallet", {}).get("name")
        or f"sn{subnet}miner"
    )


def _resolve_hotkey_name(raw_config: dict[str, Any], subnet: int, hotkey: str | None) -> str:
    """Resolve hotkey name using subnet-specific config if available."""
    if hotkey:
        return hotkey

    subnet_cfg = _subnet_settings(raw_config, subnet)
    wallet_cfg = subnet_cfg.get("wallet", {})
    return (
        wallet_cfg.get("hotkey")
        or raw_config.get("global", {}).get("wallet", {}).get("hotkey")
        or "default"
    )


def _network_key(network: str) -> str:
    """Translate user-facing network choice to bittensor network key."""
    return "test" if network == "testnet" else "finney"


def _format_balance(value: Any) -> str:
    """Normalize chain balance representations for display."""
    text = str(value)
    if text.startswith("τ"):
        return text
    try:
        return f"τ{float(value):.6f}"
    except (TypeError, ValueError):
        return text


def _state_file_for_subnet(subnet: int) -> Path:
    return PROJECT_ROOT / "subnets" / f"sn{subnet}" / "state.json"


def _log_file_for_subnet(subnet: int) -> Path:
    return PROJECT_ROOT / "subnets" / f"sn{subnet}" / "listener.log"


def _sn13_db_path() -> Path:
    default_path = PROJECT_ROOT / "subnets" / "sn13" / "data" / "sn13.sqlite3"
    return Path(os.environ.get("JARVIS_SN13_DB_PATH", str(default_path)))


def _sn13_export_root() -> Path:
    return PROJECT_ROOT / "subnets" / "sn13" / "exports"


def _sn13_gravity_cache_dir() -> Path:
    return PROJECT_ROOT / "subnets" / "sn13" / "cache" / "gravity"


def _workstream_db_path() -> Path:
    default_path = PROJECT_ROOT / "data" / "workstream.sqlite3"
    return Path(os.environ.get("JARVIS_WORKSTREAM_DB_PATH", str(default_path)))


def _runtime_entrypoint_for_subnet(subnet: int) -> Path | None:
    """Find the best available runtime script for a subnet."""
    subnet_dir = PROJECT_ROOT / "subnets" / f"sn{subnet}"
    candidates = [
        subnet_dir / "listener" / "listener.py",
        subnet_dir / "miner.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _is_pid_running(pid: int | None) -> bool:
    """Check whether a PID still exists."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_state(subnet: int) -> dict[str, Any]:
    state_file = _state_file_for_subnet(subnet)
    if not state_file.exists():
        return {}
    try:
        state = json.loads(state_file.read_text())
    except json.JSONDecodeError:
        return {}
    return state if isinstance(state, dict) else {}


def _wallet_hotkey_file_exists(wallet_name: str, hotkey_name: str) -> bool:
    wallet_root = Path.home() / ".bittensor" / "wallets" / wallet_name
    hotkey_paths = [
        wallet_root / "hotkeys" / hotkey_name,
    ]
    if hotkey_name == "default":
        hotkey_paths.append(wallet_root / "hotkeys" / "default")
    else:
        hotkey_paths.append(wallet_root / hotkey_name)
    return any(path.exists() for path in hotkey_paths)


def _query_hotkey_registration(
    *,
    wallet_name: str,
    hotkey_name: str,
    network: str,
    subnet: int,
) -> tuple[bool, str | None, str | None]:
    """Best-effort live chain registration check."""
    bt = get_bittensor()
    net = _network_key(network)
    try:
        wallet = bt.Wallet(name=wallet_name, hotkey=hotkey_name)
    except TypeError:
        wallet = bt.Wallet(name=wallet_name)

    hotkey = getattr(getattr(wallet, "hotkeypub", None), "ss58_address", None)
    if hotkey is None:
        hotkey = getattr(getattr(wallet, "hotkey", None), "ss58_address", None)
    if not hotkey:
        return False, None, "wallet hotkey address not available"

    subtensor = bt.Subtensor(network=net)
    metagraph = subtensor.metagraph(subnet)
    return hotkey in metagraph.hotkeys, hotkey, None


def _print_banner() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]{JARVIS_BANNER}[/bold cyan]",
            subtitle="[bold]multi-subnet miner control plane[/bold]",
            border_style="cyan",
        )
    )


def _configure_monitor_logging(verbose: bool = False) -> None:
    """Configure logging for the legacy registration monitor tools."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    logging.getLogger().setLevel(level)
    logging.getLogger("miner_tools").setLevel(level)
    logging.getLogger("bittensor").setLevel(logging.WARNING if verbose else logging.ERROR)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    try:
        from loguru import logger as loguru_logger

        loguru_logger.remove()
        loguru_logger.add(
            sys.stderr,
            level="INFO" if verbose else "ERROR",
            format="<level>{level}</level> {message}",
        )
    except Exception:
        pass


def _load_monitor_config(ctx) -> tuple[Any, list[Any]]:
    """Load miner_tools config for monitor/registration commands."""
    from miner_tools.config import load_config

    config_file = ctx.obj["config_path"]
    try:
        return load_config(config_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc


def _fallback_subnet_config(netuid: int):
    """Create a minimal subnet config for ad-hoc monitor price/register commands."""
    from miner_tools.models import AlertConfig, SubnetConfig

    return SubnetConfig(netuid=netuid, price_threshold_tao=0, alerts=AlertConfig())


def _monitor_targets(subnets: list[Any], netuid: int | None) -> list[Any]:
    if netuid is None:
        return subnets
    targets = [subnet for subnet in subnets if subnet.netuid == netuid]
    return targets or [_fallback_subnet_config(netuid)]


def _run_async(coro):
    """Run an async monitor command from Click without reusing stale loops."""
    return asyncio.run(coro)


def _sn13_plan_context(
    *,
    dd_file: Path | None,
    cache_dir: Path | None,
    sample_dd: bool,
    db_path: Path | None,
    target_items: int,
    recent_buckets: int,
    max_tasks: int,
):
    from subnets.sn13.simulator import (
        ClosedLoopSimulationConfig,
        create_tasks_from_demands,
        load_snapshot,
        plan_demands,
    )
    from subnets.sn13.storage import SQLiteStorage

    resolved_db_path = db_path or _sn13_db_path()
    resolved_cache_dir = cache_dir or _sn13_gravity_cache_dir()
    storage = SQLiteStorage(resolved_db_path)
    snapshot = load_snapshot(dd_file, cache_dir=resolved_cache_dir, use_sample=sample_dd)
    config = ClosedLoopSimulationConfig(
        target_items_per_bucket=target_items,
        default_recent_buckets=recent_buckets,
        max_tasks=max_tasks,
        export=False,
    )
    demands = plan_demands(storage=storage, snapshot=snapshot, config=config)
    tasks = create_tasks_from_demands(
        storage=storage,
        demands=demands,
        config=config,
    )
    return resolved_db_path, snapshot, tasks


def _sn13_publication_economics_options(command):
    """Attach shared economics options to SN13 publish/automation commands."""
    options = [
        click.option(
            "--max-task-cost",
            type=float,
            default=None,
            envvar="JARVIS_SN13_MAX_TASK_COST",
        ),
        click.option(
            "--expected-reward",
            type=float,
            default=None,
            envvar="JARVIS_SN13_EXPECTED_REWARD",
        ),
        click.option(
            "--expected-submitted",
            type=int,
            default=None,
            envvar="JARVIS_SN13_EXPECTED_SUBMITTED",
        ),
        click.option(
            "--expected-accepted",
            type=int,
            default=None,
            envvar="JARVIS_SN13_EXPECTED_ACCEPTED",
        ),
        click.option(
            "--duplicate-rate",
            type=float,
            default=None,
            envvar="JARVIS_SN13_DUPLICATE_RATE",
        ),
        click.option(
            "--rejection-rate",
            type=float,
            default=None,
            envvar="JARVIS_SN13_REJECTION_RATE",
        ),
        click.option(
            "--validation-pass-probability",
            type=float,
            default=None,
            envvar="JARVIS_SN13_VALIDATION_PASS_PROBABILITY",
        ),
        click.option(
            "--payout-basis",
            type=click.Choice(["accepted_scorable_record", "accepted_record", "flat_task", "none"]),
            default=None,
            envvar="JARVIS_SN13_PAYOUT_BASIS",
        ),
        click.option(
            "--operator-payout",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_OPERATOR_PAYOUT",
        ),
        click.option(
            "--scraper-provider-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_SCRAPER_PROVIDER_COST",
        ),
        click.option(
            "--proxy-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_PROXY_COST",
        ),
        click.option(
            "--compute-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_COMPUTE_COST",
        ),
        click.option(
            "--local-storage-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_LOCAL_STORAGE_COST",
        ),
        click.option(
            "--export-staging-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_EXPORT_STAGING_COST",
        ),
        click.option(
            "--upload-bandwidth-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_UPLOAD_BANDWIDTH_COST",
        ),
        click.option(
            "--retry-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_RETRY_COST",
        ),
        click.option(
            "--risk-reserve",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_RISK_RESERVE",
        ),
        click.option(
            "--jarvis-archive-bucket-cost",
            type=float,
            default=0.0,
            show_default=True,
            envvar="JARVIS_SN13_JARVIS_ARCHIVE_BUCKET_COST",
        ),
        click.option(
            "--s3-mode",
            type=click.Choice(
                ["upstream_presigned", "jarvis_archive", "upstream_and_jarvis_archive"]
            ),
            default="upstream_presigned",
            show_default=True,
            envvar="JARVIS_SN13_S3_MODE",
        ),
        click.option(
            "--currency",
            type=str,
            default="USD",
            show_default=True,
            envvar="JARVIS_SN13_CURRENCY",
        ),
    ]
    for option in reversed(options):
        command = option(command)
    return command


def _sn13_publication_economics_config(
    *,
    max_task_cost: float | None,
    expected_reward: float | None,
    expected_submitted: int | None,
    expected_accepted: int | None,
    duplicate_rate: float | None,
    rejection_rate: float | None,
    validation_pass_probability: float | None,
    payout_basis: str | None,
    operator_payout: float,
    scraper_provider_cost: float,
    proxy_cost: float,
    compute_cost: float,
    local_storage_cost: float,
    export_staging_cost: float,
    upload_bandwidth_cost: float,
    retry_cost: float,
    risk_reserve: float,
    jarvis_archive_bucket_cost: float,
    s3_mode: str,
    currency: str,
):
    """Build the economics config used to gate SN13 task publication."""
    from pydantic import ValidationError

    from subnets.sn13.economics import CostBreakdown, PayoutBasis, S3StorageMode
    from subnets.sn13.publication import PublicationEconomicsConfig

    try:
        return PublicationEconomicsConfig(
            max_task_cost=max_task_cost,
            expected_reward_value=expected_reward,
            expected_submitted_records=expected_submitted,
            expected_accepted_scorable_records=expected_accepted,
            expected_duplicate_rate=duplicate_rate,
            expected_rejection_rate=rejection_rate,
            validation_pass_probability=validation_pass_probability,
            payout_basis=PayoutBasis(payout_basis) if payout_basis else None,
            costs=CostBreakdown(
                operator_payout=operator_payout,
                scraper_provider_cost=scraper_provider_cost,
                proxy_cost=proxy_cost,
                compute_cost=compute_cost,
                local_storage_cost=local_storage_cost,
                export_staging_cost=export_staging_cost,
                upload_bandwidth_cost=upload_bandwidth_cost,
                retry_cost=retry_cost,
                risk_reserve=risk_reserve,
                jarvis_archive_bucket_cost=jarvis_archive_bucket_cost,
            ),
            s3_storage_mode=S3StorageMode(s3_mode),
            currency=currency,
        )
    except ValidationError as exc:
        raise click.ClickException(str(exc)) from exc


def _alert_channels_label(subnet) -> str:
    channels = []
    if subnet.alerts.discord:
        channels.append("Discord")
    if subnet.alerts.telegram:
        channels.append("Telegram")
    return ", ".join(channels) if channels else "-"


@click.group(context_settings={"ignore_unknown_options": True}, invoke_without_command=True)
@click.version_option(version="1.0.0", prog_name="jarvis-miner")
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Path to configuration file.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose CLI output.")
@click.pass_context
def cli(ctx, config_path: Path, verbose: bool):
    """Jarvis-Miner — Complete miner orchestration for Bittensor subnets."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose
    ctx.obj["raw_config"] = _load_raw_config(config_path)

    if ctx.invoked_subcommand is None:
        _print_banner()
        lines = [
            f"Config: {config_path}",
            f"Subnets configured: {len(ctx.obj['raw_config'].get('subnets', []))}",
        ]
        if verbose:
            console.print(Panel.fit("\n".join(lines), border_style="cyan"))
        console.print(ctx.get_help())


# ============================================================================
# WALLET Commands
# ============================================================================


@cli.group()
def wallet():
    """Wallet management commands."""
    pass


@wallet.command("create")
@click.option("--name", "-n", type=str, required=True, help="Wallet name")
@click.option(
    "--password",
    "-p",
    type=str,
    default=None,
    help="Password (optional, will prompt)",
    hide_input=True,
)
def wallet_create(name: str, password: str | None):
    """Create a new wallet with coldkey and hotkey."""
    bt = get_bittensor()

    wallet_path = Path.home() / ".bittensor" / "wallets" / name

    if wallet_path.exists():
        console.print(f"[red]Wallet '{name}' already exists[/red]")
        return

    console.print(f"[yellow]Creating wallet: {name}[/yellow]")

    try:
        wallet = bt.Wallet(name=name)
        wallet.create_new_coldkey(n_words=24, use_password=bool(password), hotkey_password=password)
        wallet.create_new_hotkey(n_words=12, use_password=False)

        console.print(f"[green]✓ Wallet '{name}' created![/green]")
        console.print(f"[cyan]Coldkey: {wallet.coldkeypub.ss58_address}[/cyan]")
        console.print(f"[cyan]Hotkey: {wallet.hotkeypub.ss58_address}[/cyan]")
        console.print("[yellow]⚠️  Save your seed words! They cannot be recovered.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@wallet.command("create-hotkey")
@click.option("--name", "-n", type=str, required=True, help="Wallet name")
@click.option("--subnet", "-s", type=int, default=None, help="Subnet ID")
def wallet_create_hotkey(name: str, subnet: int | None):
    """Create a new hotkey for a subnet."""
    bt = get_bittensor()
    wallet_path = Path.home() / ".bittensor" / "wallets" / name
    if not wallet_path.exists():
        console.print(f"[red]Wallet '{name}' does not exist[/red]")
        return

    try:
        wallet = bt.Wallet(name=name)
        hotkey_name = str(subnet) if subnet else "default"
        wallet.create_new_hotkey(n_words=12, use_password=False, hotkey_name=hotkey_name)
        console.print(f"[green]✓ Hotkey '{hotkey_name}' created for {name}![/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@wallet.command("info")
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="testnet")
@click.option("--all", "-a", is_flag=True, help="Show all wallets")
@click.pass_context
def wallet_info(ctx, network: str, all: bool):
    """Show wallet info with balances and stake status."""
    bt = get_bittensor()

    wallet_path = Path.home() / ".bittensor" / "wallets"
    if not wallet_path.exists():
        console.print("[red]No wallets found[/red]")
        return

    net = "test" if network == "testnet" else "finney"

    try:
        subtensor = bt.Subtensor(network=net)
    except Exception as e:
        console.print(f"[red]Failed to connect to {network}: {e}[/red]")
        return

    table = Table(title=f"Wallets on {network}")
    table.add_column("Name", style="cyan")
    table.add_column("Hotkey", style="green")
    table.add_column("Balance", style="yellow")
    table.add_column("SN13 Stake", style="magenta")

    raw_config = ctx.obj.get("raw_config", {})
    configured_wallets = {
        item.get("wallet", {}).get("name")
        for item in raw_config.get("subnets", [])
        if item.get("wallet", {}).get("name")
    }

    for w in sorted(wallet_path.iterdir()):
        if not w.is_dir():
            continue
        if not all and configured_wallets and w.name not in configured_wallets:
            continue
        try:
            wallet = bt.Wallet(name=w.name)
            hotkey = wallet.hotkeypub.ss58_address
        except Exception:
            continue

        # Balance
        try:
            balance = subtensor.get_balance(wallet.coldkeypub.ss58_address)
            balance_str = f"τ{float(balance):.2f}"
        except Exception:
            balance_str = "N/A"

        # SN13 stake
        try:
            meta = subtensor.metagraph(13)
            if hotkey in meta.hotkeys:
                uid = meta.hotkeys.index(hotkey)
                stake = float(meta.stake[uid])
                stake_str = f"τ{stake:.2f}"
            else:
                stake_str = "-"
        except Exception:
            stake_str = "-"

        table.add_row(w.name, hotkey[:10] + "...", balance_str, stake_str)

    console.print(table)


@wallet.command("balances")
@click.option("--wallet", "-w", type=str, required=True, help="Wallet name")
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="testnet")
def wallet_balances(wallet: str, network: str):
    """Show detailed balance across all subnets."""
    bt = get_bittensor()
    net = "test" if network == "testnet" else "finney"

    try:
        wallet_obj = bt.Wallet(name=wallet)
        subtensor = bt.Subtensor(network=net)
        coldkey = wallet_obj.coldkeypub.ss58_address
        hotkey = wallet_obj.hotkeypub.ss58_address
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Primary balance
    try:
        balance = subtensor.get_balance(coldkey)
        console.print(f"\n[bold cyan]═══ {wallet} on {network} ═══[/bold cyan]")
        console.print(f"Coldkey: {coldkey}")
        console.print(f"Balance: [green]τ{float(balance):.4f}[/green] TAO")
    except Exception as e:
        console.print(f"[red]Balance error: {e}[/red]")

    # All subnet stakes
    table = Table(title="Active Subnet Stakes")
    table.add_column("SN", style="cyan")
    table.add_column("UID", style="yellow")
    table.add_column("Stake", style="green")

    for netuid in range(1, 65):
        try:
            meta = subtensor.metagraph(netuid)
            if hotkey in meta.hotkeys:
                uid = meta.hotkeys.index(hotkey)
                stake = float(meta.stake[uid])
                if stake > 0:
                    table.add_row(str(netuid), str(uid), f"τ{stake:.2f}")
        except Exception:
            pass

    if table.row_count > 0:
        console.print(table)
    else:
        console.print("[yellow]No active stakes[/yellow]")


@wallet.command("faucet")
@click.option("--wallet", "-w", type=str, default="sn13miner")
def wallet_faucet(wallet: str):
    """Get testnet TAO via PoW (testnet only)."""
    bt = get_bittensor()
    console.print(f"[yellow]Running faucet for {wallet}...[/yellow]")
    console.print("[dim]This uses Proof of Work, may take minutes...[/dim]")

    try:
        wallet_obj = bt.Wallet(name=wallet)
        subtensor = bt.Subtensor(network="test")
        subtensor.run_faucet(wallet=wallet_obj)
        console.print("[green]✓ Faucet complete![/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ============================================================================
# MINER Commands
# ============================================================================


@cli.group()
def miner():
    """Miner management commands."""
    pass


@miner.command("start")
@click.option("--subnet", "-s", type=int, default=13, help="Subnet ID")
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default=None)
@click.option("--wallet", "-w", type=str, default=None)
@click.pass_context
def miner_start(ctx, subnet: int, network: str | None, wallet: str | None):
    """Start miner listener."""
    raw_config = ctx.obj.get("raw_config", {})
    network = _resolve_network(raw_config, network)
    wallet = _resolve_wallet_name(raw_config, subnet, wallet)

    subnet_dir = PROJECT_ROOT / "subnets" / f"sn{subnet}"

    if not subnet_dir.exists():
        console.print(f"[red]Subnet {subnet} not found[/red]")
        return

    state_file = _state_file_for_subnet(subnet)
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            if state.get("running") and _is_pid_running(state.get("pid")):
                console.print(f"[yellow]Miner already running on subnet {subnet}[/yellow]")
                return
            if state.get("running"):
                console.print(
                    f"[yellow]Found stale running state for subnet {subnet}; replacing it.[/yellow]"
                )

    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    runtime_script = _runtime_entrypoint_for_subnet(subnet)
    log_file = _log_file_for_subnet(subnet)
    capture_dir = subnet_dir / "listener" / "captures"

    if runtime_script is None:
        console.print(f"[red]No runtime entrypoint found for subnet {subnet}[/red]")
        raise SystemExit(1)

    net_arg = _network_key(network)
    python_exe = venv_python if venv_python.exists() else Path(sys.executable)
    cmd = [
        str(python_exe),
        "-u",
        str(runtime_script),
        "--wallet",
        wallet,
        "--network",
        net_arg,
    ]
    if runtime_script.parent.name == "listener":
        cmd.extend(["--capture-dir", str(capture_dir)])

    console.print(f"[yellow]Starting miner on subnet {subnet} ({network})...[/yellow]")
    if ctx.obj.get("verbose"):
        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

    env = os.environ.copy()
    env.setdefault("ARROW_USER_SIMD_LEVEL", "NONE")

    with open(log_file, "w") as out:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

    state = {
        "subnet": subnet,
        "network": network,
        "wallet": wallet,
        "pid": proc.pid,
        "running": True,
    }
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    console.print(f"[green]✓ Miner started (PID {proc.pid})[/green]")


@miner.command("stop")
@click.option("--subnet", "-s", type=int, default=13)
def miner_stop(subnet: int):
    """Stop miner listener."""
    state_file = _state_file_for_subnet(subnet)

    if not state_file.exists():
        console.print(f"[yellow]No miner state for subnet {subnet}[/yellow]")
        return

    with open(state_file) as f:
        state = json.load(f)

    pid = state.get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            console.print(f"[green]✓ Miner stopped (PID {pid})[/green]")
        except ProcessLookupError:
            console.print(f"[yellow]Process {pid} not found[/yellow]")

    state["running"] = False
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


@miner.command("status")
@click.option("--subnet", "-s", type=int, default=13)
def miner_status(subnet: int):
    """Check miner status."""
    state_file = _state_file_for_subnet(subnet)
    log_file = _log_file_for_subnet(subnet)

    table = Table(title=f"Subnet {subnet} Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        running = bool(state.get("running")) and _is_pid_running(state.get("pid"))
        table.add_row(
            "Status", "[green]Running[/green]" if running else "[red]Stopped[/red]"
        )
        table.add_row("PID", str(state.get("pid", "N/A")))
        table.add_row("Network", state.get("network", "N/A"))
        table.add_row("Wallet", state.get("wallet", "N/A"))
    else:
        table.add_row("Status", "[red]No state file[/red]")

    if log_file.exists():
        table.add_row("Log lines", str(sum(1 for _ in open(log_file))))
    else:
        table.add_row("Log lines", "0")

    capture_summary = (
        PROJECT_ROOT / "subnets" / f"sn{subnet}" / "listener" / "captures" / "summary.json"
    )
    if capture_summary.exists():
        table.add_row("Captures", "yes")
    else:
        table.add_row("Captures", "no")

    console.print(table)


@miner.command("logs")
@click.option("--subnet", "-s", type=int, default=13)
@click.option("--lines", "-n", type=int, default=20)
def miner_logs(subnet: int, lines: int):
    """View miner logs."""
    log_file = _log_file_for_subnet(subnet)

    if not log_file.exists():
        console.print(f"[yellow]No logs for subnet {subnet}[/yellow]")
        return

    console.print(f"[cyan]═══ Last {lines} lines from subnet {subnet} ═══[/cyan]")
    with open(log_file) as f:
        for line in f.read().splitlines()[-lines:]:
            print(line)


# ============================================================================
# MONITOR Commands
# ============================================================================


@cli.group()
def monitor():
    """Registration price monitor, auto-register, and deregister commands."""
    pass


def _monitor_watch_impl(ctx) -> None:
    """Start the live price monitor with auto-registration and deregister alerts."""
    verbose = bool(ctx.obj.get("verbose", False))
    _configure_monitor_logging(verbose)
    global_cfg, subnets = _load_monitor_config(ctx)

    from miner_tools.deregister import DeregisterMonitor
    from miner_tools.monitor import Monitor

    monitor_engine = Monitor(global_cfg, subnets)
    dereg_monitor = DeregisterMonitor(global_cfg, subnets)

    enabled = [subnet for subnet in subnets if subnet.enabled]
    auto_reg = [subnet for subnet in enabled if subnet.auto_register]
    dereg_entries = sum(len(subnet.deregister_entries) for subnet in enabled)
    alert_channel_set = {
        label for subnet in enabled if (label := _alert_channels_label(subnet)) != "-"
    }
    wallet = global_cfg.wallet
    headline = "\n".join(
        [
            "[bold cyan]JARVIS ORCHESTRATOR[/bold cyan]",
            "[bold white]Registration Watch[/bold white]",
            (
                f"Network [bold]{global_cfg.subtensor_network}[/bold] | "
                f"source [bold]{global_cfg.price_source}[/bold] | "
                f"data [bold]{global_cfg.data_dir}[/bold]"
            ),
            (
                f"Watching [bold]{len(enabled)}[/bold] subnet(s) | "
                f"auto-register [bold]{'ON' if auto_reg else 'OFF'}[/bold] | "
                f"deregister watches [bold]{dereg_entries}[/bold]"
            ),
            (
                f"Wallet [bold]{wallet.name}/{wallet.hotkey}[/bold] | "
                f"alerts [bold]{', '.join(sorted(alert_channel_set)) or 'none'}[/bold]"
            ),
        ]
    )
    console.print(Panel.fit(headline, border_style="cyan"))

    table = Table(title="Watched Subnets", show_lines=False)
    table.add_column("SN", justify="right", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Threshold", justify="right", style="yellow")
    table.add_column("Poll", justify="right")
    table.add_column("Adaptive", justify="center")
    table.add_column("Auto", justify="center")
    table.add_column("Alerts", style="magenta")
    table.add_column("Dereg", justify="right")
    for subnet in enabled:
        table.add_row(
            str(subnet.netuid),
            subnet.label,
            f"{subnet.price_threshold_tao:.4f}",
            f"{subnet.poll_interval_seconds}s",
            "yes" if subnet.adaptive_polling else "no",
            "yes" if subnet.auto_register else "no",
            _alert_channels_label(subnet),
            str(len(subnet.deregister_entries)),
        )
    console.print(table)

    if verbose:
        console.print("[dim]Verbose poll logs enabled. Press Ctrl+C to stop.[/dim]")
    else:
        console.print(
            "[dim]Running quietly. First chain poll can take ~15s. "
            "Use -v for detailed poll logs. Press Ctrl+C to stop.[/dim]"
        )

    async def _run_both():
        tasks = [asyncio.create_task(monitor_engine.start(), name="price-monitor")]
        if dereg_monitor.has_entries:
            tasks.append(asyncio.create_task(dereg_monitor.start(), name="dereg-monitor"))
        await asyncio.gather(*tasks, return_exceptions=True)

    try:
        _run_async(_run_both())
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")
    finally:
        console.print("[dim]Monitor stopped.[/dim]")


@monitor.command("watch")
@click.pass_context
def monitor_watch(ctx) -> None:
    """Start live price monitoring with auto-registration and deregister alerts."""
    _monitor_watch_impl(ctx)


@cli.command("watch")
@click.pass_context
def legacy_watch(ctx) -> None:
    """Compatibility alias for `monitor watch`."""
    _monitor_watch_impl(ctx)


def _monitor_price_impl(ctx, netuid: int | None) -> None:
    """Fetch the current registration burn cost for one or all configured subnets."""
    from miner_tools.fetcher import close_subtensor, fetch_burn_cost

    global_cfg, subnets = _load_monitor_config(ctx)
    targets = _monitor_targets(subnets, netuid)

    table = Table(title="Registration Burn Cost", show_lines=True)
    table.add_column("SN", style="cyan", justify="right")
    table.add_column("Label", style="white")
    table.add_column("Cost (TAO)", style="bold yellow", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Ratio", justify="right")
    table.add_column("Status", justify="center")

    for subnet in targets:
        try:
            reading = _run_async(
                fetch_burn_cost(
                    subnet,
                    global_cfg.subtensor_network,
                    global_cfg.subtensor_endpoint,
                    global_cfg.taostats_api_key,
                    source=global_cfg.price_source,
                )
            )
            ratio = (
                reading.cost_tao / subnet.price_threshold_tao
                if subnet.price_threshold_tao > 0
                else 0
            )
            if subnet.price_threshold_tao > 0:
                threshold = f"{subnet.price_threshold_tao:.6f}"
                ratio_text = f"{ratio:.2f}x"
                if ratio <= 0.5:
                    status = "[bold green]EXCELLENT[/bold green]"
                elif ratio <= 1.0:
                    status = "[green]GOOD[/green]"
                elif ratio <= 1.5:
                    status = "[yellow]FAIR[/yellow]"
                else:
                    status = "[red]HIGH[/red]"
            else:
                threshold = "-"
                ratio_text = "-"
                status = "[dim]-[/dim]"

            table.add_row(
                str(subnet.netuid),
                subnet.label,
                f"{reading.cost_tao:.6f}",
                threshold,
                ratio_text,
                status,
            )
        except Exception as exc:
            table.add_row(str(subnet.netuid), subnet.label, f"[red]{exc}[/red]", "-", "-", "-")

    console.print(table)
    close_subtensor()


@monitor.command("price")
@click.argument("netuid", type=int, required=False)
@click.pass_context
def monitor_price(ctx, netuid: int | None) -> None:
    """Fetch current registration burn cost for configured subnets."""
    _monitor_price_impl(ctx, netuid)


@cli.command("price")
@click.argument("netuid", type=int, required=False)
@click.pass_context
def legacy_price(ctx, netuid: int | None) -> None:
    """Compatibility alias for `monitor price`."""
    _monitor_price_impl(ctx, netuid)


def _monitor_status_impl(ctx) -> None:
    """Show monitor state, price history, and floor events."""
    from miner_tools.models import MonitorState, Trend

    global_cfg, subnets = _load_monitor_config(ctx)
    state = MonitorState.load(global_cfg.data_dir / "monitor_state.json")

    if not state.histories:
        console.print("[dim]No price history found. Run 'jarvis-miner monitor watch' first.[/dim]")
        return

    table = Table(title="Monitor Status", show_lines=True, expand=True)
    table.add_column("SN", style="cyan", justify="right", width=4)
    table.add_column("Subnet", style="white", width=16)
    table.add_column("Last Price", style="bold yellow", justify="right", width=14)
    table.add_column("Trend", width=12)
    table.add_column("Readings", justify="right", width=8)
    table.add_column("Min", justify="right", width=12)
    table.add_column("Max", justify="right", width=12)
    table.add_column("Avg", justify="right", width=12)
    table.add_column("Floors", justify="right", width=6)
    table.add_column("Chart", width=30)
    table.add_column("Polls", justify="right", width=6)

    for subnet in subnets:
        history = state.histories.get(subnet.netuid)
        if not history or not history.readings:
            continue

        last = history.readings[-1]
        trend = history.compute_trend(global_cfg.trend_window)
        trend_style = {
            Trend.RISING: "red",
            Trend.STABLE: "yellow",
            Trend.FALLING: "green",
            Trend.UNKNOWN: "dim",
        }[trend]
        min_price = history.min_price()
        max_price = history.max_price()
        avg_price = history.avg_price()
        table.add_row(
            str(subnet.netuid),
            subnet.label,
            f"{last.cost_tao:.6f} TAO",
            f"[{trend_style}]{trend.value.upper()}[/{trend_style}]",
            str(len(history.readings)),
            f"{min_price:.6f}" if min_price is not None else "-",
            f"{max_price:.6f}" if max_price is not None else "-",
            f"{avg_price:.6f}" if avg_price is not None else "-",
            str(len(history.detected_floors)),
            history.sparkline(30),
            str(state.poll_counts.get(subnet.netuid, 0)),
        )

    console.print(table)

    floor_seen = False
    for subnet in subnets:
        history = state.histories.get(subnet.netuid)
        if history and history.detected_floors:
            if not floor_seen:
                console.print("\n[bold]Recent Floor Events:[/bold]")
                floor_seen = True
            for floor in history.detected_floors[-3:]:
                console.print(
                    f"  SN{subnet.netuid} ({subnet.label}): "
                    f"floor at {floor.floor_price:.6f} TAO "
                    f"({floor.timestamp.strftime('%Y-%m-%d %H:%M')}) "
                    f"+{floor.current_rise_pct:.1f}% rise"
                )


@monitor.command("status")
@click.pass_context
def monitor_status(ctx) -> None:
    """Show monitor state, price history, and floor events."""
    _monitor_status_impl(ctx)


@cli.command("status")
@click.pass_context
def legacy_status(ctx) -> None:
    """Compatibility alias for `monitor status`."""
    _monitor_status_impl(ctx)


def _monitor_info_impl(ctx) -> None:
    """Show detailed subnet information from the chain."""
    from miner_tools.fetcher import close_subtensor, fetch_subnet_info

    global_cfg, subnets = _load_monitor_config(ctx)

    table = Table(title="Subnet Information", show_lines=True)
    table.add_column("SN", style="cyan", justify="right")
    table.add_column("Name", style="white", width=16)
    table.add_column("Burn (TAO)", style="yellow", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("TAO In", justify="right")
    table.add_column("Tempo", justify="right")
    table.add_column("Symbol", justify="center")

    for subnet in subnets:
        try:
            info = fetch_subnet_info(
                subnet.netuid,
                global_cfg.subtensor_network,
                global_cfg.subtensor_endpoint,
            )
            table.add_row(
                str(subnet.netuid),
                info.get("name", subnet.label),
                f"{info['burn']:.6f}" if info.get("burn") else "-",
                f"{info['price']:.6f}" if info.get("price") else "-",
                f"{info['tao_in']:.2f}" if info.get("tao_in") else "-",
                str(info.get("tempo", "-")),
                info.get("symbol", "-"),
            )
        except Exception as exc:
            table.add_row(str(subnet.netuid), subnet.label, f"[red]{exc}[/red]", *["-"] * 4)

    console.print(table)
    close_subtensor()


@monitor.command("info")
@click.pass_context
def monitor_info(ctx) -> None:
    """Show detailed subnet information from the chain."""
    _monitor_info_impl(ctx)


@cli.command("info")
@click.pass_context
def legacy_info(ctx) -> None:
    """Compatibility alias for `monitor info`."""
    _monitor_info_impl(ctx)


def _monitor_register_impl(
    ctx,
    netuid: int,
    wallet_name: str | None,
    hotkey_name: str | None,
    dry_run: bool,
    yes: bool,
) -> None:
    """Register configured wallet/hotkey on a subnet using burned registration."""
    from miner_tools.fetcher import burned_register_sdk, close_subtensor, fetch_burn_cost
    from miner_tools.models import WalletConfig

    global_cfg, subnets = _load_monitor_config(ctx)
    wallet_cfg = global_cfg.wallet
    if wallet_name:
        wallet_cfg = WalletConfig(
            name=wallet_name,
            hotkey=hotkey_name or wallet_cfg.hotkey,
            path=wallet_cfg.path,
        )
    elif hotkey_name:
        wallet_cfg = WalletConfig(
            name=wallet_cfg.name,
            hotkey=hotkey_name,
            path=wallet_cfg.path,
        )

    subnet = next((item for item in subnets if item.netuid == netuid), None)
    if subnet is None:
        subnet = _fallback_subnet_config(netuid)

    try:
        reading = _run_async(
            fetch_burn_cost(
                subnet,
                global_cfg.subtensor_network,
                global_cfg.subtensor_endpoint,
                global_cfg.taostats_api_key,
                source=global_cfg.price_source,
            )
        )
        console.print(
            f"SN{netuid} registration cost: "
            f"[bold yellow]{reading.cost_tao:.6f} TAO[/bold yellow]"
        )
    except Exception as exc:
        console.print(f"[yellow]Could not fetch cost: {exc}[/yellow]")

    if dry_run:
        console.print(
            f"[dim]Dry run: would register wallet={wallet_cfg.name}, "
            f"hotkey={wallet_cfg.hotkey} on SN{netuid}[/dim]"
        )
        close_subtensor()
        return

    if not yes and not click.confirm(
        f"Register on SN{netuid} with wallet '{wallet_cfg.name}/{wallet_cfg.hotkey}'?"
    ):
        console.print("[dim]Cancelled.[/dim]")
        close_subtensor()
        return

    console.print("[dim]Registering... this may take up to 30s[/dim]")
    try:
        result = burned_register_sdk(
            netuid,
            wallet_cfg,
            global_cfg.subtensor_network,
            global_cfg.subtensor_endpoint,
        )
        if result.error == "already_registered":
            console.print(
                f"[yellow]Already registered![/yellow] "
                f"Hotkey {result.hotkey[:16]}... is on SN{netuid}"
            )
        elif result.success:
            console.print(
                f"[green]Registered![/green] "
                f"Cost: {result.cost_tao:.6f} TAO, Hotkey: {result.hotkey[:16]}..."
            )
        else:
            console.print(f"[red]Registration failed:[/red] {result.error}")
    except Exception as exc:
        console.print(f"[red]Registration error:[/red] {exc}")
    finally:
        close_subtensor()


@monitor.command("register")
@click.argument("netuid", type=int)
@click.option("-w", "--wallet", "wallet_name", default=None, help="Wallet name override.")
@click.option("-k", "--hotkey", "hotkey_name", default=None, help="Hotkey name override.")
@click.option("--dry-run", is_flag=True, help="Show what would happen without registering.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def monitor_register(
    ctx,
    netuid: int,
    wallet_name: str | None,
    hotkey_name: str | None,
    dry_run: bool,
    yes: bool,
) -> None:
    """Register a wallet on a subnet using monitor config wallet settings."""
    _monitor_register_impl(ctx, netuid, wallet_name, hotkey_name, dry_run, yes)


@cli.command("register")
@click.argument("netuid", type=int)
@click.option("-w", "--wallet", "wallet_name", default=None, help="Wallet name override.")
@click.option("-k", "--hotkey", "hotkey_name", default=None, help="Hotkey name override.")
@click.option("--dry-run", is_flag=True, help="Show what would happen without registering.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def legacy_register(
    ctx,
    netuid: int,
    wallet_name: str | None,
    hotkey_name: str | None,
    dry_run: bool,
    yes: bool,
) -> None:
    """Compatibility alias for `monitor register`."""
    _monitor_register_impl(ctx, netuid, wallet_name, hotkey_name, dry_run, yes)


def _monitor_deregister_check_impl(ctx) -> None:
    """Check registration status of all configured deregister-watch hotkeys."""
    from miner_tools.fetcher import close_subtensor, is_registered_sdk

    global_cfg, subnets = _load_monitor_config(ctx)

    table = Table(title="Deregister Monitor Status", show_lines=True)
    table.add_column("SN", style="cyan", justify="right")
    table.add_column("Subnet", style="white")
    table.add_column("Hotkey", style="dim")
    table.add_column("Label")
    table.add_column("Status", justify="center")

    found_any = False
    for subnet in subnets:
        for entry in subnet.deregister_entries:
            found_any = True
            try:
                registered = is_registered_sdk(
                    entry.hotkey_ss58,
                    subnet.netuid,
                    global_cfg.subtensor_network,
                    global_cfg.subtensor_endpoint,
                )
                status = "[green]REGISTERED[/green]" if registered else "[red]DEREGISTERED[/red]"
            except Exception as exc:
                status = f"[yellow]{exc}[/yellow]"

            table.add_row(
                str(subnet.netuid),
                subnet.label,
                f"{entry.hotkey_ss58[:12]}...{entry.hotkey_ss58[-6:]}",
                entry.display_name,
                status,
            )

    if found_any:
        console.print(table)
    else:
        console.print(
            "[dim]No deregister entries configured. Add `deregister` entries to config.yaml.[/dim]"
        )
    close_subtensor()


@monitor.command("deregister-check")
@click.pass_context
def monitor_deregister_check(ctx) -> None:
    """Check registration status of configured deregister-watch hotkeys."""
    _monitor_deregister_check_impl(ctx)


@cli.command("deregister-check")
@click.pass_context
def legacy_deregister_check(ctx) -> None:
    """Compatibility alias for `monitor deregister-check`."""
    _monitor_deregister_check_impl(ctx)


def _monitor_validate_impl(ctx, check_webhooks: bool) -> None:
    """Validate monitor config and optionally test webhook connectivity."""
    from miner_tools.config import load_config

    config_file = ctx.obj["config_path"]
    try:
        _, subnets = load_config(config_file)
        console.print(f"[green]Config is valid.[/green] {len(subnets)} subnet(s) configured.")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc

    if not check_webhooks:
        return

    import aiohttp

    from miner_tools.alerter import validate_webhooks

    console.print("\n[dim]Testing webhook connectivity...[/dim]")

    async def _check():
        async with aiohttp.ClientSession() as session:
            return await validate_webhooks(subnets, session)

    results = _run_async(_check())
    for subnet in subnets:
        for channel, valid in results.get(subnet.netuid, {}).items():
            icon = "[green]pass[/green]" if valid else "[red]fail[/red]"
            console.print(f"  SN{subnet.netuid} {channel}: {icon}")


@monitor.command("validate")
@click.option("--check-webhooks", is_flag=True, help="Also test webhook connectivity.")
@click.pass_context
def monitor_validate(ctx, check_webhooks: bool) -> None:
    """Validate monitor config and optionally test webhook connectivity."""
    _monitor_validate_impl(ctx, check_webhooks)


@cli.command("validate")
@click.option("--check-webhooks", is_flag=True, help="Also test webhook connectivity.")
@click.pass_context
def legacy_validate(ctx, check_webhooks: bool) -> None:
    """Compatibility alias for `monitor validate`."""
    _monitor_validate_impl(ctx, check_webhooks)


def _monitor_config_show_impl(ctx) -> None:
    """Show full monitor configuration including auto-register and deregister settings."""
    global_cfg, subnets = _load_monitor_config(ctx)
    config_file = ctx.obj["config_path"]

    console.print(Panel(f"[bold]Config file:[/bold] {config_file}", border_style="blue"))
    console.print("\n[bold]Global Settings:[/bold]")
    console.print(f"  Network:            {global_cfg.subtensor_network}")
    console.print(f"  Endpoint:           {global_cfg.subtensor_endpoint or 'default'}")
    console.print(f"  Price source:       {global_cfg.price_source}")
    console.print(f"  taostats API key:   {'set' if global_cfg.taostats_api_key else 'not set'}")
    console.print(f"  Data dir:           {global_cfg.data_dir}")
    console.print(f"  Log level:          {global_cfg.log_level}")
    console.print(f"  Trend window:       {global_cfg.trend_window} readings")
    console.print(f"  Alert cooldown:     {global_cfg.alert_cooldown_seconds}s")
    console.print(
        f"  Wallet:             {global_cfg.wallet.name}/{global_cfg.wallet.hotkey} "
        f"({global_cfg.wallet.path})"
    )

    console.print(f"\n[bold]Subnets ({len(subnets)}):[/bold]")
    for subnet in subnets:
        status_text = "[green]enabled[/green]" if subnet.enabled else "[dim]disabled[/dim]"
        channels = []
        if subnet.alerts.discord:
            channels.append("Discord")
        if subnet.alerts.telegram:
            channels.append("Telegram")
        channel_text = ", ".join(channels) if channels else "[red]none[/red]"
        console.print(
            f"  [{subnet.netuid:>3}] {subnet.label:<20} "
            f"threshold={subnet.price_threshold_tao:.4f} TAO "
            f"interval={subnet.poll_interval_seconds}s "
            f"alerts={channel_text} {status_text}"
        )

        extras = []
        if subnet.max_spend_tao:
            extras.append(f"max_spend={subnet.max_spend_tao:.4f} TAO")
        if subnet.auto_register:
            extras.append("[green]auto_register=ON[/green]")
        if subnet.adaptive_polling:
            extras.append(f"adaptive={subnet.min_poll_interval_seconds}-{subnet.poll_interval_seconds}s")
        if subnet.floor_detection:
            extras.append(f"floor_window={subnet.floor_window}")
        if subnet.signal_file:
            extras.append(f"signal={subnet.signal_file}")
        if subnet.deregister_entries:
            names = ", ".join(entry.display_name for entry in subnet.deregister_entries)
            extras.append(f"deregister=[{names}]")
        if extras:
            console.print(f"         {', '.join(extras)}")


@monitor.command("config")
@click.pass_context
def monitor_config_show(ctx) -> None:
    """Show full monitor configuration."""
    _monitor_config_show_impl(ctx)


@cli.command("config-show")
@click.pass_context
def legacy_config_show(ctx) -> None:
    """Compatibility alias for `monitor config`."""
    _monitor_config_show_impl(ctx)


@monitor.command("wallet")
@click.pass_context
def monitor_wallet(ctx) -> None:
    """Show monitor wallet status, balance, and configured registrations."""
    from miner_tools.fetcher import close_subtensor, get_wallet_info_sdk

    global_cfg, subnets = _load_monitor_config(ctx)
    wallet_cfg = global_cfg.wallet
    console.print(
        Panel(
            f"[bold]Wallet: {wallet_cfg.name}/{wallet_cfg.hotkey}[/bold]\n"
            f"Path: {wallet_cfg.path}",
            border_style="blue",
        )
    )

    try:
        info = get_wallet_info_sdk(
            wallet_cfg,
            global_cfg.subtensor_network,
            global_cfg.subtensor_endpoint,
        )
    except Exception as exc:
        console.print(f"[red]Error reading wallet:[/red] {exc}")
        close_subtensor()
        return

    if info["coldkey_exists"]:
        console.print(f"\n[bold]Coldkey:[/bold] [green]{info['coldkey_ss58']}[/green]")
        if info["balance_tao"] is not None:
            balance = info["balance_tao"]
            style = "green" if balance > 0.1 else "yellow" if balance > 0 else "red"
            console.print(f"  Balance: [{style}]{balance:.6f} TAO[/{style}]")
        else:
            console.print("  Balance: [dim]could not fetch[/dim]")
    else:
        console.print("\n[bold]Coldkey:[/bold] [red]NOT FOUND[/red]")
        console.print(
            f"  [dim]Create with: btcli wallet new_coldkey --wallet.name {wallet_cfg.name} "
            f"--wallet.path {wallet_cfg.path}[/dim]"
        )

    if info["hotkey_exists"]:
        console.print(f"\n[bold]Hotkey:[/bold] [green]{info['hotkey_ss58']}[/green]")
        if info["registered_on"]:
            registered_on = ", ".join(str(sn) for sn in info["registered_on"])
            console.print(f"  Registered on: SN{registered_on}")
        else:
            console.print("  Registered on: [dim]none[/dim]")
    else:
        console.print("\n[bold]Hotkey:[/bold] [red]NOT FOUND[/red]")
        console.print(
            f"  [dim]Create with: btcli wallet new_hotkey --wallet.name {wallet_cfg.name} "
            f"--wallet.hotkey {wallet_cfg.hotkey} --wallet.path {wallet_cfg.path}[/dim]"
        )

    auto_reg = [subnet for subnet in subnets if subnet.auto_register]
    if auto_reg:
        console.print("\n[bold]Auto-register enabled for:[/bold]")
        for subnet in auto_reg:
            console.print(
                f"  SN{subnet.netuid} ({subnet.label}) - "
                f"threshold {subnet.price_threshold_tao} TAO"
            )

    dereg = [(subnet, entry) for subnet in subnets for entry in subnet.deregister_entries]
    if dereg:
        console.print(f"\n[bold]Deregister monitor:[/bold] {len(dereg)} hotkey(s)")

    close_subtensor()


# ============================================================================
# NETWORK Commands
# ============================================================================


@cli.group()
def network():
    """Network commands."""
    pass


@network.command("register")
@click.option("--subnet", "-s", type=int, required=True, help="Subnet ID")
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default=None)
@click.option("--wallet", "-w", type=str, default=None)
@click.pass_context
def network_register(ctx, subnet: int, network: str | None, wallet: str | None):
    """Register wallet on subnet (burn TAO)."""
    bt = get_bittensor()
    raw_config = ctx.obj.get("raw_config", {})
    network = _resolve_network(raw_config, network)
    wallet = _resolve_wallet_name(raw_config, subnet, wallet)
    net = _network_key(network)

    console.print(f"[yellow]Registering {wallet} on subnet {subnet} ({network})...[/yellow]")

    try:
        wallet_obj = bt.Wallet(name=wallet)
        subtensor = bt.Subtensor(network=net)
        success = subtensor.register(wallet=wallet_obj, netuid=subnet)

        if success:
            console.print("[green]✓ Registered successfully![/green]")
        else:
            console.print("[red]Registration failed[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@network.command("info")
@click.option("--subnet", "-s", type=int, default=13)
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default=None)
@click.pass_context
def network_info(ctx, subnet: int, network: str | None):
    """Show subnet info from chain."""
    bt = get_bittensor()
    network = _resolve_network(ctx.obj.get("raw_config", {}), network)
    net = _network_key(network)

    try:
        subtensor = bt.Subtensor(network=net)
        meta = subtensor.metagraph(subnet)

        table = Table(title=f"SN{subnet} on {network}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Miners", str(len(meta.hotkeys)))
        table.add_row("Max", str(meta.n))
        table.add_row("Emission", f"{float(meta.emission) * 100:.1f}%")

        # Top validators
        stakes = list(enumerate(meta.stake))
        stakes.sort(key=lambda x: float(x[1]), reverse=True)
        if stakes[0][1] > 0:
            table.add_row("Top Stake", f"τ{float(stakes[0][1]):.0f}")

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@network.command("price")
@click.option("--subnet", "-s", type=int, default=None, help="Optional subnet context for display.")
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default=None)
@click.pass_context
def network_price(ctx, subnet: int | None, network: str | None):
    """Show current burn cost for subnet registration on a network."""
    bt = get_bittensor()
    raw_config = ctx.obj.get("raw_config", {})
    network = _resolve_network(raw_config, network)
    net = _network_key(network)

    try:
        subtensor = bt.Subtensor(network=net)
        price = subtensor.get_subnet_burn_cost()
        title = f"{network} registration burn"
        if subnet is not None:
            title += f" (context SN{subnet})"
        console.print(f"[bold]{title}: {_format_balance(price)}[/bold]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ============================================================================
# Workstream Commands
# ============================================================================


@cli.group("workstream")
def workstream_group():
    """Admin commands for the durable workstream and its HTTP boundary."""
    pass


@workstream_group.command("serve")
@click.option("--host", default=None, help="Override JARVIS_WORKSTREAM_HOST.")
@click.option("--port", type=int, default=None, help="Override JARVIS_WORKSTREAM_PORT.")
@click.option("--reload", is_flag=True, help="Enable uvicorn reload for local development.")
def workstream_serve(host: str | None, port: int | None, reload: bool):
    """Serve the workstream HTTP boundary using durable local SQLite stores."""
    import uvicorn

    from workstream.api.runtime import create_default_app, runtime_configuration

    config = runtime_configuration()
    if config["config_error"]:
        raise click.ClickException(str(config["config_error"]))
    resolved_host = host or str(config["host"])
    resolved_port = int(config["port"]) if port is None else port

    console.print(
        Panel.fit(
            "\n".join(
                [
                    "Jarvis Workstream",
                    f"Host: {resolved_host}",
                    f"Port: {resolved_port}",
                    "Store: SQLite",
                    "Operators: API only; no CLI access",
                ]
            ),
            border_style="cyan",
        )
    )
    if reload:
        uvicorn.run(
            "workstream.api.runtime:create_default_app",
            host=resolved_host,
            port=resolved_port,
            reload=reload,
            factory=True,
        )
        return

    app = create_default_app()
    uvicorn.run(app, host=resolved_host, port=resolved_port, reload=False)


@workstream_group.command("status")
@click.option("--workstream-db-path", type=click.Path(path_type=Path), default=None)
@click.option("--sn13-db-path", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def workstream_status(
    workstream_db_path: Path | None,
    sn13_db_path: Path | None,
    json_output: bool,
):
    """Show workstream runtime configuration and current durable store counts."""
    from subnets.sn13.storage import SQLiteStorage
    from workstream.api.runtime import runtime_configuration
    from workstream.sqlite_store import SQLiteWorkstream

    env_values = dict(os.environ)
    if workstream_db_path is not None:
        env_values["JARVIS_WORKSTREAM_DB_PATH"] = str(workstream_db_path)
    if sn13_db_path is not None:
        env_values["JARVIS_SN13_DB_PATH"] = str(sn13_db_path)

    config = runtime_configuration(env_values)
    resolved_workstream_path = Path(str(config["workstream_db_path"]))
    resolved_sn13_path = Path(str(config["sn13_db_path"]))

    workstream_summary = {
        "total_tasks": 0,
        "open_tasks": 0,
        "completed_tasks": 0,
        "cancelled_tasks": 0,
        "available_now": 0,
    }
    if resolved_workstream_path.exists():
        workstream_summary = SQLiteWorkstream(resolved_workstream_path).summary()

    sn13_summary = {
        "canonical_entities": 0,
        "accepted_submissions": 0,
        "rejected_submissions": 0,
        "duplicate_observations": 0,
        "operators_seen": 0,
    }
    if resolved_sn13_path.exists():
        sn13_summary = SQLiteStorage(resolved_sn13_path).audit_summary()

    payload = {
        **config,
        "workstream_db_exists": resolved_workstream_path.exists(),
        "sn13_db_exists": resolved_sn13_path.exists(),
        **workstream_summary,
        **sn13_summary,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title="Jarvis Workstream Status")
    table.add_column("Fact", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Workstream DB", str(resolved_workstream_path))
    table.add_row("Workstream DB exists", "yes" if resolved_workstream_path.exists() else "no")
    table.add_row("SN13 DB", str(resolved_sn13_path))
    table.add_row("SN13 DB exists", "yes" if resolved_sn13_path.exists() else "no")
    table.add_row("Host", str(config["host"]))
    table.add_row("Port", str(config["port"]))
    table.add_row("Auth required", "yes" if config["auth_required"] else "no")
    table.add_row("Configured operators", str(config["configured_operator_count"]))
    table.add_row("Operator IDs", ", ".join(config["configured_operator_ids"]) or "-")
    table.add_row("Clock skew", f"{config['max_clock_skew_seconds']}s")
    table.add_row("Config error", str(config["config_error"] or "-"))
    table.add_row("Open tasks", str(payload["open_tasks"]))
    table.add_row("Completed tasks", str(payload["completed_tasks"]))
    table.add_row("Cancelled tasks", str(payload["cancelled_tasks"]))
    table.add_row("Available now", str(payload["available_now"]))
    table.add_row("Canonical entities", str(payload["canonical_entities"]))
    table.add_row("Accepted submissions", str(payload["accepted_submissions"]))
    table.add_row("Rejected submissions", str(payload["rejected_submissions"]))
    table.add_row("Duplicate observations", str(payload["duplicate_observations"]))
    table.add_row("Operators seen", str(payload["operators_seen"]))
    console.print(table)


@workstream_group.command("tasks")
@click.option("--workstream-db-path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--status",
    "task_status",
    type=click.Choice(["all", "open", "completed", "cancelled"]),
    default="all",
    show_default=True,
)
@click.option("--subnet", type=str, default=None)
@click.option("--source", type=str, default=None)
@click.option("--limit", type=int, default=50, show_default=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def workstream_tasks(
    workstream_db_path: Path | None,
    task_status: str,
    subnet: str | None,
    source: str | None,
    limit: int,
    json_output: bool,
):
    """List tasks currently stored in the durable workstream."""
    from workstream.models import WorkstreamTaskStatus
    from workstream.sqlite_store import SQLiteWorkstream

    resolved_workstream_path = workstream_db_path or _workstream_db_path()
    tasks = []
    if resolved_workstream_path.exists():
        workstream = SQLiteWorkstream(resolved_workstream_path)
        status_filter = None
        if task_status != "all":
            status_filter = WorkstreamTaskStatus(task_status)
        tasks = workstream.list_tasks(
            status=status_filter,
            subnet=subnet,
            source=source,
            limit=limit,
        )

    payload = {
        "workstream_db_path": str(resolved_workstream_path),
        "task_count": len(tasks),
        "tasks": [task.model_dump(mode="json") for task in tasks],
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title="Jarvis Workstream Tasks")
    table.add_column("Task", style="cyan")
    table.add_column("Subnet", style="green")
    table.add_column("Source", style="green")
    table.add_column("Target", style="yellow")
    table.add_column("Status", style="magenta")
    table.add_column("Accepted", style="white")
    table.add_column("Qty", justify="right")
    for task in tasks:
        table.add_row(
            task.task_id,
            task.subnet,
            task.source,
            task.contract.get("label") or task.contract.get("keyword") or "-",
            task.status.value,
            f"{task.accepted_count}/{task.acceptance_cap}",
            str(task.contract.get("quantity_target") or "-"),
        )
    console.print(table)
    console.print(f"[cyan]Workstream DB:[/cyan] {resolved_workstream_path}")


# ============================================================================
# SN13 Commands
# ============================================================================


@cli.group()
def sn13():
    """Subnet 13 operational commands."""
    pass


@sn13.group()
def dd():
    """Dynamic Desirability / Gravity commands."""
    pass


@dd.command("show")
@click.option("--file", "dd_file", type=click.Path(path_type=Path), default=None)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
@click.option("--sample-dd", is_flag=True, help="Use built-in sample DD records for CI/dev only.")
def sn13_dd_show(dd_file: Path | None, cache_dir: Path | None, sample_dd: bool):
    """Show Gravity/DD jobs that would drive Jarvis operator demand."""
    from subnets.sn13.simulator import load_snapshot

    cache_dir = cache_dir or _sn13_gravity_cache_dir()
    try:
        snapshot = load_snapshot(dd_file, cache_dir=cache_dir, use_sample=sample_dd)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title="SN13 Dynamic Desirability Jobs")
    table.add_column("Job", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Label", style="yellow")
    table.add_column("Keyword", style="magenta")
    table.add_column("Weight", justify="right")
    table.add_column("Window", style="white")
    for job in snapshot.jobs:
        if job.start_datetime or job.end_datetime:
            window = f"{job.start_datetime or '-'} -> {job.end_datetime or '-'}"
        else:
            window = "recent/default"
        table.add_row(
            job.job_id,
            job.source.value,
            job.label or "-",
            job.keyword or "-",
            f"{job.weight:.2f}",
            window,
        )
    console.print(table)
    console.print(f"[cyan]Source:[/cyan] {snapshot.source_ref or 'unknown'}")
    if sample_dd:
        console.print(
            "[yellow]Sample DD mode is for CI/dev only; "
            "refresh real Gravity before planning work.[/yellow]"
        )


@dd.command("refresh")
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
@click.option("--url", type=str, default=None, help="Override Gravity aggregate URL.")
@click.option("--timeout-seconds", type=int, default=30, show_default=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_dd_refresh(
    cache_dir: Path | None,
    url: str | None,
    timeout_seconds: int,
    json_output: bool,
):
    """Fetch real Gravity/DD jobs into the local Jarvis cache."""
    from subnets.sn13.gravity import GRAVITY_TOTAL_URL, GravityFetchError, refresh_gravity_cache

    cache_dir = cache_dir or _sn13_gravity_cache_dir()
    source_url = url or GRAVITY_TOTAL_URL
    try:
        result = refresh_gravity_cache(
            cache_dir=cache_dir,
            url=source_url,
            timeout_seconds=timeout_seconds,
        )
    except (GravityFetchError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    payload = {
        "cache_path": str(result.cache_path),
        "metadata_path": str(result.metadata_path),
        "source_url": result.metadata.source_url,
        "fetched_at": result.metadata.fetched_at.isoformat(),
        "record_count": result.metadata.record_count,
        "sha256": result.metadata.sha256,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title="SN13 Gravity Cache Refreshed")
    table.add_column("Fact", style="cyan")
    table.add_column("Value", style="green")
    for key, value in payload.items():
        table.add_row(key, str(value))
    console.print(table)


@sn13.group()
def plan():
    """Plan personal-operator work from SN13 policy and DD."""
    pass


@sn13.group()
def economics():
    """Estimate SN13 task cost, margin, and take/refuse gates."""
    pass


@economics.command("estimate")
@click.option("--source", type=click.Choice(["X", "REDDIT", "YOUTUBE"]), required=True)
@click.option("--label", type=str, default=None)
@click.option("--keyword", type=str, default=None)
@click.option("--desirability-job-id", type=str, default=None)
@click.option("--desirability-weight", type=float, default=None)
@click.option("--quantity-target", type=int, default=None)
@click.option("--max-task-cost", type=float, default=None)
@click.option("--expected-reward", type=float, default=None)
@click.option("--expected-submitted", type=int, default=None)
@click.option("--expected-accepted", type=int, default=None)
@click.option("--duplicate-rate", type=float, default=None)
@click.option("--rejection-rate", type=float, default=None)
@click.option("--validation-pass-probability", type=float, default=None)
@click.option(
    "--payout-basis",
    type=click.Choice(["accepted_scorable_record", "accepted_record", "flat_task", "none"]),
    default=None,
)
@click.option("--operator-payout", type=float, default=0.0, show_default=True)
@click.option("--scraper-provider-cost", type=float, default=0.0, show_default=True)
@click.option("--proxy-cost", type=float, default=0.0, show_default=True)
@click.option("--compute-cost", type=float, default=0.0, show_default=True)
@click.option("--local-storage-cost", type=float, default=0.0, show_default=True)
@click.option("--export-staging-cost", type=float, default=0.0, show_default=True)
@click.option("--upload-bandwidth-cost", type=float, default=0.0, show_default=True)
@click.option("--retry-cost", type=float, default=0.0, show_default=True)
@click.option("--risk-reserve", type=float, default=0.0, show_default=True)
@click.option("--jarvis-archive-bucket-cost", type=float, default=0.0, show_default=True)
@click.option(
    "--s3-mode",
    type=click.Choice(["upstream_presigned", "jarvis_archive", "upstream_and_jarvis_archive"]),
    default="upstream_presigned",
    show_default=True,
)
@click.option("--currency", type=str, default="USD", show_default=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_economics_estimate(
    source: str,
    label: str | None,
    keyword: str | None,
    desirability_job_id: str | None,
    desirability_weight: float | None,
    quantity_target: int | None,
    max_task_cost: float | None,
    expected_reward: float | None,
    expected_submitted: int | None,
    expected_accepted: int | None,
    duplicate_rate: float | None,
    rejection_rate: float | None,
    validation_pass_probability: float | None,
    payout_basis: str | None,
    operator_payout: float,
    scraper_provider_cost: float,
    proxy_cost: float,
    compute_cost: float,
    local_storage_cost: float,
    export_staging_cost: float,
    upload_bandwidth_cost: float,
    retry_cost: float,
    risk_reserve: float,
    jarvis_archive_bucket_cost: float,
    s3_mode: str,
    currency: str,
    json_output: bool,
):
    """Estimate whether a planned SN13 task is economically safe to publish."""
    from pydantic import ValidationError

    from subnets.sn13.economics import TaskEconomicsInput, evaluate_task_economics
    from subnets.sn13.models import DataSource

    publication_economics = _sn13_publication_economics_config(
        max_task_cost=max_task_cost,
        expected_reward=expected_reward,
        expected_submitted=expected_submitted,
        expected_accepted=expected_accepted,
        duplicate_rate=duplicate_rate,
        rejection_rate=rejection_rate,
        validation_pass_probability=validation_pass_probability,
        payout_basis=payout_basis,
        operator_payout=operator_payout,
        scraper_provider_cost=scraper_provider_cost,
        proxy_cost=proxy_cost,
        compute_cost=compute_cost,
        local_storage_cost=local_storage_cost,
        export_staging_cost=export_staging_cost,
        upload_bandwidth_cost=upload_bandwidth_cost,
        retry_cost=retry_cost,
        risk_reserve=risk_reserve,
        jarvis_archive_bucket_cost=jarvis_archive_bucket_cost,
        s3_mode=s3_mode,
        currency=currency,
    )

    try:
        task = TaskEconomicsInput(
            source=DataSource(source),
            label=label,
            keyword=keyword,
            desirability_job_id=desirability_job_id,
            desirability_weight=desirability_weight,
            quantity_target=quantity_target,
            max_task_cost=publication_economics.max_task_cost,
            expected_reward_value=publication_economics.expected_reward_value,
            expected_submitted_records=publication_economics.expected_submitted_records,
            expected_accepted_scorable_records=(
                publication_economics.expected_accepted_scorable_records
            ),
            expected_duplicate_rate=publication_economics.expected_duplicate_rate,
            expected_rejection_rate=publication_economics.expected_rejection_rate,
            validation_pass_probability=publication_economics.validation_pass_probability,
            payout_basis=publication_economics.payout_basis,
            costs=publication_economics.costs,
            s3_storage_mode=publication_economics.s3_storage_mode,
            currency=publication_economics.currency,
        )
    except ValidationError as exc:
        raise click.ClickException(str(exc)) from exc

    decision = evaluate_task_economics(task)
    payload = {
        "source": source,
        "target": label or keyword,
        "currency": decision.currency,
        "can_take_task": decision.can_take_task,
        "blockers": decision.blockers,
        "warnings": decision.warnings,
        "total_task_cost": decision.total_task_cost,
        "accepted_scorable_unit_cost": decision.accepted_scorable_unit_cost,
        "quality_adjusted_unit_cost": decision.quality_adjusted_unit_cost,
        "expected_margin": decision.expected_margin,
        "s3_storage_cost_owner": decision.s3_storage_cost_owner,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title="SN13 Task Economics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Can take task", "yes" if decision.can_take_task else "[red]no[/red]")
    table.add_row("Total task cost", f"{decision.total_task_cost:.4f} {decision.currency}")
    table.add_row(
        "Accepted scorable unit cost",
        (
            f"{decision.accepted_scorable_unit_cost:.8f} {decision.currency}"
            if decision.accepted_scorable_unit_cost is not None
            else "unknown"
        ),
    )
    table.add_row(
        "Quality-adjusted unit cost",
        (
            f"{decision.quality_adjusted_unit_cost:.8f} {decision.currency}"
            if decision.quality_adjusted_unit_cost is not None
            else "unknown"
        ),
    )
    table.add_row(
        "Expected margin",
        (
            f"{decision.expected_margin:.4f} {decision.currency}"
            if decision.expected_margin is not None
            else "unknown"
        ),
    )
    table.add_row("S3 storage owner", decision.s3_storage_cost_owner)
    table.add_row("Blockers", ", ".join(decision.blockers) or "-")
    table.add_row("Warnings", ", ".join(decision.warnings) or "-")
    console.print(table)


@economics.command("s3-cost")
@click.option("--storage-gb-month", type=float, default=0.0, show_default=True)
@click.option("--storage-usd-per-gb-month", type=float, default=0.0, show_default=True)
@click.option("--put-requests", type=int, default=0, show_default=True)
@click.option("--put-usd-per-1000", type=float, default=0.0, show_default=True)
@click.option("--get-requests", type=int, default=0, show_default=True)
@click.option("--get-usd-per-1000", type=float, default=0.0, show_default=True)
@click.option("--retrieval-gb", type=float, default=0.0, show_default=True)
@click.option("--retrieval-usd-per-gb", type=float, default=0.0, show_default=True)
@click.option("--transfer-out-gb", type=float, default=0.0, show_default=True)
@click.option("--transfer-out-usd-per-gb", type=float, default=0.0, show_default=True)
@click.option("--lifecycle-transition-requests", type=int, default=0, show_default=True)
@click.option("--lifecycle-transition-usd-per-1000", type=float, default=0.0, show_default=True)
@click.option("--monitoring-object-count", type=int, default=0, show_default=True)
@click.option("--monitoring-usd-per-1000-objects", type=float, default=0.0, show_default=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_economics_s3_cost(
    storage_gb_month: float,
    storage_usd_per_gb_month: float,
    put_requests: int,
    put_usd_per_1000: float,
    get_requests: int,
    get_usd_per_1000: float,
    retrieval_gb: float,
    retrieval_usd_per_gb: float,
    transfer_out_gb: float,
    transfer_out_usd_per_gb: float,
    lifecycle_transition_requests: int,
    lifecycle_transition_usd_per_1000: float,
    monitoring_object_count: int,
    monitoring_usd_per_1000_objects: float,
    json_output: bool,
):
    """Calculate Jarvis-owned archive S3 cost from explicit usage and unit prices."""
    from subnets.sn13.economics import S3ArchiveCostInput, calculate_s3_archive_cost

    usage = S3ArchiveCostInput(
        storage_gb_month=storage_gb_month,
        storage_usd_per_gb_month=storage_usd_per_gb_month,
        put_requests=put_requests,
        put_usd_per_1000=put_usd_per_1000,
        get_requests=get_requests,
        get_usd_per_1000=get_usd_per_1000,
        retrieval_gb=retrieval_gb,
        retrieval_usd_per_gb=retrieval_usd_per_gb,
        transfer_out_gb=transfer_out_gb,
        transfer_out_usd_per_gb=transfer_out_usd_per_gb,
        lifecycle_transition_requests=lifecycle_transition_requests,
        lifecycle_transition_usd_per_1000=lifecycle_transition_usd_per_1000,
        monitoring_object_count=monitoring_object_count,
        monitoring_usd_per_1000_objects=monitoring_usd_per_1000_objects,
    )
    estimate = calculate_s3_archive_cost(usage)
    payload = estimate.model_dump(mode="json")
    payload["total"] = estimate.total
    payload["note"] = (
        "This is Jarvis-owned archive cost only. Upstream SN13 validation upload uses "
        "the upstream presigned destination; Jarvis still pays local export, outbound "
        "bandwidth, retries, and archive costs when archive mode is enabled."
    )

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title="SN13 Jarvis Archive S3 Cost")
    table.add_column("Component", style="cyan")
    table.add_column("USD", style="green")
    table.add_row("Storage", f"{estimate.storage_cost:.6f}")
    table.add_row("PUT requests", f"{estimate.put_request_cost:.6f}")
    table.add_row("GET requests", f"{estimate.get_request_cost:.6f}")
    table.add_row("Retrieval", f"{estimate.retrieval_cost:.6f}")
    table.add_row("Transfer out", f"{estimate.transfer_out_cost:.6f}")
    table.add_row("Lifecycle transitions", f"{estimate.lifecycle_transition_cost:.6f}")
    table.add_row("Monitoring", f"{estimate.monitoring_cost:.6f}")
    table.add_row("Total", f"{estimate.total:.6f}")
    console.print(table)
    console.print(
        "[yellow]Archive cost only. Use `sn13 economics estimate` to include "
        "operator, provider, export, bandwidth, retry, and risk costs.[/yellow]"
    )


@plan.command("tasks")
@click.option("--dd-file", type=click.Path(path_type=Path), default=None)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
@click.option("--sample-dd", is_flag=True, help="Use built-in sample DD records for CI/dev only.")
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--target-items", type=int, default=5, show_default=True)
@click.option("--recent-buckets", type=int, default=1, show_default=True)
@click.option("--max-tasks", type=int, default=10, show_default=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_plan_tasks(
    dd_file: Path | None,
    cache_dir: Path | None,
    sample_dd: bool,
    db_path: Path | None,
    target_items: int,
    recent_buckets: int,
    max_tasks: int,
    json_output: bool,
):
    """Plan operator tasks from Gravity/DD and current SQLite coverage."""
    try:
        db_path, snapshot, tasks = _sn13_plan_context(
            dd_file=dd_file,
            cache_dir=cache_dir,
            sample_dd=sample_dd,
            db_path=db_path,
            target_items=target_items,
            recent_buckets=recent_buckets,
            max_tasks=max_tasks,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "db_path": str(db_path),
                    "desirability_source": snapshot.source_ref,
                    "desirability_jobs": len(snapshot.jobs),
                    "tasks": [
                        task.to_workstream_contract().model_dump(mode="json")
                        for task in tasks
                    ],
                },
                indent=2,
            )
        )
        return

    table = Table(title="SN13 Planned Operator Tasks")
    table.add_column("Task", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Label", style="yellow")
    table.add_column("Bucket", justify="right")
    table.add_column("Qty", justify="right")
    table.add_column("Priority", justify="right")
    table.add_column("Mode", style="magenta")
    for task in tasks:
        table.add_row(
            task.task_id,
            task.source,
            task.label or task.keyword or "-",
            str(task.time_bucket),
            str(task.quantity_target),
            f"{task.priority:.3f}",
            "open",
        )
    console.print(table)
    console.print(f"[cyan]Database:[/cyan] {db_path}")
    console.print(f"[cyan]DD source:[/cyan] {snapshot.source_ref or 'unknown'}")
    console.print("[cyan]Publication:[/cyan] open competitive intake in workstream mode")


@plan.command("publish")
@_sn13_publication_economics_options
@click.option("--dd-file", type=click.Path(path_type=Path), default=None)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
@click.option("--sample-dd", is_flag=True, help="Use built-in sample DD records for CI/dev only.")
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--workstream-db-path", type=click.Path(path_type=Path), default=None)
@click.option("--target-items", type=int, default=5, show_default=True)
@click.option("--recent-buckets", type=int, default=1, show_default=True)
@click.option("--max-tasks", type=int, default=10, show_default=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_plan_publish(
    dd_file: Path | None,
    cache_dir: Path | None,
    sample_dd: bool,
    db_path: Path | None,
    workstream_db_path: Path | None,
    target_items: int,
    recent_buckets: int,
    max_tasks: int,
    max_task_cost: float | None,
    expected_reward: float | None,
    expected_submitted: int | None,
    expected_accepted: int | None,
    duplicate_rate: float | None,
    rejection_rate: float | None,
    validation_pass_probability: float | None,
    payout_basis: str | None,
    operator_payout: float,
    scraper_provider_cost: float,
    proxy_cost: float,
    compute_cost: float,
    local_storage_cost: float,
    export_staging_cost: float,
    upload_bandwidth_cost: float,
    retry_cost: float,
    risk_reserve: float,
    jarvis_archive_bucket_cost: float,
    s3_mode: str,
    currency: str,
    json_output: bool,
):
    """Publish planned SN13 tasks into the durable workstream store."""
    from subnets.sn13.publication import evaluate_publication_batch
    from subnets.sn13.workstream import publish_sn13_tasks
    from workstream.sqlite_store import SQLiteWorkstream

    try:
        resolved_db_path, snapshot, tasks = _sn13_plan_context(
            dd_file=dd_file,
            cache_dir=cache_dir,
            sample_dd=sample_dd,
            db_path=db_path,
            target_items=target_items,
            recent_buckets=recent_buckets,
            max_tasks=max_tasks,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    economics = _sn13_publication_economics_config(
        max_task_cost=max_task_cost,
        expected_reward=expected_reward,
        expected_submitted=expected_submitted,
        expected_accepted=expected_accepted,
        duplicate_rate=duplicate_rate,
        rejection_rate=rejection_rate,
        validation_pass_probability=validation_pass_probability,
        payout_basis=payout_basis,
        operator_payout=operator_payout,
        scraper_provider_cost=scraper_provider_cost,
        proxy_cost=proxy_cost,
        compute_cost=compute_cost,
        local_storage_cost=local_storage_cost,
        export_staging_cost=export_staging_cost,
        upload_bandwidth_cost=upload_bandwidth_cost,
        retry_cost=retry_cost,
        risk_reserve=risk_reserve,
        jarvis_archive_bucket_cost=jarvis_archive_bucket_cost,
        s3_mode=s3_mode,
        currency=currency,
    )
    publication = evaluate_publication_batch(tasks, economics=economics)

    resolved_workstream_db_path = workstream_db_path or _workstream_db_path()
    workstream = SQLiteWorkstream(resolved_workstream_db_path)
    published = publish_sn13_tasks(list(publication.publishable_tasks), workstream=workstream)

    payload = {
        "db_path": str(resolved_db_path),
        "workstream_db_path": str(resolved_workstream_db_path),
        "desirability_source": snapshot.source_ref,
        "desirability_jobs": len(snapshot.jobs),
        "planned_tasks": len(tasks),
        "published_tasks": len(published),
        "refused_tasks": len(publication.refused_tasks),
        "publication_mode": "open_competitive_intake",
        "task_ids": [task.task_id for task in published],
        "refusals": [
            assessment.model_dump(mode="json") for assessment in publication.refused_tasks
        ],
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title="SN13 Workstream Publication")
    table.add_column("Fact", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("SN13 DB", str(resolved_db_path))
    table.add_row("Workstream DB", str(resolved_workstream_db_path))
    table.add_row("DD source", snapshot.source_ref or "unknown")
    table.add_row("DD jobs", str(len(snapshot.jobs)))
    table.add_row("Planned tasks", str(len(tasks)))
    table.add_row("Published tasks", str(len(published)))
    table.add_row("Refused tasks", str(len(publication.refused_tasks)))
    table.add_row("Publication mode", "open competitive intake")
    console.print(table)
    if published:
        task_table = Table(title="Published SN13 Tasks")
        task_table.add_column("Task", style="cyan")
        task_table.add_column("Source", style="green")
        task_table.add_column("Target", style="yellow")
        task_table.add_column("Qty", justify="right")
        task_table.add_column("Mode", style="magenta")
        for task in published:
            task_table.add_row(
                task.task_id,
                task.source,
                task.contract.get("label") or task.contract.get("keyword") or "-",
                str(task.contract["quantity_target"]),
                "open",
            )
        console.print(task_table)
    if publication.refused_tasks:
        refusal_table = Table(title="Economically Refused SN13 Tasks")
        refusal_table.add_column("Task", style="cyan")
        refusal_table.add_column("Target", style="yellow")
        refusal_table.add_column("Blockers", style="red")
        for assessment in publication.refused_tasks:
            refusal_table.add_row(
                assessment.task_id,
                assessment.target or "-",
                ", ".join(assessment.blockers) or "-",
            )
        console.print(refusal_table)


@sn13.command("readiness")
@click.option("--network", "-n", type=click.Choice(["mainnet", "testnet"]), default=None)
@click.option("--wallet", "-w", type=str, default=None)
@click.option("--hotkey", type=str, default=None)
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--disk-path", type=click.Path(path_type=Path), default=None)
@click.option("--export-root", type=click.Path(path_type=Path), default=None)
@click.option("--skip-chain", is_flag=True, help="Do not query chain registration.")
@click.option("--registered", is_flag=True, help="Assume hotkey is registered for local checks.")
@click.option("--json-output", "--json", "json_output", is_flag=True)
@click.pass_context
def sn13_readiness(
    ctx,
    network: str | None,
    wallet: str | None,
    hotkey: str | None,
    db_path: Path | None,
    disk_path: Path | None,
    export_root: Path | None,
    skip_chain: bool,
    registered: bool,
    json_output: bool,
):
    """Show whether Jarvis runtime can serve SN13, intake data, and export."""
    from subnets.sn13.readiness import (
        ReadinessStatus,
        SN13Capability,
        SN13RuntimeState,
        evaluate_sn13_readiness,
    )
    from subnets.sn13.storage import SQLiteStorage

    raw_config = ctx.obj.get("raw_config", {})
    network = _resolve_network(raw_config, network)
    wallet = _resolve_wallet_name(raw_config, 13, wallet)
    hotkey = _resolve_hotkey_name(raw_config, 13, hotkey)
    db_path = db_path or _sn13_db_path()
    disk_path = disk_path or db_path.parent
    export_root = export_root or _sn13_export_root()

    state = _load_state(13)
    listener_running = bool(state.get("running")) and _is_pid_running(state.get("pid"))
    disk_path.mkdir(parents=True, exist_ok=True)
    disk_free_gb = shutil.disk_usage(disk_path).free / GB
    db_healthy = SQLiteStorage(db_path).health_check()
    parquet_export_available = export_root.exists() and any(export_root.rglob("*.parquet"))

    hotkey_registered = registered
    hotkey_address = None
    chain_error = None
    if not skip_chain and not registered:
        try:
            hotkey_registered, hotkey_address, chain_error = _query_hotkey_registration(
                wallet_name=wallet,
                hotkey_name=hotkey,
                network=network,
                subnet=13,
            )
        except Exception as exc:
            chain_error = str(exc)

    wallet_hotkey_can_sign = _wallet_hotkey_file_exists(wallet, hotkey)
    runtime = SN13RuntimeState(
        wallet_name=wallet,
        wallet_hotkey=hotkey,
        hotkey_registered=hotkey_registered,
        listener_running=listener_running,
        local_db_healthy=db_healthy,
        disk_free_gb=disk_free_gb,
        wallet_hotkey_can_sign=wallet_hotkey_can_sign,
        parquet_export_available=parquet_export_available,
        jarvis_archive_bucket_configured=bool(os.environ.get("JARVIS_SN13_ARCHIVE_S3_BUCKET")),
    )
    report = evaluate_sn13_readiness(runtime=runtime, env=os.environ)

    payload = {
        "network": network,
        "wallet": wallet,
        "hotkey": hotkey,
        "hotkey_address": hotkey_address,
        "chain_error": chain_error,
        "capabilities": {
            capability.value: report.can(capability) for capability in SN13Capability
        },
        "runtime": {
            "listener_running": listener_running,
            "database": str(db_path),
            "database_healthy": db_healthy,
            "disk_path": str(disk_path),
            "disk_free_gb": disk_free_gb,
            "parquet_export_available": parquet_export_available,
            "wallet_hotkey_can_sign": wallet_hotkey_can_sign,
            "archive_bucket_configured": bool(
                os.environ.get("JARVIS_SN13_ARCHIVE_S3_BUCKET")
            ),
        },
        "checks": [
            {
                "name": check.name,
                "status": check.status.value,
                "message": check.message,
                "upstream_confirmed": check.upstream_confirmed,
            }
            for check in report.checks
        ],
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        if not report.can(SN13Capability.SERVE_VALIDATORS):
            raise SystemExit(2)
        return

    table = Table(title="SN13 Readiness")
    table.add_column("Capability", style="cyan")
    table.add_column("Ready", style="green")
    table.add_column("Meaning", style="white")
    capability_labels = {
        SN13Capability.SERVE_VALIDATORS: "Serve live validator requests",
        SN13Capability.INTAKE_OPERATOR_UPLOADS: "Intake personal-operator uploads",
        SN13Capability.EXPORT_UPSTREAM_S3: "Export to upstream presigned S3 validation path",
        SN13Capability.ARCHIVE_JARVIS_S3: "Archive exported data to Jarvis-owned S3",
    }
    for capability, label in capability_labels.items():
        ready = report.can(capability)
        table.add_row(capability.value, "[green]yes[/green]" if ready else "[red]no[/red]", label)
    console.print(table)

    runtime_table = Table(title="Runtime Facts")
    runtime_table.add_column("Fact", style="cyan")
    runtime_table.add_column("Value", style="green")
    runtime_table.add_row("Network", network)
    runtime_table.add_row("Wallet", wallet)
    runtime_table.add_row("Hotkey name", hotkey)
    runtime_table.add_row("Hotkey address", hotkey_address or "not checked")
    runtime_table.add_row("Listener running", "yes" if listener_running else "no")
    runtime_table.add_row("Database", str(db_path))
    runtime_table.add_row("Database healthy", "yes" if db_healthy else "no")
    runtime_table.add_row("Free disk", f"{disk_free_gb:.1f} GB")
    runtime_table.add_row("Parquet exports", "present" if parquet_export_available else "missing")
    if chain_error:
        runtime_table.add_row("Chain check", f"[yellow]{chain_error}[/yellow]")
    console.print(runtime_table)

    checks_table = Table(title="Requirement Checks")
    checks_table.add_column("Check", style="cyan")
    checks_table.add_column("Status", style="green")
    checks_table.add_column("Source", style="magenta")
    checks_table.add_column("Message", style="white")
    for check in report.checks:
        if check.status == ReadinessStatus.PASS:
            status = "[green]pass[/green]"
        elif check.status == ReadinessStatus.WARN:
            status = "[yellow]warn[/yellow]"
        else:
            status = "[red]blocked[/red]"
        checks_table.add_row(
            check.name,
            status,
            "upstream" if check.upstream_confirmed else "jarvis",
            check.message,
        )
    console.print(checks_table)

    if not report.can(SN13Capability.SERVE_VALIDATORS):
        raise SystemExit(2)


@sn13.group()
def scheduler():
    """Run automated DD refresh and work publication loops."""
    pass


@scheduler.command("run")
@_sn13_publication_economics_options
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--workstream-db-path", type=click.Path(path_type=Path), default=None)
@click.option("--target-items", type=int, default=5, show_default=True)
@click.option("--recent-buckets", type=int, default=1, show_default=True)
@click.option("--max-tasks", type=int, default=10, show_default=True)
@click.option("--interval-seconds", type=int, default=1200, show_default=True)
@click.option("--dd-timeout-seconds", type=int, default=30, show_default=True)
@click.option("--sample-dd", is_flag=True, help="Use built-in sample DD records for CI/dev only.")
@click.option("--once", is_flag=True, help="Run one scheduler cycle and exit.")
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_scheduler_run(
    cache_dir: Path | None,
    db_path: Path | None,
    workstream_db_path: Path | None,
    target_items: int,
    recent_buckets: int,
    max_tasks: int,
    interval_seconds: int,
    dd_timeout_seconds: int,
    sample_dd: bool,
    once: bool,
    max_task_cost: float | None,
    expected_reward: float | None,
    expected_submitted: int | None,
    expected_accepted: int | None,
    duplicate_rate: float | None,
    rejection_rate: float | None,
    validation_pass_probability: float | None,
    payout_basis: str | None,
    operator_payout: float,
    scraper_provider_cost: float,
    proxy_cost: float,
    compute_cost: float,
    local_storage_cost: float,
    export_staging_cost: float,
    upload_bandwidth_cost: float,
    retry_cost: float,
    risk_reserve: float,
    jarvis_archive_bucket_cost: float,
    s3_mode: str,
    currency: str,
    json_output: bool,
):
    """Refresh DD and publish economically safe SN13 work on a cadence."""
    import time
    from datetime import datetime, timezone

    from subnets.sn13.gravity import refresh_gravity_cache
    from subnets.sn13.publication import evaluate_publication_batch
    from subnets.sn13.workstream import publish_sn13_tasks
    from workstream.sqlite_store import SQLiteWorkstream

    economics = _sn13_publication_economics_config(
        max_task_cost=max_task_cost,
        expected_reward=expected_reward,
        expected_submitted=expected_submitted,
        expected_accepted=expected_accepted,
        duplicate_rate=duplicate_rate,
        rejection_rate=rejection_rate,
        validation_pass_probability=validation_pass_probability,
        payout_basis=payout_basis,
        operator_payout=operator_payout,
        scraper_provider_cost=scraper_provider_cost,
        proxy_cost=proxy_cost,
        compute_cost=compute_cost,
        local_storage_cost=local_storage_cost,
        export_staging_cost=export_staging_cost,
        upload_bandwidth_cost=upload_bandwidth_cost,
        retry_cost=retry_cost,
        risk_reserve=risk_reserve,
        jarvis_archive_bucket_cost=jarvis_archive_bucket_cost,
        s3_mode=s3_mode,
        currency=currency,
    )
    resolved_workstream_db_path = workstream_db_path or _workstream_db_path()
    resolved_cache_dir = cache_dir or _sn13_gravity_cache_dir()
    workstream = SQLiteWorkstream(resolved_workstream_db_path)

    cycle_index = 0
    while True:
        cycle_index += 1
        if not sample_dd:
            refresh_gravity_cache(cache_dir=resolved_cache_dir, timeout_seconds=dd_timeout_seconds)

        resolved_db_path, snapshot, tasks = _sn13_plan_context(
            dd_file=None,
            cache_dir=resolved_cache_dir,
            sample_dd=sample_dd,
            db_path=db_path,
            target_items=target_items,
            recent_buckets=recent_buckets,
            max_tasks=max_tasks,
        )
        publication = evaluate_publication_batch(tasks, economics=economics)
        published = publish_sn13_tasks(list(publication.publishable_tasks), workstream=workstream)
        payload = {
            "cycle": cycle_index,
            "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "db_path": str(resolved_db_path),
            "workstream_db_path": str(resolved_workstream_db_path),
            "desirability_source": snapshot.source_ref,
            "desirability_jobs": len(snapshot.jobs),
            "planned_tasks": len(tasks),
            "published_tasks": len(published),
            "refused_tasks": len(publication.refused_tasks),
            "published_task_ids": [task.task_id for task in published],
        }

        if json_output:
            click.echo(json.dumps(payload, indent=2))
        else:
            table = Table(title="SN13 Scheduler Cycle")
            table.add_column("Fact", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Cycle", str(cycle_index))
            table.add_row("DD source", snapshot.source_ref or "unknown")
            table.add_row("DD jobs", str(len(snapshot.jobs)))
            table.add_row("Planned tasks", str(len(tasks)))
            table.add_row("Published tasks", str(len(published)))
            table.add_row("Refused tasks", str(len(publication.refused_tasks)))
            table.add_row("Interval", f"{interval_seconds}s")
            console.print(table)

        if once:
            return
        time.sleep(interval_seconds)


@sn13.group()
def simulate():
    """Run local SN13 simulations before mainnet."""
    pass


@simulate.command("operator")
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--source", type=click.Choice(["X", "REDDIT"]), default="X")
@click.option("--label", type=str, default="#bittensor")
@click.option("--operator-id", type=str, default="sim_operator")
@click.option("--count", type=int, default=3, show_default=True)
@click.option("--job-id", type=str, default="sim_job")
def sn13_simulate_operator(
    db_path: Path | None,
    source: str,
    label: str,
    operator_id: str,
    count: int,
    job_id: str,
):
    """Simulate personal operators pushing valid source records into Jarvis."""
    from datetime import datetime, timezone

    from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
    from subnets.sn13.models import DataSource
    from subnets.sn13.storage import SQLiteStorage
    from subnets.sn13.tasks import SN13OperatorRuntime

    db_path = db_path or _sn13_db_path()
    storage = SQLiteStorage(db_path)
    runtime = SN13OperatorRuntime(storage=storage)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    data_source = DataSource(source)

    stored = 0
    rejected = 0
    for index in range(count):
        created_at = now
        uri = _simulated_uri(data_source.value, label, index, created_at)
        submission = OperatorSubmission(
            operator_id=operator_id,
            source=data_source,
            label=label,
            uri=uri,
            source_created_at=created_at,
            scraped_at=now,
            content=_simulated_content(data_source.value, label, index, created_at, uri),
            provenance=SubmissionProvenance(
                scraper_id="jarvis.simulator",
                query_type="simulated_operator_push",
                query_value=label,
                job_id=job_id,
            ),
        )
        result = runtime.ingest_submission(submission, now=now)
        stored += 1 if result.stored else 0
        rejected += 0 if result.stored else 1

    console.print(f"[green]Stored {stored} simulated {source} submission(s)[/green]")
    if rejected:
        console.print(f"[yellow]Rejected {rejected} submission(s)[/yellow]")
    console.print(f"[cyan]Database:[/cyan] {db_path}")


@simulate.command("cycle")
@click.option("--dd-file", type=click.Path(path_type=Path), default=None)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
@click.option("--sample-dd", is_flag=True, help="Use built-in sample DD records for CI/dev only.")
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--export-root", type=click.Path(path_type=Path), default=None)
@click.option("--operators", type=int, default=2, show_default=True)
@click.option("--target-items", type=int, default=5, show_default=True)
@click.option("--recent-buckets", type=int, default=1, show_default=True)
@click.option("--max-tasks", type=int, default=4, show_default=True)
@click.option("--miner-hotkey", type=str, default="jarvis_simulated_hotkey", show_default=True)
@click.option("--no-export", is_flag=True)
@click.option("--json-output", "--json", "json_output", is_flag=True)
def sn13_simulate_cycle(
    dd_file: Path | None,
    cache_dir: Path | None,
    sample_dd: bool,
    db_path: Path | None,
    export_root: Path | None,
    operators: int,
    target_items: int,
    recent_buckets: int,
    max_tasks: int,
    miner_hotkey: str,
    no_export: bool,
    json_output: bool,
):
    """Run DD -> operator task -> storage -> validator -> export locally."""
    from subnets.sn13.simulator import (
        ClosedLoopSimulationConfig,
        load_snapshot,
        run_closed_loop_simulation,
    )
    from subnets.sn13.storage import SQLiteStorage

    db_path = db_path or _sn13_db_path()
    export_root = export_root or _sn13_export_root()
    cache_dir = cache_dir or _sn13_gravity_cache_dir()
    try:
        snapshot = load_snapshot(dd_file, cache_dir=cache_dir, use_sample=sample_dd)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    storage = SQLiteStorage(db_path)
    config = ClosedLoopSimulationConfig(
        operator_ids=tuple(f"sim_operator_{idx + 1}" for idx in range(operators)),
        target_items_per_bucket=target_items,
        default_recent_buckets=recent_buckets,
        max_tasks=max_tasks,
        miner_hotkey=miner_hotkey,
        export=not no_export,
    )
    report = run_closed_loop_simulation(
        storage=storage,
        snapshot=snapshot,
        output_root=export_root,
        config=config,
    )

    if json_output:
        click.echo(
            json.dumps(
                {
                    "db_path": str(db_path),
                    "export_root": str(export_root),
                    "desirability_source": snapshot.source_ref,
                    "summary": report.to_summary_dict(),
                    "exports": [
                        result.model_dump(mode="json") for result in report.export_results
                    ],
                },
                indent=2,
            )
        )
        return

    table = Table(title="SN13 Closed-Loop Simulation")
    table.add_column("Stage", style="cyan")
    table.add_column("Result", style="green")
    for key, value in report.to_summary_dict().items():
        table.add_row(key, str(value))
    console.print(table)
    console.print(f"[cyan]Database:[/cyan] {db_path}")
    console.print(f"[cyan]Export root:[/cyan] {export_root}")
    console.print(f"[cyan]DD source:[/cyan] {snapshot.source_ref or 'unknown'}")


@simulate.command("validator")
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
@click.option("--query", type=click.Choice(["index", "bucket", "contents"]), default="index")
@click.option("--source", type=click.Choice(["X", "REDDIT"]), default="X")
@click.option("--label", type=str, default="#bittensor")
@click.option("--time-bucket", type=int, default=None)
@click.option("--limit", type=int, default=10)
@click.option(
    "--json-output",
    "--json",
    "json_output",
    is_flag=True,
    help="Print JSON-compatible simulation output.",
)
def sn13_simulate_validator(
    db_path: Path | None,
    query: str,
    source: str,
    label: str,
    time_bucket: int | None,
    limit: int,
    json_output: bool,
):
    """Simulate validator queries against local canonical storage."""
    from subnets.sn13.listener.protocol_adapter import (
        bind_get_contents_by_buckets_response,
        bind_get_data_entity_bucket_response,
        bind_get_miner_index_response,
    )
    from subnets.sn13.models import DataSource
    from subnets.sn13.storage import SQLiteStorage

    db_path = db_path or _sn13_db_path()
    storage = SQLiteStorage(db_path)
    data_source = DataSource(source)
    bucket_id = {
        "source": source,
        "label": {"value": label},
        "time_bucket": {"id": time_bucket or _latest_time_bucket(storage, data_source, label)},
    }

    if query == "index":
        synapse = SimpleNamespace()
        payload = bind_get_miner_index_response(
            synapse,
            storage=storage,
            miner_hotkey="jarvis_simulated_hotkey",
        )
        summary = {"query": "GetMinerIndex", "bucket_groups": len(payload.get("sources", {}))}
    elif query == "bucket":
        synapse = SimpleNamespace(data_entity_bucket_id=bucket_id)
        entities = bind_get_data_entity_bucket_response(synapse, storage=storage, limit=limit)
        payload = {"data_entities": [_json_safe_entity(entity) for entity in entities]}
        summary = {"query": "GetDataEntityBucket", "entities": len(entities)}
    else:
        synapse = SimpleNamespace(data_entity_bucket_ids=[bucket_id])
        contents = bind_get_contents_by_buckets_response(
            synapse,
            storage=storage,
            per_bucket_limit=limit,
        )
        payload = {
            "bucket_ids_to_contents": [
                (bucket, [content.decode("utf-8", errors="replace") for content in raw_contents])
                for bucket, raw_contents in contents
            ]
        }
        summary = {"query": "GetContentsByBuckets", "buckets": len(contents)}

    if json_output:
        click.echo(json.dumps({"summary": summary, "payload": payload}, indent=2, default=str))
        return

    table = Table(title=f"SN13 Validator Simulation: {summary['query']}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for key, value in summary.items():
        table.add_row(key, str(value))
    table.add_row("Database", str(db_path))
    if query != "index":
        table.add_row("Source", source)
        table.add_row("Label", label)
        table.add_row("Time bucket", str(bucket_id["time_bucket"]["id"]))
    console.print(table)


def _latest_time_bucket(storage, source, label: str) -> int:
    from datetime import datetime, timezone

    from subnets.sn13.models import time_bucket_from_datetime

    buckets = [
        bucket
        for bucket in storage.get_buckets_for_source(source)
        if label is None or bucket.label == label.strip().casefold()
    ]
    if buckets:
        return max(bucket.time_bucket for bucket in buckets)
    return time_bucket_from_datetime(datetime.now(timezone.utc))


def _simulated_uri(source: str, label: str, index: int, created_at) -> str:
    safe_label = label.strip("#$/ ").replace(" ", "-").lower() or "unlabeled"
    stamp = int(created_at.timestamp())
    if source == "REDDIT":
        return f"https://www.reddit.com/r/{safe_label}/comments/jarvis{stamp}{index}"
    return f"https://x.com/jarvis_sim/status/{stamp}{index}"


def _simulated_content(source: str, label: str, index: int, created_at, uri: str) -> dict[str, Any]:
    timestamp = created_at.isoformat()
    if source == "REDDIT":
        post_id = f"jarvis_reddit_{int(created_at.timestamp())}_{index}"
        return {
            "id": post_id,
            "username": "jarvis_sim_operator",
            "url": uri,
            "createdAt": timestamp,
            "title": f"Jarvis simulated Reddit item {index} for {label}",
            "body": f"Simulated Reddit body for {label}",
        }
    tweet_id = f"jarvis_x_{int(created_at.timestamp())}_{index}"
    return {
        "tweet_id": tweet_id,
        "username": "jarvis_sim_operator",
        "text": f"Jarvis simulated X item {index} for {label}",
        "url": uri,
        "timestamp": timestamp,
    }


def _json_safe_entity(entity: dict[str, Any]) -> dict[str, Any]:
    safe = dict(entity)
    content = safe.get("content")
    if isinstance(content, bytes):
        safe["content"] = content.decode("utf-8", errors="replace")
    return safe


# ============================================================================
# CONFIG Commands
# ============================================================================


@cli.group()
def config():
    """Configuration management."""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration."""
    from miner_tools.config import load_config

    config_file = ctx.obj["config_path"]

    try:
        raw = _load_yaml_config_file(config_file)
        global_cfg, subnets = load_config(config_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc

    global_table = Table(title="Global Settings")
    global_table.add_column("Setting", style="cyan")
    global_table.add_column("Value", style="green")
    global_table.add_row("Config Path", str(config_file))
    global_table.add_row("Network", global_cfg.subtensor_network)
    global_table.add_row("Data Dir", str(global_cfg.data_dir))
    global_table.add_row("Wallet", global_cfg.wallet.name)
    global_table.add_row("Hotkey", global_cfg.wallet.hotkey)
    console.print(global_table)

    subnet_table = Table(title="Configured Subnets")
    subnet_table.add_column("SN", style="cyan", justify="right")
    subnet_table.add_column("Nickname", style="green")
    subnet_table.add_column("Wallet", style="white")
    subnet_table.add_column("Threshold", style="yellow", justify="right")
    subnet_table.add_column("Enabled", style="magenta")

    subnet_entries = raw.get("subnets", [])
    nickname_by_netuid = {int(item["netuid"]): item.get("nickname", "-") for item in subnet_entries}
    wallet_by_netuid = {
        int(item["netuid"]): item.get("wallet", {}).get("name", global_cfg.wallet.name)
        for item in subnet_entries
    }
    for subnet in subnets:
        subnet_table.add_row(
            str(subnet.netuid),
            nickname_by_netuid.get(subnet.netuid, subnet.label),
            wallet_by_netuid.get(subnet.netuid, global_cfg.wallet.name),
            f"{subnet.price_threshold_tao:.4f}",
            "yes" if subnet.enabled else "no",
        )

    console.print(subnet_table)


@config.command("validate")
@click.pass_context
def config_validate(ctx):
    """Validate configuration."""
    from miner_tools.config import load_config

    config_file = ctx.obj["config_path"]
    try:
        _, subnets = load_config(config_file)
        console.print("[green]✓ Config valid[/green]")
        console.print(f"[cyan]{len(subnets)} subnet(s) configured[/cyan]")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    cli()
