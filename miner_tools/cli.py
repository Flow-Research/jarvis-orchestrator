"""CLI interface for the Jarvis Miner CLI."""

from __future__ import annotations

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


@click.group()
@click.version_option(version="1.0.0", prog_name="jarvis-miner")
@click.option(
    "-c",
    "--config",
    type=click.Path(),
    default=None,
    help="Path to config file (default: miner_tools/config/config.yaml or $JARVIS_CONFIG)",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, config: str | None, verbose: bool) -> None:
    """Jarvis Miner — Monitor, Auto-Register & Deregister Alerts

    Monitor subnet registration prices, auto-register when favorable,
    and alert when your hotkeys get deregistered.
    """
    ctx.ensure_object(dict)
    log_level = logging.DEBUG if verbose else logging.INFO

    # Import bittensor FIRST so its logging setup happens before our config
    # This prevents bittensor from overriding our log level
    try:
        import bittensor  # noqa: F401
    except ImportError:
        pass

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Ensure our loggers keep INFO level even after bittensor setup
    logging.getLogger().setLevel(log_level)
    logging.getLogger("miner_tools").setLevel(log_level)

    config_path = Path(config) if config else default_config_path()
    ctx.obj["config_path"] = config_path


# ── monitor ────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def monitor(ctx: click.Context) -> None:
    """Start the monitor with auto-registration and deregister alerts."""
    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    from .deregister import DeregisterMonitor
    from .monitor import Monitor

    monitor = Monitor(global_cfg, subnets)
    dereg_monitor = DeregisterMonitor(global_cfg, subnets)

    enabled = [s for s in subnets if s.enabled]
    auto_reg = [s for s in enabled if s.auto_register]
    dereg_entries = sum(len(s.deregister_entries) for s in enabled)

    channels = []
    for s in enabled:
        ch = []
        if s.alerts.discord:
            ch.append("Discord")
        if s.alerts.telegram:
            ch.append("Telegram")
        channels.append(", ".join(ch) if ch else "none")

    lines = [
        "[bold green]Jarvis Miner[/bold green]",
        f"Network: {global_cfg.subtensor_network}  |  Source: {global_cfg.price_source}",
        f"Subnets: {len(enabled)}  |  Data dir: {global_cfg.data_dir}",
        f"Alerts: {', '.join(set(channels)) or 'none configured'}",
    ]
    if auto_reg:
        sn_list = ", SN".join(str(s.netuid) for s in auto_reg)
        w = global_cfg.wallet
        lines.append(
            f"Auto-register: [green]ON[/green] for SN{sn_list} (wallet={w.name}/{w.hotkey})"
        )
    if dereg_entries:
        lines.append(f"Deregister monitor: [cyan]{dereg_entries} hotkey(s)[/cyan]")

    console.print(Panel.fit("\n".join(lines), border_style="green"))

    async def _run_both():
        tasks = [
            asyncio.create_task(monitor.start(), name="price-monitor"),
        ]
        if dereg_monitor.has_entries:
            tasks.append(asyncio.create_task(dereg_monitor.start(), name="dereg-monitor"))
        await asyncio.gather(*tasks, return_exceptions=True)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_both())
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")
    finally:
        console.print("[dim]Monitor stopped.[/dim]")


# ── price ────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("netuid", type=int, required=False)
@click.pass_context
def price(ctx: click.Context, netuid: int | None) -> None:
    """Fetch the current burn cost for a subnet.

    If NETUID is provided, fetches only that subnet.
    Otherwise fetches all configured subnets.
    """
    from .fetcher import close_subtensor, fetch_burn_cost

    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    if netuid is not None:
        targets = [s for s in subnets if s.netuid == netuid]
        if not targets:
            targets = [
                SubnetConfig(
                    netuid=netuid,
                    price_threshold_tao=0,
                    alerts=__import__(
                        "miner_tools.models", fromlist=["AlertConfig"]
                    ).AlertConfig(),
                )
            ]
    else:
        targets = subnets

    table = Table(title="Registration Burn Cost", show_lines=True)
    table.add_column("SN", style="cyan", justify="right")
    table.add_column("Label", style="white")
    table.add_column("Cost (TAO)", style="bold yellow", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Ratio", justify="right")
    table.add_column("Status", justify="center")

    for subnet in targets:
        try:
            reading = asyncio.run(
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
                threshold_str = f"{subnet.price_threshold_tao:.6f}"
                ratio_str = f"{ratio:.2f}x"
                if ratio <= 0.5:
                    status = "[bold green]EXCELLENT[/bold green]"
                elif ratio <= 1.0:
                    status = "[green]GOOD[/green]"
                elif ratio <= 1.5:
                    status = "[yellow]FAIR[/yellow]"
                else:
                    status = "[red]HIGH[/red]"
            else:
                threshold_str = "\u2500"
                ratio_str = "\u2500"
                status = "[dim]\u2500[/dim]"

            table.add_row(
                str(subnet.netuid),
                subnet.label,
                f"{reading.cost_tao:.6f}",
                threshold_str,
                ratio_str,
                status,
            )
        except Exception as e:
            table.add_row(
                str(subnet.netuid),
                subnet.label,
                f"[red]{e}[/red]",
                "\u2500",
                "\u2500",
                "\u2500",
            )

    console.print(table)
    close_subtensor()


# ── status ───────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show monitor state, price history, and sparkline charts."""
    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    state_path = global_cfg.data_dir / "monitor_state.json"
    state = MonitorState.load(state_path)

    if not state.histories:
        console.print("[dim]No price history found. Run 'jarvis-miner watch' first.[/dim]")
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
        trend_str = f"[{trend_style}]{trend.value.upper()}[/{trend_style}]"

        sparkline = history.sparkline(30)
        min_p = history.min_price()
        max_p = history.max_price()
        avg_p = history.avg_price()

        table.add_row(
            str(subnet.netuid),
            subnet.label,
            f"{last.cost_tao:.6f} TAO",
            trend_str,
            str(len(history.readings)),
            f"{min_p:.6f}" if min_p is not None else "\u2500",
            f"{max_p:.6f}" if max_p is not None else "\u2500",
            f"{avg_p:.6f}" if avg_p is not None else "\u2500",
            str(len(history.detected_floors)),
            sparkline,
            str(state.poll_counts.get(subnet.netuid, 0)),
        )

    console.print(table)

    # Show recent floor events
    floors_found = False
    for subnet in subnets:
        history = state.histories.get(subnet.netuid)
        if history and history.detected_floors:
            if not floors_found:
                console.print("\n[bold]\U0001f48e Recent Floor Events:[/bold]")
                floors_found = True
            for floor in history.detected_floors[-3:]:
                console.print(
                    f"  SN {subnet.netuid} ({subnet.label}): "
                    f"floor at {floor.floor_price:.6f} TAO "
                    f"({floor.timestamp.strftime('%Y-%m-%d %H:%M')}) "
                    f"+{floor.current_rise_pct:.1f}% rise"
                )


# ── info ─────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Show detailed subnet information from the chain."""
    from .fetcher import close_subtensor, fetch_subnet_info

    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

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
            info_data = fetch_subnet_info(
                subnet.netuid,
                global_cfg.subtensor_network,
                global_cfg.subtensor_endpoint,
            )

            burn_str = f"{info_data['burn']:.6f}" if info_data.get("burn") else "\u2500"
            price_str = f"{info_data['price']:.6f}" if info_data.get("price") else "\u2500"
            tao_in_str = f"{info_data['tao_in']:.2f}" if info_data.get("tao_in") else "\u2500"

            table.add_row(
                str(subnet.netuid),
                info_data.get("name", subnet.label),
                burn_str,
                price_str,
                tao_in_str,
                str(info_data.get("tempo", "\u2500")),
                info_data.get("symbol", "\u2500"),
            )
        except Exception as e:
            table.add_row(str(subnet.netuid), subnet.label, f"[red]{e}[/red]", *["\u2500"] * 4)

    console.print(table)
    close_subtensor()


# ── register ─────────────────────────────────────────────────────────────


@cli.command()
@click.argument("netuid", type=int)
@click.option("-w", "--wallet", "wallet_name", default=None, help="Wallet name override.")
@click.option("-k", "--hotkey", "hotkey_name", default=None, help="Hotkey name override.")
@click.option("--dry-run", is_flag=True, help="Show what would happen without registering.")
@click.pass_context
def register(
    ctx: click.Context,
    netuid: int,
    wallet_name: str | None,
    hotkey_name: str | None,
    dry_run: bool,
) -> None:
    """Register a wallet on a subnet (burn TAO).

    Burns TAO to register your wallet's hotkey on the specified subnet.
    Uses the wallet configured in config.yaml (or overrides via --wallet/--hotkey).
    """
    from .fetcher import burned_register_sdk, close_subtensor, fetch_burn_cost

    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    wallet_cfg = global_cfg.wallet
    if wallet_name:
        wallet_cfg = WalletConfig(
            name=wallet_name,
            hotkey=hotkey_name or wallet_cfg.hotkey,
            path=wallet_cfg.path,
        )

    # Get current burn cost
    subnet = next((s for s in subnets if s.netuid == netuid), None)
    if subnet is None:
        subnet = SubnetConfig(netuid=netuid, price_threshold_tao=0, alerts=AlertConfig())

    try:
        reading = asyncio.run(
            fetch_burn_cost(
                subnet,
                global_cfg.subtensor_network,
                global_cfg.subtensor_endpoint,
            )
        )
        console.print(
            f"SN{netuid} registration cost: [bold yellow]{reading.cost_tao:.6f} TAO[/bold yellow]"
        )
    except Exception as e:
        console.print(f"[yellow]Could not fetch cost: {e}[/yellow]")

    if dry_run:
        console.print(
            f"[dim]Dry run — would register with wallet={wallet_cfg.name}, "
            f"hotkey={wallet_cfg.hotkey} on SN{netuid}[/dim]"
        )
        close_subtensor()
        return

    if not click.confirm(
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
                f"[green]\u2713 Registered![/green] "
                f"Cost: {result.cost_tao:.6f} TAO, Hotkey: {result.hotkey[:16]}..."
            )
        else:
            console.print(f"[red]\u2717 Registration failed:[/red] {result.error}")
    except Exception as e:
        console.print(f"[red]Registration error:[/red] {e}")
    finally:
        close_subtensor()


# ── deregister-check ─────────────────────────────────────────────────────


@cli.command("deregister-check")
@click.pass_context
def deregister_check(ctx: click.Context) -> None:
    """Check registration status of all monitored hotkeys."""
    from .fetcher import close_subtensor, is_registered_sdk

    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

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
            except Exception as e:
                status = f"[yellow]{e}[/yellow]"

            table.add_row(
                str(subnet.netuid),
                subnet.label,
                f"{entry.hotkey_ss58[:12]}...{entry.hotkey_ss58[-6:]}",
                entry.display_name,
                status,
            )

    if not found_any:
        console.print(
            "[dim]No deregister entries configured. Add 'deregister' entries to config.yaml[/dim]"
        )
    else:
        console.print(table)

    close_subtensor()


@cli.command("validate")
@click.option("--check-webhooks", is_flag=True, help="Also test webhook connectivity.")
@click.pass_context
def validate(ctx: click.Context, check_webhooks: bool) -> None:
    """Validate config file and optionally test webhook connectivity."""
    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
        console.print(
            f"[green]\u2713 Config is valid.[/green] {len(subnets)} subnet(s) configured."
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]\u2717 Config error:[/red] {e}")
        sys.exit(1)

    if check_webhooks:
        import aiohttp

        from .alerter import validate_webhooks

        console.print("\n[dim]Testing webhook connectivity...[/dim]")

        async def _check():
            async with aiohttp.ClientSession() as session:
                return await validate_webhooks(subnets, session)

        results = asyncio.run(_check())

        for subnet in subnets:
            channels = results.get(subnet.netuid, {})
            for channel, valid in channels.items():
                icon = "[green]\u2713[/green]" if valid else "[red]\u2717[/red]"
                console.print(f"  SN {subnet.netuid} {channel}: {icon}")


# ── config ────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Show the current configuration."""
    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    console.print(Panel(f"[bold]Config file:[/bold] {config_path}", border_style="blue"))

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
    for s in subnets:
        status_str = "[green]enabled[/green]" if s.enabled else "[dim]disabled[/dim]"

        channels = []
        if s.alerts.discord:
            channels.append("Discord")
        if s.alerts.telegram:
            channels.append("Telegram")
        ch_str = ", ".join(channels) if channels else "[red]none[/red]"

        console.print(
            f"  [{s.netuid:>3}] {s.label:<20} "
            f"threshold={s.price_threshold_tao:.4f} TAO  "
            f"interval={s.poll_interval_seconds}s  "
            f"alerts={ch_str}  "
            f"{status_str}"
        )

        extras = []
        if s.max_spend_tao:
            extras.append(f"max_spend={s.max_spend_tao:.4f} TAO")
        if s.auto_register:
            extras.append("[green]auto_register=ON[/green]")
        if s.adaptive_polling:
            extras.append(f"adaptive={s.min_poll_interval_seconds}-{s.poll_interval_seconds}s")
        if s.floor_detection:
            extras.append(f"floor_window={s.floor_window}")
        if s.signal_file:
            extras.append(f"signal={s.signal_file}")
        if s.deregister_entries:
            names = ", ".join(e.display_name for e in s.deregister_entries)
            extras.append(f"deregister=[{names}]")

        if extras:
            console.print(f"         {', '.join(extras)}")


# ── wallet ──────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def wallet(ctx: click.Context) -> None:
    """Show wallet status: keys, balance, and registration on configured subnets."""
    from .fetcher import close_subtensor, get_wallet_info_sdk

    config_path = ctx.obj["config_path"]
    try:
        global_cfg, subnets = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    w = global_cfg.wallet
    console.print(
        Panel(
            f"[bold]Wallet: {w.name}/{w.hotkey}[/bold]\nPath: {w.path}",
            border_style="blue",
        )
    )

    try:
        info = get_wallet_info_sdk(w, global_cfg.subtensor_network, global_cfg.subtensor_endpoint)
    except Exception as e:
        console.print(f"[red]Error reading wallet:[/red] {e}")
        close_subtensor()
        return

    # Coldkey
    if info["coldkey_exists"]:
        console.print(f"\n[bold]Coldkey:[/bold] [green]{info['coldkey_ss58']}[/green]")
        if info["balance_tao"] is not None:
            bal = info["balance_tao"]
            bal_style = "green" if bal > 0.1 else "yellow" if bal > 0 else "red"
            console.print(f"  Balance: [{bal_style}]{bal:.6f} TAO[/{bal_style}]")
        else:
            console.print("  Balance: [dim]could not fetch[/dim]")
    else:
        console.print("\n[bold]Coldkey:[/bold] [red]NOT FOUND[/red]")
        console.print(
            f"  [dim]Create with: btcli wallet new_coldkey --wallet.name {w.name} "
            f"--wallet.path {w.path}[/dim]"
        )

    # Hotkey
    if info["hotkey_exists"]:
        console.print(f"\n[bold]Hotkey:[/bold] [green]{info['hotkey_ss58']}[/green]")
        if info["registered_on"]:
            sn_list = ", ".join(str(sn) for sn in info["registered_on"])
            console.print(f"  Registered on: SN{sn_list}")
        else:
            console.print("  Registered on: [dim]none[/dim]")
    else:
        console.print("\n[bold]Hotkey:[/bold] [red]NOT FOUND[/red]")
        console.print(
            f"  [dim]Create with: btcli wallet new_hotkey --wallet.name {w.name} "
            f"--wallet.hotkey {w.hotkey} --wallet.path {w.path}[/dim]"
        )

    # Subnets configured for auto-register
    auto_reg = [s for s in subnets if s.auto_register]
    if auto_reg:
        console.print("\n[bold]Auto-register enabled for:[/bold]")
        for s in auto_reg:
            console.print(f"  SN{s.netuid} ({s.label}) — threshold {s.price_threshold_tao} TAO")

    # Deregister entries
    dereg = [(s, e) for s in subnets for e in s.deregister_entries]
    if dereg:
        console.print(f"\n[bold]Deregister monitor:[/bold] {len(dereg)} hotkey(s)")

    close_subtensor()


# ── Entry point ──────────────────────────────────────────────────────────


def main():
    cli()


if __name__ == "__main__":
    main()
