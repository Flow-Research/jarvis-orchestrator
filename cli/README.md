# Jarvis Miner CLI

Unified CLI for wallet, miner, network, and config operations.

## Installation

```bash
uv pip install -e .
```

## Usage

```bash
jarvis-miner [OPTIONS] COMMAND [ARGS]...
```

## Commands

### wallet

Wallet operations.

```bash
# Show wallet balance and registrations
jarvis-miner wallet info
```

### network

Network registration and monitoring.

```bash
# Show registration burn cost on the default network
jarvis-miner network price

# Show registration burn cost with subnet context
jarvis-miner network price --subnet 13

# Show subnet info from chain
jarvis-miner network info --subnet 13

# Register on subnet
jarvis-miner network register --subnet 13
```

### miner

Manage miner listener.

```bash
# Start miner listener
jarvis-miner miner start --subnet 13

# Stop miner listener
jarvis-miner miner stop --subnet 13

# Show miner status
jarvis-miner miner status --subnet 13
```

### config

Configuration management.

```bash
# Show current configuration
jarvis-miner config show

# Validate configuration
jarvis-miner config validate
```

## Options

| Option | Description |
|--------|-------------|
| `--version` | Show version |
| `-c, --config PATH` | Config file path |
| `-v, --verbose` | Enable debug logging |

## Examples

### Check price before registering

```bash
jarvis-miner network price --subnet 13
```

### Start miner on testnet

```bash
jarvis-miner miner start --subnet 13 --network testnet
```

### View wallet status

```bash
jarvis-miner wallet info
```

## Config File

Default: `miner_tools/config/config.yaml` or set `JARVIS_CONFIG` env var.

 Override with:
```bash
jarvis-miner -c myconfig.yaml config show
jarvis-miner -c myconfig.yaml network price --subnet 13
```

## License

Internal use only.
