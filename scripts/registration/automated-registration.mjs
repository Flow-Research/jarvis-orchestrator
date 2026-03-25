/**
 * Automated Registration Script (R02)
 *
 * Listens to the live Binance WebSocket for BTC/USDT trades. When the
 * price of BTC exceeds a defined threshold, it triggers an automated
 * registration POST request to the orchestrator webhook.
 */

import WebSocket from 'ws';

const WS_URL = process.env.WS_URL || 'wss://stream.binance.com:9443/ws/btcusdt@trade';
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || 'https://webhook.site/';
const RECONNECT_INTERVAL_MS = 5000;
const PRICE_THRESHOLD = parseFloat(process.env.PRICE_THRESHOLD || '95000');

const dummyAgentData = {
  agentName: 'JarvisNode-001',
  walletAddress: '0x0000000000000000000000000000000000000000',
  capabilities: ['automation', 'trading'],
  timestamp: Date.now()
};

let ws;
let isRegistered = false;

function connectWebSocket() {
  console.log(`[WebSocket] Connecting to ${WS_URL}...`);
  ws = new WebSocket(WS_URL);

  ws.on('open', () => {
    console.log('[WebSocket] Connected successfully to the Binance Live Trade stream.');
    console.log(`[Oracle] Waiting for BTC price to exceed $${PRICE_THRESHOLD.toLocaleString()}...\n`);
  });

  ws.on('message', async (data) => {
    try {
      const message = JSON.parse(data);

      if (message.e === 'trade' && message.p) {
        const currentPrice = parseFloat(message.p);

        process.stdout.write(`\r[Live Price] BTC/USDT: $${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} `);

        if (currentPrice > PRICE_THRESHOLD) {
          if (!isRegistered) {
            console.log(`\n\n[WebSocket] Price Window OPEN. BTC hit $${currentPrice.toFixed(2)}.`);
            console.log('[WebSocket] Triggering automated registration...');
            await executeRegistration();
          }
        } else {
          if (isRegistered) {
            console.log(`\n[WebSocket] Price Window CLOSED. BTC dropped to $${currentPrice.toFixed(2)}.`);
            isRegistered = false;
          }
        }
      }
    } catch (error) {
      console.error('\n[WebSocket] Error parsing incoming message:', error.message);
    }
  });

  ws.on('close', () => {
    console.log('\n[WebSocket] Connection closed. Attempting to reconnect in 5 seconds...');
    setTimeout(connectWebSocket, RECONNECT_INTERVAL_MS);
  });

  ws.on('error', (error) => {
    console.error(`\n[WebSocket] Error encountered: ${error.message}`);
    ws.close();
  });
}

async function executeRegistration() {
  try {
    console.log(`[Registration] Sending payload to ${ORCHESTRATOR_URL}...`);

    const response = await fetch(ORCHESTRATOR_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...dummyAgentData,
        timestamp: Date.now()
      })
    });

    if (response.ok) {
      console.log(`[Registration] Registration Successful. Status: ${response.status}`);
      isRegistered = true;
    } else {
      console.error(`[Registration] Failed with status: ${response.status} - ${response.statusText}`);
    }
  } catch (error) {
    console.error('\n[Registration] Network error during registration:', error.message);
  }
}

console.log('--- Initializing Automated Registration Script (R02) ---');
connectWebSocket();
