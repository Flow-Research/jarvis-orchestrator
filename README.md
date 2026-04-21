# Jarvis Orchestrator

Multi-subnet miner management for Bittensor.

## Structure

```
jarvis-orchestrator/
├── cli/                      # CLI commands
│   └── README.md            # CLI documentation
├── subnets/                  # Per-subnet miner implementations
│   ├── sn6/                  # Numinous — forecasting
│   └── sn13/                 # Data Universe — data scraping
├── miner_tools/              # Shared operational tooling
│   └── README.md          # Tools documentation
├── tests/
├── docs/
└── pyproject.toml
```

## Quick Start

```bash
# Install
uv pip install --python .venv/bin/python -e .
ln -sf /home/abiorh/flow/jarvis-orchestrator/.venv/bin/jarvis-miner ~/.local/bin/jarvis-miner

# CLI help
jarvis-miner --help
```

## Documentation

- [CLI Commands](cli/README.md)
- [Miner Tools](miner_tools/README.md)

## Testing

```bash
uv run pytest tests/ -v
uv run ruff check cli/ miner_tools/ subnets/
```

## License

Internal use only.
