# Bittensor CLI Installation Fix

## The Issue
Bittensor 10.x changed how the CLI works. The `btcli` command is no longer included by default.

## Solution 1: Install via pipx (Recommended)

```bash
# Install pipx if you don't have it
pipx install bittensor

# Then run:
btcli wallet new_coldkey --wallet.name testminer
btcli wallet new_hotkey --wallet.name testminer --wallet.hotkey miner1

# Register on testnet
btcli subnet register --netuid 13 --wallet.name testminer --wallet.hotkey miner1 --subtensor.network test
```

## Solution 2: Use Python API Directly

Create wallet programmatically:

```python
from bittensor import Wallet

# Create wallet with new coldkey
wallet = Wallet(name='testminer')
wallet.create_new_coldkey(
    hotkey_name='miner1',
    use_password=True,
    suppress=True  # Won't prompt for password
)
```

## Solution 3: Old CLI Installation

```bash
pip install "bittensor>=8.0.0,<9.0.0" --force-reinstall
```

This installs bittensor 8.x which has the btcli command included.

## Quick Test

After installing, test with:

```bash
btcli wallet list
btcli subnet list --subtensor.network test
```