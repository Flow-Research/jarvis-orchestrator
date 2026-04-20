#!/usr/bin/env python3
"""
Jarvis-Miner CLI — Copy from original miner_tools/cli.py
"""

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import default_config_path, load_config
from .models import AlertConfig, MonitorState, SubnetConfig, Trend, WalletConfig

console = Console()


@click.group("watch")
@click.version_option(version="1.0.0", prog_name="jarvis-miner")
@click.option("-c", "--config", type=click.Path(), default=None)
@click.option("-v", "--verbose", is_flag=True)
@click.pass_context
def watch(ctx, config, verbose):
    """Start live price monitor with auto-registration and deregister alerts."""
    from .fetcher import close_subtensor, fetch_burn_cost

    config_path = config or default_config_path()
    global_cfg, subnets = load_config(config_path)

    from .deregister import DeregisterMonitor
    from .monitor import Monitor

    monitor = Monitor(global_cfg, subnets)
    dereg_monitor = DeregisterMonitor(global_cfg, subnets)

    enabled = [s for s in subnets if s.enabled]
    console.print(f"[bold]Monitoring {len(enabled)} subnets...[/]")

    async def run():
        tasks = [asyncio.create_task(monitor.start())]
        if dereg_monitor.has_entries:
            tasks.append(asyncio.create_task(dereg_monitor.start()))
        await asyncio.gather(*tasks, return_exceptions=True)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        console.print("[yellow]Stopped[/yellow]")


@click.group("wallet")
def wallet():
    """Show wallet status."""
    from .fetcher import close_subtensor, get_wallet_info_sdk

    global_cfg, subnets = load_config(default_config_path())
    w = global_cfg.wallet

    try:
        info = get_wallet_info_sdk(w, global_cfg.subtensor_network, global_cfg.subtensor_endpoint)

        if info["coldkey_exists"]:
            console.print(f"[bold]Coldkey:[/bold] {info['coldkey_ss58']}")
            if info["balance_tao"]:
                console.print(f"  Balance: {info['balance_tao']:.6f} TAO")

        if info["hotkey_exists"]:
            console.print(f"[bold]Hotkey:[/bold] {info['hotkey_ss58']}")
            if info["registered_on"]:
                console.print(
                    f"  Registered on: SN{', '.join(str(s) for s in info['registered_on'])}"
                )

        close_subtensor()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@click.group("status")
def status():
    """Show monitor state and price history."""
    from .fetcher import close_subtensor

    global_cfg, subnets = load_config(default_config_path())
    state_path = global_cfg.data_dir / "monitor_state.json"
    state = MonitorState.load(state_path)

    if not state.histories:
        console.print("[dim]No data. Run 'jarvis-miner watch' first.[/dim]")
        return

    table = Table(title="Price History")
    table.add_column("SN", style="cyan")
    table.add_column("Last Price", style="yellow")
    table.add_column("Readings")

    for subnet in subnets:
        history = state.histories.get(subnet.netuid)
        if history and history.readings:
            last = history.readings[-1]
            table.add_row(
                str(subnet.netuid), f"{last.cost_tao:.6f} TAO", str(len(history.readings))
            )

    console.print(table)
    close_subtensor()


@click.group("price")
def price():
    """Fetch burn cost for subnets."""
    from .fetcher import close_subtensor, fetch_burn_cost

    global_cfg, subnets = load_config(default_config_path())

    table = Table(title="Registration Burn Cost")
    table.add_column("SN", style="cyan")
    table.add_column("Label", style="white")
    table.add_column("Cost (TAO)", style="yellow")
    table.add_column("Threshold")

    for subnet in subnets:
        try:
            reading = asyncio.run(
                fetch_burn_cost(subnet, global_cfg.subtensor_network, global_cfg.subtensor_endpoint)
            )
            table.add_row(
                str(subnet.netuid),
                subnet.label,
                f"{reading.cost_tao:.6f}",
                f"{subnet.price_threshold_tao:.6f}",
            )
        except Exception as e:
            table.add_row(str(subnet.netuid), subnet.label, f"[red]{e}[/red]", "-")

    console.print(table)
    close_subtensor()
