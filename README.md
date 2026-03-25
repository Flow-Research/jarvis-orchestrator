# Jarvis Orchestrator

The main orchestrator service backing the Jarvis Flow Framework infrastructure.

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```
2. Configure environment rules (copy `.env.example` if applicable, or configure `.env`).

## Scripts

### Automated Registration (R02)
This script acts as the automated listener for orchestrator agent registration. It polls a live WebSocket (default: Binance BTC/USDT live trades) and automatically triggers an agent POST registration to an Orchestrator webhook whenever the `PRICE_THRESHOLD` condition is met.

To test the registration functionality locally against live crypto markets:

```bash
PRICE_THRESHOLD="95000" ORCHESTRATOR_URL="https://webhook.site/YOUR-UUID-HERE" node scripts/registration/automated-registration.mjs
```


## Documentation
Please see `.jarvis/context/` for canonical project structures, technical debt tracking, and roadmap states as dictated by Flow Framework schemas.
