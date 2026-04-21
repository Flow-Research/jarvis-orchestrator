# Jarvis Miner Tools

Shared operational tooling for Bittensor subnets.

```
miner_tools/
├── config/               # YAML config files
│   ├── config.yaml      # Mainnet
│   └── config.test.yaml # Testnet
├── config.py           # YAML + env-var loader
├── models.py          # Data structures
├── fetcher.py         # Bittensor chain interactions
├── monitor.py         # Price monitoring engine
├── alerter.py        # Discord + Telegram alerts
└── deregister.py     # Hotkey deregistration monitor
```

## Components

### monitor.py
Adaptive price monitor that polls subnet registration costs and detects floor events.

### alerter.py
Discord/Telegram alert system with cooldown and rate limiting.

### fetcher.py
Bittensor chain interaction - get subnet info, registration costs, metagraph data.

### deregister.py
Monitors configured hotkeys and alerts when they get deregistered.

### config.py
YAML configuration loader with environment variable substitution.

## Configuration

Edit `miner_tools/config/config.yaml`:

```yaml
global:
  subtensor_network: finney
  alerts:
    channel: both
    discord:
      webhook_url: "${DISCORD_WEBHOOK}"
    telegram:
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_USER_ID}"

subnets:
  - netuid: 13
    price_threshold_tao: 0.8
    max_spend_tao: 1.5
    enabled: true
```

## Environment Variables

Create `.env` file:

```bash
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_USER_ID=123456789
```

## Importing

```python
from miner_tools.config import load_config
from miner_tools.monitor import PriceMonitor
from miner_tools.alerter import Alerter
from miner_tools.fetcher import fetch_burn_cost
```

## License

Internal use only.