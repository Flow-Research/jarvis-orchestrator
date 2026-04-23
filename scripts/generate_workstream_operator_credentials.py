#!/usr/bin/env python3
"""Generate workstream operator credentials for external testers."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a server-side operator secret map and a tester handoff file "
            "for the Jarvis workstream API."
        )
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of operator credentials to generate.",
    )
    parser.add_argument(
        "--prefix",
        default="company_tester",
        help="Operator ID prefix. IDs become <prefix>_01, <prefix>_02, ...",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8787",
        help="Workstream API base URL to include in the tester handoff file.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/workstream/tester-pack",
        help="Directory for generated server and handoff files.",
    )
    parser.add_argument(
        "--label",
        default="operators",
        help="Stable label used in generated filenames.",
    )
    return parser.parse_args()


def build_credentials(
    *,
    count: int,
    prefix: str,
    base_url: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    secrets_map: dict[str, str] = {}
    handoff: list[dict[str, str]] = []
    width = max(2, len(str(count)))
    for index in range(1, count + 1):
        operator_id = f"{prefix}_{index:0{width}d}"
        operator_secret = secrets.token_urlsafe(24)
        secrets_map[operator_id] = operator_secret
        handoff.append(
            {
                "operator_id": operator_id,
                "operator_secret": operator_secret,
                "base_url": base_url.rstrip("/"),
            }
    )
    return secrets_map, handoff


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=isinstance(payload, dict)) + "\n")
    temp_path.replace(path)


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be >= 1")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    secrets_map, handoff = build_credentials(
        count=args.count,
        prefix=args.prefix,
        base_url=args.base_url,
    )

    server_path = output_dir / f"{args.label}.server-operator-secrets.json"
    handoff_path = output_dir / f"{args.label}.tester-handoff.json"
    individual_dir = output_dir / f"{args.label}.operators"

    _write_json(server_path, secrets_map)
    _write_json(handoff_path, handoff)
    individual_dir.mkdir(parents=True, exist_ok=True)
    for stale_file in individual_dir.glob("*.json"):
        stale_file.unlink()
    for item in handoff:
        operator_path = individual_dir / f"{item['operator_id']}.json"
        _write_json(operator_path, item)

    print(json.dumps(
        {
            "count": args.count,
            "server_secret_map_path": str(server_path),
            "tester_handoff_path": str(handoff_path),
            "individual_operator_dir": str(individual_dir),
            "base_url": args.base_url.rstrip("/"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
