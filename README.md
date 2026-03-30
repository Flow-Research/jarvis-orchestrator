# Jarvis Miner — Registration Price Monitor

A production-grade CLI tool for monitoring Bittensor subnet registration burn costs. It tracks prices across multiple subnets, detects price floors, sends alerts to Discord/Telegram, and supports automated registration when prices drop below your threshold.

## Why This Tool?

Registering on Bittensor subnets requires burning TAO (the native token). The cost fluctuates constantly based on demand — sometimes it's 0.3 TAO, other times it spikes to 2+ TAO. 

**The problem:** Manually watching prices is impossible. Prices can spike or drop at any moment, and waiting for the right price means constantly checking.

**The solution:** Jarvis automatically monitors prices 24/7, alerts you when prices drop, and can even auto-register when the price hits your target.

## What It Does

```
┌─────────────────────────────────────────────────────────────────┐
│                    BITTENSOR BLOCKCHAIN                        │
│  Subnet 6, 8, 9, 13, 18, 28, 37, 41, 50                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │ "What's the burn cost?"
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    JARVIS MONITOR                              │
│                                                                 │
│  ✓ Polls prices every 60-300 seconds                           │
│  ✓ Tracks price history & trends                               │
│  ✓ Detects price floors (best entry points)                   │
│  ✓ Sends Discord/Telegram alerts                               │
│  ✓ Auto-registers when price ≤ threshold                      │
│  ✓ Alerts if your miner gets deregistered                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        ▼                                   ▼
   YOU GET ALERT                    AUTO-REGISTRATION
   → decide to register              → happens automatically
```

## Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/yourorg/jarvis-orchestrator.git
cd jarvis-orchestrator

# Install dependencies
uv sync --extra dev

# Install bittensor SDK (required for chain interaction)
uv pip install bittensor
```

### 2. Create a Wallet (if you don't have one)

```bash
# Create a coldkey (your TAO address)
btcli wallet new_coldkey --wallet.name jarvis

# Create a hotkey (your miner identity)
btcli wallet new_hotkey --wallet.name jarvis --wallet.hotkey miner1

# Fund your coldkey with TAO (get from exchange)
```

### 3. Configure

Create a `.env` file in the project root:

```bash
# Discord — get from Server Settings → Integrations → Webhooks
DISCORD_WEBHOOK=https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE

# Telegram — get from @BotFather
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_USER_ID=123456789
```

Edit `jarvis_miner/config/config.yaml`:

```yaml
global:
  subtensor_network: finney        # mainnet (use "test" for testnet)
  data_dir: data
  
  wallet:
    name: jarvis                   # your wallet name
    hotkey: miner1                # your hotkey name

  alerts:
    channel: both
    discord:
      webhook_url: "${DISCORD_WEBHOOK}"
    telegram:
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_USER_ID}"

subnets:
  # Example: Monitor SN13, alert when price ≤ 0.8 TAO
  # Auto-register when price drops to 0.8 TAO
  - netuid: 13
    nickname: "Data Universe"
    price_threshold_tao: 0.8
    max_spend_tao: 1.5            # never pay more than 1.5 TAO
    auto_register: true           # enable auto-registration
    enabled: true
```

### 4. Verify & Run

```bash
# Check your wallet exists and has balance
jarvis wallet

# Validate config
jarvis validate

# Check current prices (one-shot)
jarvis price

# Start monitoring (runs 24/7)
jarvis watch
```

## How It Works

### The Monitoring Loop

```
┌─────────────────────────────────────────────────────────────┐
│                    jarvis watch                             │
│                  (R-01 Price Monitor)                        │
└────────────────────────────┬────────────────────────────────┘
                             │
         Every N seconds ────►│ polls burn cost from chain
                             │
                             ▼
                    ┌─────────────────┐
                    │ Price <=        │
                    │ threshold?      │
                    └────────┬────────┘
                        Yes  │  No
            ┌───────────────┴────────────┐
            ▼                            │
    ┌─────────────────┐                  │
    │ 1. Discord/     │                  │
    │    Telegram     │                  │
    │    alert        │                  │
    └────────┬────────┘                  │
             │                           │
             ▼                           │
    ┌─────────────────┐                  │
    │ 2. auto_       │                  │
    │    register    │                  │
    │    = true?     │                  │
    └────────┬────────┘                  │
        Yes  │                          │
        ┌────┴────┐                     │
        ▼         │                      │
┌─────────────┐  │                      │
│ R-02 Script │◄─┘                      │
│ executes    │                          │
│ burn        │                          │
│ registration                          │
└─────────────┘                          │
                                          │
                                          ▼
                              (wait for next poll cycle)
```

### Adaptive Polling

The monitor intelligently adjusts how often it checks prices:

| Price | Poll Interval | Why |
|-------|---------------|-----|
| Far above threshold (2.0x) | 300s (5 min) | No urgency |
| Getting close (1.5x) | 60s (1 min) | Watch closely |
| Below threshold | 60s (1 min) | Alert mode |

### Floor Detection

Jarvis detects when prices bottom out — often the best time to register:

```
12:00  Price: 0.80 ──┐
12:05  Price: 0.72   │ declining
12:10  Price: 0.55   │
12:15  Price: 0.48   │ ← FLOOR DETECTED!
12:20  Price: 0.50   │ rising
12:25  Price: 0.52 ──┘
         💎 FLOOR ALERT: "Price hit 0.48 TAO, now rising +8%"
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `jarvis watch` | Start the monitor daemon (runs until Ctrl+C) |
| `jarvis price` | One-shot price check for all subnets |
| `jarvis price 13` | Check price for subnet 13 only |
| `jarvis status` | Show price history, trends, floor events |
| `jarvis info` | Show subnet metadata from chain |
| `jarvis register 13` | Manually register on subnet 13 |
| `jarvis deregister-check` | Check if your hotkeys are still registered |
| `jarvis wallet` | Show wallet balance & registration status |
| `jarvis validate` | Validate config file |
| `jarvis validate --check-webhooks` | Test webhook connectivity |
| `jarvis config-show` | Display current configuration |
| `jarvis -v watch` | Run with debug logging |

### Global Options

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Config file (default: `jarvis_miner/config/config.yaml`) |
| `-v, --verbose` | Enable debug logging |
| `--version` | Show version |

## Configuration

### Per-Subnet Options

| Field | Default | Description |
|-------|---------|-------------|
| `netuid` | (required) | Subnet ID (1-255) |
| `nickname` | `"Subnet {netuid}"` | Friendly name for alerts |
| `price_threshold_tao` | `0.5` | Alert when price ≤ this |
| `max_spend_tao` | none | Hard cap — never register above this |
| `poll_interval_seconds` | `300` | Normal polling interval |
| `min_poll_interval_seconds` | `60` | Fast polling when near threshold |
| `adaptive_polling` | `true` | Auto-adjust poll speed |
| `floor_detection` | `true` | Detect price floors |
| `floor_window` | `6` | Readings to detect floor |
| `auto_register` | `false` | Auto-register when price ≤ threshold |
| `deregister` | `[]` | Hotkeys to monitor for deregistration |
| `enabled` | `true` | Enable/disable this subnet |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_WEBHOOK` | * | Discord webhook URL |
| `TELEGRAM_BOT_TOKEN` | * | Telegram bot token |
| `TELEGRAM_USER_ID` | * | Your Telegram chat ID |
| `DISCORD_ROLE` | No | Role to ping on Discord |
| `JARVIS_CONFIG` | No | Custom config path |

*Unless `alerts.channel: none`

## Testnet

Before using mainnet, test on testnet:

```bash
# Run on testnet
jarvis -c jarvis_miner/config/config.test.yaml watch
```

Testnet features:
- `subtensor_network: test` — connects to Bittensor testnet
- Low thresholds (~0.01 TAO) — testnet costs are minimal
- Fast polling (60s) — quick feedback

## Alert Levels

| Level | Emoji | Condition | Action |
|-------|-------|-----------|--------|
| EXCELLENT | 🟢 | Price ≤ 50% of threshold | Register now! |
| GOOD | 🟢 | Price ≤ threshold | Safe to register |
| INFO | 🔵 | Price ≤ 1.5x threshold | Getting close |
| WARNING | 🟠 | Price ≤ 3x threshold | Too expensive |
| CRITICAL | 🔴 | Price > 3x threshold | Don't register |
| FLOOR | 💎 | Price floor detected | Best window! |

## Available Subnets

| SN | Name | Type | Typical Cost |
|----|------|------|--------------|
| 6 | Numinous | Forecasting | 0.3-1.0 TAO |
| 8 | Vanta | Trading | 0.2-0.8 TAO |
| 9 | Pretraining | LLM pretraining | 0.5-2.0 TAO |
| 13 | Data Universe | Data scraping | 0.4-1.5 TAO |
| 18 | Zeus | Prediction | 0.1-0.5 TAO |
| 28 | S&P Oracle | Financial | 0.2-0.8 TAO |
| 37 | Finetuning | Model finetuning | 0.4-1.5 TAO |
| 41 | Sports Tensor | Sports prediction | 0.1-0.4 TAO |
| 50 | Synth | Synthetic data | 0.1-0.5 TAO |

## Project Structure

```
jarvis-orchestrator/
├── jarvis_miner/
│   ├── __init__.py
│   ├── cli.py              # CLI commands
│   ├── config/
│   │   ├── config.yaml    # mainnet config
│   │   └── config.test.yaml # testnet config
│   ├── config.py          # YAML loader + env vars
│   ├── models.py          # data structures
│   ├── fetcher.py         # chain interaction
│   ├── alerter.py         # Discord/Telegram alerts
│   ├── monitor.py         # R-01 price monitor
│   └── deregister.py      # R-03 deregister monitor
├── tests/                 # 120 tests
├── pyproject.toml
└── .env                   # secrets
```

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=jarvis_miner --cov-report=term-missing

# Lint check
uv run ruff check jarvis_miner/
```

## Threshold Strategy

**Week 1: Discovery** — Run `jarvis watch` and observe. Note the price ranges.

**Week 2: Refine** — Adjust thresholds based on observed data:
```yaml
price_threshold_tao: 0.8   # 80% of your 7-day average
```

**Week 3+: Execute** — Enable auto-registration and let Jarvis find the best windows.

## Troubleshooting

**"Environment variable not set"**
→ Check `.env` file exists with correct variable names

**"bittensor SDK not installed"**
→ Run `uv pip install bittensor`

**"No price history found"**
→ Run `jarvis watch` first to collect data

**"Webhook not working"**
→ Run `jarvis validate --check-webhooks` to test

**Need debug logs?**
→ `jarvis -v watch`

## License

Internal use only.
<div align="center">

# **Bittensor Subnet Template** <!-- omit in toc -->
[![Discord Chat](https://img.shields.io/discord/308323056592486420.svg)](https://discord.gg/bittensor)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) 

---

## The Incentivized Internet <!-- omit in toc -->

[Discord](https://discord.gg/bittensor) • [Network](https://taostats.io/) • [Research](https://bittensor.com/whitepaper)
</div>

---
- [Quickstarter template](#quickstarter-template)
- [Introduction](#introduction)
  - [Example](#example)
- [Installation](#installation)
  - [Before you proceed](#before-you-proceed)
  - [Install](#install)
- [Writing your own incentive mechanism](#writing-your-own-incentive-mechanism)
- [Writing your own subnet API](#writing-your-own-subnet-api)
- [Subnet Links](#subnet-links)
- [License](#license)

---
## Quickstarter template

This template contains all the required installation instructions, scripts, and files and functions for:
- Building Bittensor subnets.
- Creating custom incentive mechanisms and running these mechanisms on the subnets. 

In order to simplify the building of subnets, this template abstracts away the complexity of the underlying blockchain and other boilerplate code. While the default behavior of the template is sufficient for a simple subnet, you should customize the template in order to meet your specific requirements.
---

## Introduction

**IMPORTANT**: If you are new to Bittensor subnets, read this section before proceeding to [Installation](#installation) section. 

The Bittensor blockchain hosts multiple self-contained incentive mechanisms called **subnets**. Subnets are playing fields in which:
- Subnet miners who produce value, and
- Subnet validators who produce consensus

determine together the proper distribution of TAO for the purpose of incentivizing the creation of value, i.e., generating digital commodities, such as intelligence or data. 

Each subnet consists of:
- Subnet miners and subnet validators.
- A protocol using which the subnet miners and subnet validators interact with one another. This protocol is part of the incentive mechanism.
- The Bittensor API using which the subnet miners and subnet validators interact with Bittensor's onchain consensus engine [Yuma Consensus](https://bittensor.com/documentation/validating/yuma-consensus). The Yuma Consensus is designed to drive these actors: subnet validators and subnet miners, into agreement on who is creating value and what that value is worth. 

This starter template is split into three primary files. To write your own incentive mechanism, you should edit these files. These files are:
1. `template/protocol.py`: Contains the definition of the protocol used by subnet miners and subnet validators.
2. `neurons/miner.py`: Script that defines the subnet miner's behavior, i.e., how the subnet miner responds to requests from subnet validators.
3. `neurons/validator.py`: This script defines the subnet validator's behavior, i.e., how the subnet validator requests information from the subnet miners and determines the scores.

### Example

The Bittensor Subnet 1 for Text Prompting is built using this template. See [prompting](https://github.com/macrocosm-os/prompting) for how to configure the files and how to add monitoring and telemetry and support multiple miner types. Also see this Subnet 1 in action on [Taostats](https://taostats.io/subnets/netuid-1/) explorer.

---

## Installation

### Before you proceed
Before you proceed with the installation of the subnet, note the following: 

- Use these instructions to run your subnet locally for your development and testing, or on Bittensor testnet or on Bittensor mainnet. 
- **IMPORTANT**: We **strongly recommend** that you first run your subnet locally and complete your development and testing before running the subnet on Bittensor testnet. Furthermore, make sure that you next run your subnet on Bittensor testnet before running it on the Bittensor mainnet.
- You can run your subnet either as a subnet owner, or as a subnet validator or as a subnet miner. 
- **IMPORTANT:** Make sure you are aware of the minimum compute requirements for your subnet. See the [Minimum compute YAML configuration](./min_compute.yml).
- Note that installation instructions differ based on your situation: For example, installing for local development and testing will require a few additional steps compared to installing for testnet. Similarly, installation instructions differ for a subnet owner vs a validator or a miner. 

### Install

- **Running locally**: Follow the step-by-step instructions described in this section: [Running Subnet Locally](./docs/running_on_staging.md).
- **Running on Bittensor testnet**: Follow the step-by-step instructions described in this section: [Running on the Test Network](./docs/running_on_testnet.md).
- **Running on Bittensor mainnet**: Follow the step-by-step instructions described in this section: [Running on the Main Network](./docs/running_on_mainnet.md).

---

## Writing your own incentive mechanism

As described in [Quickstarter template](#quickstarter-template) section above, when you are ready to write your own incentive mechanism, update this template repository by editing the following files. The code in these files contains detailed documentation on how to update the template. Read the documentation in each of the files to understand how to update the template. There are multiple **TODO**s in each of the files identifying sections you should update. These files are:
- `template/protocol.py`: Contains the definition of the wire-protocol used by miners and validators.
- `neurons/miner.py`: Script that defines the miner's behavior, i.e., how the miner responds to requests from validators.
- `neurons/validator.py`: This script defines the validator's behavior, i.e., how the validator requests information from the miners and determines the scores.
- `template/forward.py`: Contains the definition of the validator's forward pass.
- `template/reward.py`: Contains the definition of how validators reward miner responses.

In addition to the above files, you should also update the following files:
- `README.md`: This file contains the documentation for your project. Update this file to reflect your project's documentation.
- `CONTRIBUTING.md`: This file contains the instructions for contributing to your project. Update this file to reflect your project's contribution guidelines.
- `template/__init__.py`: This file contains the version of your project.
- `setup.py`: This file contains the metadata about your project. Update this file to reflect your project's metadata.
- `docs/`: This directory contains the documentation for your project. Update this directory to reflect your project's documentation.

__Note__
The `template` directory should also be renamed to your project name.
---

# Writing your own subnet API
To leverage the abstract `SubnetsAPI` in Bittensor, you can implement a standardized interface. This interface is used to interact with the Bittensor network and can be used by a client to interact with the subnet through its exposed axons.

What does Bittensor communication entail? Typically two processes, (1) preparing data for transit (creating and filling `synapse`s) and (2), processing the responses received from the `axon`(s).

This protocol uses a handler registry system to associate bespoke interfaces for subnets by implementing two simple abstract functions:
- `prepare_synapse`
- `process_responses`

These can be implemented as extensions of the generic `SubnetsAPI` interface.  E.g.:


This is abstract, generic, and takes(`*args`, `**kwargs`) for flexibility. See the extremely simple base class:
```python
class SubnetsAPI(ABC):
    def __init__(self, wallet: "bt.wallet"):
        self.wallet = wallet
        self.dendrite = bt.dendrite(wallet=wallet)

    async def __call__(self, *args, **kwargs):
        return await self.query_api(*args, **kwargs)

    @abstractmethod
    def prepare_synapse(self, *args, **kwargs) -> Any:
        """
        Prepare the synapse-specific payload.
        """
        ...

    @abstractmethod
    def process_responses(self, responses: List[Union["bt.Synapse", Any]]) -> Any:
        """
        Process the responses from the network.
        """
        ...

```


Here is a toy example:

```python
from bittensor.subnets import SubnetsAPI
from MySubnet import MySynapse

class MySynapseAPI(SubnetsAPI):
    def __init__(self, wallet: "bt.wallet"):
        super().__init__(wallet)
        self.netuid = 99

    def prepare_synapse(self, prompt: str) -> MySynapse:
        # Do any preparatory work to fill the synapse
        data = do_prompt_injection(prompt)

        # Fill the synapse for transit
        synapse = StoreUser(
            messages=[data],
        )
        # Send it along
        return synapse

    def process_responses(self, responses: List[Union["bt.Synapse", Any]]) -> str:
        # Look through the responses for information required by your application
        for response in responses:
            if response.dendrite.status_code != 200:
                continue
            # potentially apply post processing
            result_data = postprocess_data_from_response(response)
        # return data to the client
        return result_data
```

You can use a subnet API to the registry by doing the following:
1. Download and install the specific repo you want
1. Import the appropriate API handler from bespoke subnets
1. Make the query given the subnet specific API



# Subnet Links
In order to see real-world examples of subnets in-action, see the `subnet_links.py` document or access them from inside the `template` package by:
```python
import template
template.SUBNET_LINKS
[{'name': 'sn0', 'url': ''},
 {'name': 'sn1', 'url': 'https://github.com/opentensor/prompting/'},
 {'name': 'sn2', 'url': 'https://github.com/bittranslateio/bittranslate/'},
 {'name': 'sn3', 'url': 'https://github.com/gitphantomman/scraping_subnet/'},
 {'name': 'sn4', 'url': 'https://github.com/manifold-inc/targon/'},
...
]
```

## License
This repository is licensed under the MIT License.
```text
# The MIT License (MIT)
# Copyright © 2024 Opentensor Foundation

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
```
