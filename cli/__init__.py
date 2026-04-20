"""
Jarvis-Miner CLI — Unified interface for all miner operations

Organized modules:
    miner: start/stop/status
    wallet: info
    config: show
    network: register/info/price
"""

import json
import os
import signal
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_DIR = PROJECT_ROOT / "miner_tools" / "config"


# ============================================================================
# Helpers
# ============================================================================


def get_network_config(network: str = "mainnet") -> Path:
    """Get config file for network."""
    if network == "testnet":
        return CONFIG_DIR / "config.test.yaml"
    return CONFIG_DIR / "config.yaml"


def get_state_file(subnet: int) -> Path:
    """Get state file for subnet."""


SUBNET_DIR = PROJECT_ROOT / "miner_tools" / "subnets"


def get_subnet_dir(subnet: int) -> Path:
    """Get directory for subnet."""
    return SUBNET_DIR / str(subnet)


def get_state_file(subnet: int) -> Path:
    """Get state file for subnet."""
    state_dir = get_subnet_dir(subnet)
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "state.json"


# ============================================================================
# Main CLI
# ============================================================================


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Jarvis-Miner — Miner orchestration for Bittensor subnets."""
    pass


# ============================================================================
# Miner (start/stop/status)
# ============================================================================


@cli.group()
def miner():
    """Manage miner listener (queries)."""
    pass


@miner.command()
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="mainnet", help="Network"
)
def start_all(network: str):
    """Start all enabled subnets from config."""
    import yaml

    config_file = get_network_config(network)
    with open(config_file) as f:
        data = yaml.safe_load(f)

    subnets = data.get("subnets", [])
    enabled = [s for s in subnets if s.get("enabled")]

    console.print(f"[bold green]Starting all subnets on {network}...[/]")

    for s in enabled:
        netuid = s.get("netuid")
        wallet_name = s.get("wallet", {}).get("name", f"sn{netuid}miner")
        console.print(f"  Starting subnet {netuid} with wallet {wallet_name}...")

        # Start this miner (same logic as individual start)
        subnet_dir = get_subnet_dir(netuid)
        venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
        listener_script = subnet_dir / "listener" / "listener.py"

        cmd = [str(venv_python), str(listener_script), "--wallet", wallet_name]

        state_file = get_state_file(netuid)
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
                if state.get("running"):
                    console.print(f"    [yellow]Already running[/yellow]")
                    continue

        log_file = subnet_dir / "listener.log"
        with open(log_file, "w") as out:
            proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)

        state = {
            "subnet": netuid,
            "network": network,
            "wallet": wallet_name,
            "pid": proc.pid,
            "running": True,
            "started_at": "now",
        }
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        console.print(f"    [green]Started PID {proc.pid}[/]")


@miner.command()
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="mainnet", help="Network"
)
@click.option("--interval", "-i", type=int, default=60, help="Poll interval seconds")
def monitor(network: str, interval: int):
    """Monitor all enabled subnets: prices, auto-register, deregister alerts."""
    import yaml
    import time
    import bittensor as bt

    config_file = get_network_config(network)
    with open(config_file) as f:
        data = yaml.safe_load(f)

    subnets = data.get("subnets", [])
    enabled = [s for s in subnets if s.get("enabled")]

    net = "test" if network == "testnet" else "finney"
    subtensor = bt.Subtensor(network=net)

    console.print(f"[bold green]Monitoring {len(enabled)} subnets on {network}...[/]")

    try:
        while True:
            for s in enabled:
                netuid = s.get("netuid")
                nickname = s.get("nickname", f"SN{netuid}")
                try:
                    metagraph = subtensor.metagraph(netuid=netuid)
                    miners = len(metagraph.uids)
                    console.print(f"SN{netuid} ({nickname}): {miners} miners")
                except Exception as e:
                    console.print(f"SN{netuid}: [red]Error: {e}[/red]")

            console.print(f"[dim]Next update in {interval}s... (Ctrl+C to stop)[/dim]")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped[/yellow]")


@miner.command()
@click.option("--subnet", "-s", type=int, default=13, help="Subnet ID")
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="testnet", help="Network"
)
@click.option("--wallet", "-w", type=str, default=None, help="Wallet name (default: sn13miner)")
def start(subnet: int, network: str, wallet: str):
    """Start miner listener."""
    wallet = wallet or "sn13miner"
    subnet_dir = get_subnet_dir(subnet)

    console.print(f"[bold green]Starting miner on subnet {subnet} ({network})...[/]")

    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    listener_script = subnet_dir / "listener" / "listener.py"

    cmd = [str(venv_python), str(listener_script), "--wallet", wallet]

    state_file = get_state_file(subnet)
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            if state.get("pid") and state.get("running"):
                console.print(f"[yellow]Miner already running on subnet {subnet}[/]")
                return

    log_file = subnet_dir / "listener.log"
    with open(log_file, "w") as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)

    state = {
        "subnet": subnet,
        "network": network,
        "wallet": wallet,
        "pid": proc.pid,
        "running": True,
        "started_at": "now",
    }
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    console.print(f"[green]Miner started with PID {proc.pid}[/]")


@miner.command()
@click.option("--subnet", "-s", type=int, default=13, help="Subnet ID")
def stop(subnet: int):
    """Stop miner listener."""
    state_file = get_state_file(subnet)

    if not state_file.exists():
        console.print(f"[yellow]No state file for subnet {subnet}[/]")
        return

    with open(state_file) as f:
        state = json.load(f)

    pid = state.get("pid")
    if not pid:
        console.print(f"[yellow]No PID found for subnet {subnet}[/]")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        state["running"] = False
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
        console.print(f"[green]Miner stopped (PID {pid})[/]")
    except ProcessLookupError:
        console.print(f"[yellow]Process {pid} not found[/]")


@miner.command()
@click.option("--subnet", "-s", type=int, default=13, help="Subnet ID")
def status(subnet: int):
    """Show miner status."""
    subnet_dir = get_subnet_dir(subnet)
    state_file = get_state_file(subnet)
    log_file = subnet_dir / "listener.log"
    captures_dir = subnet_dir / "captures"

    table = Table(title=f"Subnet {subnet} Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        table.add_row("Status", "Running" if state.get("running") else "Stopped")
        table.add_row("PID", str(state.get("pid", "N/A")))
        table.add_row("Network", state.get("network", "N/A"))
        table.add_row("Wallet", state.get("wallet", "N/A"))
    else:
        table.add_row("Status", "No state file")

    if log_file.exists():
        lines = len(open(log_file).readlines())
        table.add_row("Log lines", str(lines))

    if captures_dir.exists():
        captures = list(captures_dir.rglob("*.json"))
        table.add_row("Queries", str(len(captures)))

    console.print(table)


# ============================================================================
# Wallet
# ============================================================================


@cli.group()
def wallet():
    """Wallet operations."""
    pass


@wallet.command()
def info():
    """Show wallet info."""
    wallet_path = Path.home() / ".bittensor" / "wallets"
    if not wallet_path.exists():
        console.print("[red]No wallets found[/red]")
        return

    table = Table()
    table.add_column("Wallet", style="cyan")
    table.add_column("Hotkey", style="green")

    for w in wallet_path.iterdir():
        if w.is_dir():
            hotkeys = list((w / "hotkeys").glob("*")) if (w / "hotkeys").exists() else []
            for h in hotkeys:
                if h.is_file():
                    table.add_row(w.name, h.name)

    console.print(table)


# ============================================================================
# Config
# ============================================================================


@cli.group()
def config():
    """Configuration management."""
    pass


@config.command()
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="mainnet", help="Network"
)
def show(network: str):
    """Show configuration."""
    import yaml

    config_file = get_network_config(network)

    if not config_file.exists():
        console.print(f"[red]Config not found: {config_file}[/red]")
        return

    with open(config_file) as f:
        data = yaml.safe_load(f)

    console.print(f"[bold]Config: {config_file.name}[/bold]")
    console.print(f"Network: {data.get('global', {}).get('subtensor_network', 'N/A')}")
    console.print(f"Data dir: {data.get('global', {}).get('data_dir', 'N/A')}")

    subnets = data.get("subnets", [])
    console.print(f"\n[bold]Monitored subnets:[/bold]")
    for s in subnets:
        if s.get("enabled"):
            console.print(f"  - {s.get('netuid')}: {s.get('nickname', 'N/A')}")


# ============================================================================
# Network (register/info/price)
# ============================================================================


@cli.group()
def network():
    """Network registration and monitoring."""
    pass


@network.command()
@click.option("--subnet", "-s", type=int, default=13, help="Subnet ID")
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="testnet", help="Network"
)
def info(subnet: int, network: str):
    """Show subnet information from chain."""
    import bittensor as bt

    net = "test" if network == "testnet" else "finney"
    subtensor = bt.Subtensor(network=net)
    metagraph = subtensor.metagraph(netuid=subnet)

    table = Table(title=f"Subnet {subnet} Info ({network})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Miners", str(len(metagraph.uids)))
    table.add_row("Validators", str(sum(metagraph.validator_permit)))

    console.print(table)


@network.command()
@click.option("--subnet", "-s", type=int, help="Subnet ID")
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="testnet", help="Network"
)
@click.option("--wallet", "-w", type=str, default="sn13miner", help="Wallet name")
def register(subnet: int, network: str, wallet: str):
    """Register wallet on subnet (burn TAO)."""
    import bittensor as bt

    net = "test" if network == "testnet" else "finney"
    subtensor = bt.Subtensor(network=net)

    console.print(f"[yellow]Registering {wallet} on subnet {subnet}...[/]")

    try:
        success = subtensor.register(wallet=wallet, netuid=subnet)
        if success:
            console.print(f"[green]Registered successfully![/]")
        else:
            console.print(f"[red]Registration failed[/]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")


@network.command()
@click.option(
    "--network", "-n", type=click.Choice(["mainnet", "testnet"]), default="mainnet", help="Network"
)
def price(network: str):
    """Show current burn cost for new subnet."""
    import bittensor as bt

    net = "test" if network == "testnet" else "finney"
    subtensor = bt.Subtensor(network=net)

    try:
        price = subtensor.get_subnet_burn_cost()
        console.print(f"[bold]Burn cost: {price} TAO[/]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")


# ============================================================================
# Entry point
# ============================================================================

if __name__ == "__main__":
    cli()
