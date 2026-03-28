/**
 * Registration Price Monitor (R-01)
 *
 * Continuously polls taostats.io for the current burn cost on a specified subnet.
 * Compares the live price against a configured threshold and dispatches an alert
 * to Discord when the price is at or below the threshold.
 */

import fs from 'node:fs/promises';
import path from 'node:path';

// Helper function to extract CLI args
function getArg(flag, defaultValue = null) {
  const index = process.argv.indexOf(flag);
  return index > -1 && index + 1 < process.argv.length ? process.argv[index + 1] : defaultValue;
}

const netuidRaw = getArg('--netuid') || getArg('-n');
const priceThresholdRaw = getArg('--price-threshold') || getArg('-t');
const alertChannel = getArg('--alert-channel') || getArg('-w');
const pollIntervalRaw = getArg('--poll-interval', '300');

if (!netuidRaw || !priceThresholdRaw) {
  console.error('Usage: node registration-price-monitor.mjs --netuid <id> --price-threshold <float> [--alert-channel <webhook_url>] [--poll-interval <seconds>]');
  process.exit(1);
}

const netuid = parseInt(netuidRaw, 10);
const priceThresholdTao = parseFloat(priceThresholdRaw);
const pollIntervalSeconds = parseInt(pollIntervalRaw, 10);
const pollIntervalMs = pollIntervalSeconds * 1000;

let lastPrice = null;

async function sendDiscordAlert(content) {
  if (!alertChannel) return;
  try {
    const res = await fetch(alertChannel, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    });
    if (!res.ok) {
      console.warn(`[Discord] Failed to send alert: ${res.status}`);
    }
  } catch (err) {
    console.error(`[Discord] Error sending webhook: ${err.message}`);
  }
}

async function writePriceHistory(entry) {
  const historyPath = path.resolve(process.cwd(), 'price_history.json');
  let history = [];
  try {
    const fileContent = await fs.readFile(historyPath, 'utf8');
    history = JSON.parse(fileContent);
  } catch (err) {
    if (err.code !== 'ENOENT') {
      console.error('[History] Failed to read history file:', err);
    }
  }

  history.push(entry);

  try {
    await fs.writeFile(historyPath, JSON.stringify(history, null, 2));
  } catch (err) {
    console.error('[History] Failed to write to history file:', err);
  }
}

async function fetchSubnetBurnCost() {
  try {
    const res = await fetch(`https://taostats.io/api/subnets/${netuid}`);
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const data = await res.json();
    return data && data.burn_cost_tao ? parseFloat(data.burn_cost_tao) : null;
  } catch (error) {
    console.warn(`[API] Could not fetch real-time burn cost: ${error.message}`);
    return null;
  }
}

async function poll() {
  console.log(`\n[Monitor] Checking price for Subnet ${netuid}...`);
  const currentCost = await fetchSubnetBurnCost();

  if (currentCost !== null) {
    let trend = 'stable';
    if (lastPrice !== null) {
      if (currentCost > lastPrice) trend = 'rising';
      if (currentCost < lastPrice) trend = 'falling';
    }

    console.log(`[Monitor] Live Cost: ${currentCost} TAO (Trend: ${trend})`);

    const entry = {
      netuid,
      burn_cost_tao: currentCost,
      trend,
      timestamp: new Date().toISOString()
    };
    await writePriceHistory(entry);

    if (currentCost <= priceThresholdTao) {
      console.log(`[Alert] Burn cost (${currentCost} TAO) is <= threshold (${priceThresholdTao} TAO)!`);
      await sendDiscordAlert(`🚨 **Registration Price Alert** 🚨\nSubnet: \`${netuid}\`\nCurrent Cost: \`${currentCost} TAO\`\nThreshold Met: \`${priceThresholdTao} TAO\``);
      
      // We do not auto-exit here because prices fluctuate; we continue polling or let the operator stop it
    }

    lastPrice = currentCost;
  }

  setTimeout(poll, pollIntervalMs);
}

console.log(`--- Initializing Registration Price Monitor (R-01) ---`);
console.log(`Subnet: ${netuid}`);
console.log(`Threshold: <= ${priceThresholdTao} TAO`);
console.log(`Poll Interval: ${pollIntervalSeconds} seconds`);
console.log(`Alert Webhook: ${alertChannel ? 'Configured' : 'None'}`);

poll();
