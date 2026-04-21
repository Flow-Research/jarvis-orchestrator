#!/usr/bin/env python3
"""
Jarvis-Miner CLI — Advanced unified interface for all miner operations.
"""

# ============================================================================
# CRITICAL: Filter bittensor CLI args BEFORE any imports
# ============================================================================
import sys

for arg in list(sys.argv):
    if (
        arg.startswith("--logging.")
        or arg.startswith("--config")
        or arg == "--strict"
        or arg == "--no_version_checking"
    ):
        sys.argv.remove(arg)

# ============================================================================
# Now import our dependencies
# ============================================================================

import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "miner_tools" / "config" / "config.yaml"

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
    return wallet_cfg.get("name") or raw_config.get("global", {}).get("wallet", {}).get("name") or f"sn{subnet}miner"


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
        if verbose:
            lines = [
                "[bold cyan]Jarvis Miner CLI[/bold cyan]",
                f"Config: {config_path}",
                f"Subnets configured: {len(ctx.obj['raw_config'].get('subnets', []))}",
            ]
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
        except:
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
        except:
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
        except:
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
        console.print(f"[green]✓ Faucet complete![/green]")
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
                console.print(f"[yellow]Found stale running state for subnet {subnet}; replacing it.[/yellow]")

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

    capture_summary = PROJECT_ROOT / "subnets" / f"sn{subnet}" / "listener" / "captures" / "summary.json"
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
            console.print(f"[green]✓ Registered successfully![/green]")
        else:
            console.print(f"[red]Registration failed[/red]")
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
        console.print(f"[green]✓ Config valid[/green]")
        console.print(f"[cyan]{len(subnets)} subnet(s) configured[/cyan]")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    cli()
