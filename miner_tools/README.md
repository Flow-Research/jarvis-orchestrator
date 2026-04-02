# Jarvis Miner — Complete Monitoring Suite

A production-grade CLI tool that does 3 things in one:

1. **Monitor** — Tracks Bittensor subnet registration prices 24/7
2. **Auto-Register** — Automatically registers when price drops below your threshold
3. **Deregister Alerts** — Monitors your hotkeys and alerts you if they get deregistered

```
┌─────────────────────────────────────────────────────────────────┐
│                    BITTENSOR NETWORK                            │
│              Subnet 6, 8, 9, 13, 18, 28, 37, 41, 50           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    JARVIS MINER                                │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │   PRICE     │  │    AUTO     │  │     DEREGISTER      │   │
│  │  MONITOR    │  │  REGISTER   │  │      MONITOR         │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│                                                                 │
│  • Adaptive polling (60-300s)                                   │
│  • Floor detection (best entry points)                         │
│  • Discord/Telegram alerts                                      │
│  • Auto-register when price ≤ threshold                        │
│  • Alerts when hotkeys get deregistered                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    PRICE ALERTS        AUTO-REGISTER      DEREGISTER ALERTS
    (when favorable)    (when triggered)   (if hotkey removed)
```

## Installation

```bash
git clone https://github.com/yourorg/jarvis-orchestrator.git
cd jarvis-orchestrator
uv pip install -e .
```

## Quick Start

### Step 1: Create Wallet (if needed)

```bash
# Create coldkey (your TAO address)
btcli wallet new_coldkey --wallet.name jarvis --wallet.path ~/.bittensor/wallets

# Create hotkey (your miner identity)
btcli wallet new_hotkey --wallet.name jarvis --wallet.hotkey miner1 --wallet.path ~/.bittensor/wallets

# Fund your coldkey with TAO
```

### Step 2: Set up Alerts (optional)

Create `.env` file:

```bash
DISCORD_WEBHOOK="https://discord.com/api/webhooks/XXXXX/XXXXX"
TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
TELEGRAM_USER_ID="123456789"
```

### Step 3: Configure

Create a `.env` file in the project root:

```bash
# Discord — get from Server Settings → Integrations → Webhooks
DISCORD_WEBHOOK=https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE

# Telegram — get from @BotFather
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_USER_ID=123456789
```

Edit `miner_tools/config/config.yaml`:

```yaml
global:
  subtensor_network: finney
  data_dir: data
  
  wallet:
    name: jarvis
    hotkey: miner1
    path: ~/.bittensor/wallets

  alerts:
    channel: both
    discord:
      webhook_url: "${DISCORD_WEBHOOK}"
    telegram:
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_USER_ID}"

subnets:
  - netuid: 13
    nickname: "Data Universe"
    price_threshold_tao: 0.8      # alert when price ≤ 0.8 TAO
    max_spend_tao: 1.5             # never pay more than this
    enabled: true
    # auto_register: true          # uncomment to auto-register
    # deregister:                  # uncomment to monitor hotkeys
    #   - hotkey: "5GrwvaEF..."
    #     label: "MyMiner"
```

### Step 4: Run

```bash
source .venv/bin/activate

# Check wallet
jarvis-miner wallet

# Validate config
jarvis-miner validate

# Check prices (one-shot)
jarvis-miner price

# Start monitoring (runs 24/7)
jarvis-miner watch
```

## How It Works

### When you run `jarvis-miner monitor`:

Two things run in parallel:

**1. Price Monitor** — polls registration costs

```
┌─────────────────────────────────────────────────────────────┐
│                    jarvis-miner watch                             │
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

**2. Deregister Monitor** — checks hotkey status

```
Every 120 seconds → fetch metagraph → compare hotkeys → alert if missing
```

### Auto-Registration Flow

```
Price drops below threshold
        │
        ▼
Send alert (Discord/Telegram)
        │
        ▼
auto_register enabled?
        │
   ┌────┴────┐
   │         │
  Yes        No
   │         │
   ▼         ▼
Burn TAO    Wait
to register
```

### Deregister Monitoring Flow

```
Every 120 seconds
        │
        ▼
Get hotkeys from metagraph
        │
        ▼
Compare with configured hotkeys
        │
   ┌────┴────┐
   │         │
 Registered  Deregistered
   │         │
   ▼         ▼
  No alert   Send alert
             "Your hotkey was
              removed from SN6!"
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `jarvis-miner watch` | Start the monitor daemon (runs until Ctrl+C) |
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
| `jarvis-miner monitor` | Start everything (price monitor + auto-register + deregister) |
| `jarvis-miner price` | Check current prices for all subnets |
| `jarvis-miner price 13` | Check price for subnet 13 only |
| `jarvis-miner status` | Show price history, trends, floor events |
| `jarvis-miner info` | Show subnet metadata from chain |
| `jarvis-miner register 13` | Manually register on subnet 13 |
| `jarvis-miner deregister-check` | Check if your hotkeys are still registered |
| `jarvis-miner wallet` | Show wallet balance and registrations |
| `jarvis-miner validate` | Validate config file |
| `jarvis-miner validate --check-webhooks` | Test webhook connectivity |
| `jarvis-miner config` | Show current configuration |

### Options

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Config file (default: `miner_tools/config/config.yaml`) |
| `-v, --verbose` | Enable debug logging |
| `--version` | Show version |

## Configuration Options

### Global Settings

| Option | Default | Description |
|--------|---------|-------------|
| `subtensor_network` | finney | "finney" (mainnet) or "test" (testnet) |
| `price_source` | auto | "sdk", "api", or "auto" |
| `data_dir` | data | Where to store state |
| `log_level` | INFO | Logging level |
| `alert_cooldown_seconds` | 600 | Seconds between alerts |
| `trend_window` | 6 | Readings for trend calculation |

### Per-Subnet Settings

| Option | Default | Description |
|--------|---------|-------------|
| `netuid` | (required) | Subnet ID |
| `nickname` | Subnet {netuid} | Friendly name |
| `price_threshold_tao` | 0.5 | Alert when price ≤ this |
| `max_spend_tao` | none | Never register above this |
| `poll_interval_seconds` | 300 | Normal polling interval |
| `min_poll_interval_seconds` | 60 | Fast polling near threshold |
| `adaptive_polling` | true | Auto-adjust poll speed |
| `floor_detection` | true | Detect price floors |
| `auto_register` | false | Auto-register when price ≤ threshold |
| `deregister` | [] | Hotkeys to monitor |
| `enabled` | true | Enable/disable |

## Examples

### Example 1: Just Monitoring (no auto-register)

Before using mainnet, test on testnet:

```bash
# Run on testnet
jarvis-miner -c miner_tools/config/config.test.yaml watch
```

### Example 2: Auto-Registration Enabled

```yaml
subnets:
  - netuid: 13
    price_threshold_tao: 0.8
    max_spend_tao: 1.5
    auto_register: true
    enabled: true
```

### Example 3: Deregister Monitoring

```yaml
subnets:
  - netuid: 6
    price_threshold_tao: 0.5
    enabled: true
    deregister:
      - hotkey: "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        label: "MyMiner1"
      - hotkey: "5FHneL4uZ7T2..."
        label: "MyMiner2"
```

### Example 4: Everything Enabled

```yaml
subnets:
  - netuid: 13
    price_threshold_tao: 0.8
    max_spend_tao: 1.5
    auto_register: true
    enabled: true
    deregister:
      - hotkey: "5GrwvaEF..."
        label: "MyMiner"
```

## Alert Levels

| Level | When |
|-------|------|
| EXCELLENT | Price ≤ 50% of threshold |
| GOOD | Price ≤ threshold |
| INFO | Price ≤ 1.5x threshold |
| WARNING | Price ≤ 3x threshold |
| CRITICAL | Price > 3x threshold |
| FLOOR | Price floor detected |

## Available Subnets

| SN | Name | Type |
|----|------|------|
| 6 | Numinous | Forecasting |
| 8 | Vanta | Trading |
| 9 | Pretraining | LLM pretraining |
| 13 | Data Universe | Data scraping |
| 18 | Zeus | Prediction |
| 28 | S&P Oracle | Financial |
| 37 | Finetuning | Model finetuning |
| 41 | Sports Tensor | Sports |
| 50 | Synth | Synthetic data |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Keyfile not found" | Create wallet with btcli |
| "No price history" | Run `jarvis-miner monitor` first |
| "Webhook not working" | Run `jarvis-miner validate --check-webhooks` |
| Need debug logs | `jarvis-miner -v monitor` |

## Project Structure

```
jarvis-orchestrator/
├── miner_tools/
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
uv run pytest tests/ --cov=miner_tools --cov-report=term-missing

# Lint check
uv run ruff check miner_tools/
```

## Threshold Strategy

**Week 1: Discovery** — Run `jarvis-miner watch` and observe. Note the price ranges.

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
→ Run `jarvis-miner watch` first to collect data

**"Webhook not working"**
→ Run `jarvis validate --check-webhooks` to test

**Need debug logs?**
→ `jarvis -v watch`

## License

Internal use only.
