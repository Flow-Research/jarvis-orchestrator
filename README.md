# Jarvis Orchestrator

Multi-subnet miner management for Bittensor.

## Current System

Jarvis is the subnet-facing miner and admin control plane.

Personal operators do not use the CLI and do not join the subnet directly. They call the shared workstream HTTP API, submit candidate data, and Jarvis decides what becomes canonical miner truth.

The active SN13 path is:

```text
real Gravity/DD -> planner -> durable workstream
-> workstream API submissions -> SN13 intake + quality gate
-> canonical SQLite -> miner index / validator responses
-> upstream export + Jarvis archive
```

The current SN13 workstream model is open competitive intake:

- tasks are open to multiple operators
- operators submit against the published contract
- duplicates and out-of-contract data are rejected
- each task closes when accepted-cap is reached or the task expires

## Structure

```
jarvis-orchestrator/
├── cli/                      # CLI commands
│   └── README.md            # CLI documentation
├── workstream/               # Shared task store, strict API models, FastAPI transport
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

For the current runnable local operator flow, read `docs/RUN_SN13_LOCALLY.md` first.

```bash
# Install
uv pip install --python .venv/bin/python -e .
ln -sf "$(pwd)/.venv/bin/jarvis-miner" ~/.local/bin/jarvis-miner

# CLI help
jarvis-miner --help

# Registration price monitor and old compatibility aliases
jarvis-miner monitor price 13
jarvis-miner monitor watch
jarvis-miner deregister-check

# Admin starts the workstream HTTP boundary
JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON='{"operator_1":"<shared-secret>"}' \
  jarvis-miner workstream serve

# For local-only unsigned development
export JARVIS_WORKSTREAM_REQUIRE_AUTH=0

# Admin publishes planned SN13 work into the durable workstream
jarvis-miner sn13 plan publish --sample-dd --json-output \
  --max-task-cost 20 --expected-reward 30 --expected-submitted 1200 \
  --expected-accepted 900 --duplicate-rate 0.04 --rejection-rate 0.10 \
  --validation-pass-probability 0.95 --payout-basis accepted_scorable_record

# Admin inspects workstream runtime state
jarvis-miner workstream status --json-output
jarvis-miner workstream tasks --status open --json-output

# Admin runs automated DD refresh + publication
jarvis-miner sn13 scheduler run --once \
  --max-task-cost 20 --expected-reward 30 --expected-submitted 1200 \
  --expected-accepted 900 --duplicate-rate 0.04 --rejection-rate 0.10 \
  --validation-pass-probability 0.95 --payout-basis accepted_scorable_record

# SN13 readiness, real Gravity refresh, planning, and local simulation
jarvis-miner sn13 readiness --network testnet
jarvis-miner sn13 dd refresh
jarvis-miner sn13 dd show
jarvis-miner sn13 economics estimate --source X --label '#bittensor' --json-output
jarvis-miner sn13 plan tasks
jarvis-miner sn13 simulate cycle
jarvis-miner sn13 simulate operator --source X --label "#bittensor" --count 5
jarvis-miner sn13 simulate validator --query bucket --source X --label "#bittensor"
```

Machine-readable admin commands accept both `--json-output` and the shorter `--json`.

Mainnet deployment package:

- deployment and cost brief: `docs/JARVIS_MAINNET_READINESS.md`
- Docker image: `Dockerfile`
- Compose stack: `docker-compose.yaml`
- deployment env: `deploy/jarvis.mainnet.env`
- monitor config: `deploy/monitor.mainnet.yaml`

## What Is Runnable Now

Runnable now:

- task publication into durable SQLite workstream
- workstream HTTP API for personal operators
- read-only human runtime dashboard at `/`
- SN13 intake and quality gate into canonical SQLite
- operator stats and audit facts

Not end-to-end complete yet:

- live validator traffic verification on the SN13 listener
- upstream parquet export/upload
- Jarvis archive upload

## Documentation

- [Engineering Gates](docs/ENGINEERING_GATES.md)
- [Workstream Architecture](docs/WORKSTREAM_ARCHITECTURE.md)
- [Official Workstream Operator Skill](docs/skills/jarvis-workstream/SKILL.md)
- [CLI Admin Guide](cli/README.md)
- [Miner Tools](miner_tools/README.md)
- [SN13 Architecture](subnets/sn13/docs/ARCHITECTURE.md)
- [SN13 Operator Contract](subnets/sn13/docs/OPERATOR_CONTRACT.md)
- [SN13 Economics](subnets/sn13/docs/ECONOMICS.md)

## Project-Local Agent Skills

Project-local skills live in `.agents/skills/` and are internal QA/development automation.

Current internal skills:

- `jarvis-test-runner`: lint, focused tests, coverage gate, and integration gate execution
- `jarvis-qa-review`: architecture, economics, durability, and docs review

The external personal-operator instructions are published as [Official Workstream Operator Skill](docs/skills/jarvis-workstream/SKILL.md), not as an internal project skill.

## Testing

```bash
uv run pytest tests/ -v
uv run pytest -q -m integration tests/test_sn13_testcontainers.py
uv run ruff check cli/ miner_tools/ subnets/
```

The integration test suite uses Testcontainers and requires Docker.

Current engineering rule:

- changes require tests
- economic decisions must be explicit
- architecture boundaries must remain consistent with the SN13 docs and workstream docs

## CI

CI runs through `uv`, verifies Docker availability, runs the SN13/CLI unit slice,
and then runs the Testcontainers-backed integration slice.

SN13's supported operator path is workstream-published scrape demand followed by intake enforcement. Old copied upstream docs, generated local state, mock query guides, and validator-query decomposition prototypes are removed from the repository.

## License

Internal use only.
