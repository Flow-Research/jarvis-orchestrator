#!/usr/bin/env python3
"""
SN13 listener daemon entrypoint.

This process serves the SN13 protocol surface from canonical SQLite and records
request/response captures for later protocol verification.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB_PATH = PROJECT_ROOT / "subnets" / "sn13" / "data" / "sn13.sqlite3"
DEFAULT_CAPTURE_DIR = PROJECT_ROOT / "subnets" / "sn13" / "listener" / "captures"


def build_parser() -> argparse.ArgumentParser:
    """Build the listener CLI."""
    parser = argparse.ArgumentParser(description="Run the Jarvis SN13 listener daemon.")
    parser.add_argument("--wallet", required=True, help="Bittensor wallet name.")
    parser.add_argument("--hotkey", default="default", help="Bittensor hotkey name.")
    parser.add_argument("--wallet-path", default="~/.bittensor/wallets", help="Wallet root path.")
    parser.add_argument("--network", default="finney", help="Bittensor network name.")
    parser.add_argument("--endpoint", default=None, help="Optional subtensor endpoint override.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(os.environ.get("JARVIS_SN13_DB_PATH", str(DEFAULT_DB_PATH))),
        help="Canonical SQLite path.",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=DEFAULT_CAPTURE_DIR,
        help="Capture output directory.",
    )
    parser.add_argument("--axon-port", type=int, default=8091, help="Axon bind port.")
    parser.add_argument("--axon-ip", default="0.0.0.0", help="Axon bind IP.")
    parser.add_argument("--axon-external-ip", default=None, help="Advertised external IP.")
    parser.add_argument(
        "--axon-external-port",
        type=int,
        default=None,
        help="Advertised external port.",
    )
    parser.add_argument("--max-workers", type=int, default=None, help="Axon worker count.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Start axon locally without subtensor serve registration.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Runtime log level.",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    from subnets.sn13.listener.runtime import SN13ListenerRuntime

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    runtime = SN13ListenerRuntime(
        db_path=args.db_path,
        capture_dir=args.capture_dir,
        wallet_name=args.wallet,
        wallet_hotkey=args.hotkey,
        wallet_path=args.wallet_path,
        network=args.network,
        endpoint=args.endpoint,
        offline=args.offline,
    )
    runtime.start(
        port=args.axon_port,
        ip=args.axon_ip,
        external_ip=args.axon_external_ip,
        external_port=args.axon_external_port,
        max_workers=args.max_workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
