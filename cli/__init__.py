#!/usr/bin/env python3
"""
Jarvis-Miner CLI

Entry point that disables bittensor automatic CLI.
"""

import os
from pathlib import Path

os.environ["BT_CLI_NO_AUTO"] = "1"


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load environment variables from a .env file if it exists."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

from cli.main import cli  # noqa: E402 - Must load .env before CLI to configure workstream

if __name__ == "__main__":
    import sys

    sys.exit(cli())
