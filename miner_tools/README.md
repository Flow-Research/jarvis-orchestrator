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

Edit `miner_tools/config/config.yaml`:

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
jarvis-miner watch
```

## How It Works

### The Monitoring Loop

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

### Global Options

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Config file (default: `miner_tools/config/config.yaml`) |
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
jarvis-miner -c miner_tools/config/config.test.yaml watch
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