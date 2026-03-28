/**
 * Automated Registration Script (R-02)
 *
 * Executes subnet registration for a specified hotkey without requiring
 * manual password entry. Uses environment variables to handle wallet decryption,
 * enabling fully automated registration when triggered by R-01's price alert.
 * Ensures the operator can act within seconds of a favorable price window
 * without human intervention.
 */

import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';

const execAsync = promisify(exec);

// Helper function to extract CLI args
function getArg(flag) {
  const index = process.argv.indexOf(flag);
  return index > -1 && index + 1 < process.argv.length ? process.argv[index + 1] : null;
}

async function fetchSubnetBurnCost(netuid) {
  try {
    // Attempt taostats API structure based on MVP spec
    const res = await fetch(`https://taostats.io/api/subnets/${netuid}`);
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const data = await res.json();
    return data && data.burn_cost_tao ? parseFloat(data.burn_cost_tao) : null;
  } catch (error) {
    console.warn(`[Warning] Could not fetch real-time burn cost from taostats: ${error.message}`);
    return null;
  }
}

async function fetchTaoUsdPrice() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd');
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const data = await res.json();
    return data?.bittensor?.usd || null;
  } catch (error) {
    console.warn(`[Warning] Could not fetch TAO/USD price: ${error.message}`);
    return null;
  }
}

async function writeToBudgetLedger(entry) {
  // Use root repository path for budget_ledger.json
  const ledgerPath = path.resolve(process.cwd(), 'budget_ledger.json');
  
  let ledger = [];
  try {
    const fileContent = await fs.readFile(ledgerPath, 'utf8');
    ledger = JSON.parse(fileContent);
  } catch (err) {
    if (err.code !== 'ENOENT') {
      console.error('[Ledger] Failed to read ledger:', err);
    }
  }

  ledger.push(entry);

  try {
    await fs.writeFile(ledgerPath, JSON.stringify(ledger, null, 2));
    console.log(`[Ledger] Wrote successful registration to ${ledgerPath}`);
  } catch (err) {
    console.error('[Ledger] Failed to write to ledger:', err);
  }
}

async function run() {
  const netuidRaw = getArg('--netuid') || getArg('-n');
  const walletName = getArg('--wallet-name') || getArg('-w');
  const hotkeyName = getArg('--hotkey-name') || getArg('-h');
  const maxSpendTaoRaw = getArg('--max-spend-tao') || getArg('-m');
  const currentBurnCostOverride = getArg('--current-burn-cost') || getArg('-c');
  const isDryRun = process.argv.includes('--dry-run');

  if (!netuidRaw || !walletName || !hotkeyName) {
    console.error('Usage: node automated-registration.mjs --netuid <id> --wallet-name <str> --hotkey-name <str> [--max-spend-tao <float>] [--current-burn-cost <float>] [--dry-run]');
    process.exit(1);
  }

  const netuid = parseInt(netuidRaw, 10);
  const maxSpendTao = maxSpendTaoRaw ? parseFloat(maxSpendTaoRaw) : null;

  console.log(`--- Initializing Automated Registration Script (R-02) ---`);
  console.log(`Target Netuid: ${netuid}`);
  console.log(`Wallet: ${walletName}`);
  console.log(`Hotkey: ${hotkeyName}`);
  if (isDryRun) console.log(`[Mode] DRY RUN ENABLED. APIs and CLI will be mocked.`);

  // 1. Safety check for Max Spend TAO
  let currentBurnCost = null;

  if (currentBurnCostOverride) {
      currentBurnCost = parseFloat(currentBurnCostOverride);
      console.log(`[Info] Using manual current burn cost override: ${currentBurnCost} TAO`);
  } else if (isDryRun) {
      // Mock API cost for testing
      currentBurnCost = 0.05;
      console.log(`[Mock] API fetch mocked. Returning fake burn cost: ${currentBurnCost} TAO`);
  } else {
      currentBurnCost = await fetchSubnetBurnCost(netuid);
  }
  
  if (maxSpendTao !== null) {
      console.log(`Max Spend Cap defined: ${maxSpendTao} TAO`);
      
      if (currentBurnCost !== null) {
          console.log(`Current Burn Cost: ${currentBurnCost} TAO`);
          if (currentBurnCost > maxSpendTao) {
             console.error(`[Abort] Current burn cost (${currentBurnCost} TAO) exceeds max spend cap (${maxSpendTao} TAO).`);
             process.exit(1);
          }
      } else {
          console.error(`[Abort] Max spend cap is defined (${maxSpendTao} TAO), but unable to verify current burn cost from taostats.\n> [Fix] To bypass the API check, run the script again and manually provide the price using: --current-burn-cost <float>`);
          process.exit(1);
      }
  }

  // Verify wallet password environment variable
  const expectedEnvVar = `BT_COLD_PW_${walletName}`;
  const envVarUpperCase = `BT_COLD_PW_${walletName.toUpperCase()}`;
  if (!process.env[expectedEnvVar] && !process.env[envVarUpperCase]) {
    console.warn(`[Warning] No wallet decryption password found in '${expectedEnvVar}' or '${envVarUpperCase}'. Registration might stall if prompted for a password!`);
  }

  // 2. Execute btcli 
  console.log(`[Registration] Executing btcli subnets register...`);
  const cmd = `btcli subnets register --netuid ${netuid} --wallet.name ${walletName} --wallet.hotkey ${hotkeyName} --subtensor.network finney --no_prompt`;
  
  let txHash = null;
  let success = false;
  let finalTaoSpent = currentBurnCost || 0.1;

  try {
     if (isDryRun) {
         console.log(`[Mock Exec] Simulating command execution:`);
         console.log(`$ ${cmd}`);
         success = true;
         txHash = "0x" + Array(64).fill(0).map(() => Math.floor(Math.random() * 16).toString(16)).join('');
         console.log(`[Mock Exec] Simulated Success! Hash: ${txHash}`);
     } else {
         const { stdout, stderr } = await execAsync(cmd, { env: process.env });
         console.log(`[btcli] execution complete. Output:`);
         console.log(stdout);
         
         // Determine success by checking stdout
         if (stdout.toLowerCase().includes('success') || stdout.toLowerCase().includes('registered') || (!stderr && stdout.trim() !== '')) {
             success = true;
             
             const txMatch = stdout.match(/0x[a-fA-F0-9]{64}/);
             if (txMatch) txHash = txMatch[0];

             // btcli might format cost differently, attempting to match "Cost: 0.123 TAO" or similar
             const costMatch = stdout.match(/Cost:?\s*([\d.]+)\s*TAO/i) || stdout.match(/spent:?\s*([\d.]+)\s*TAO/i);
             if (costMatch) finalTaoSpent = parseFloat(costMatch[1]);

         } else if (stderr) {
             console.error(`[btcli] Error running command:\n${stderr}`);
             process.exit(1);
         }
     }
  } catch (execError) {
      if (execError.code === 127 || (execError.message && execError.message.includes('not found'))) {
          console.error(`\n[Fatal Error] 'btcli' command not found! Make sure Bittensor is installed and accessible in your environment's path.`);
      } else {
          console.error(`\n[Registration] Failed to execute registration command.`);
          console.error(execError.stderr || execError.message);
      }
      process.exit(1);
  }

  // 3. Log to B-01 if successful
  if (success) {
      let usdPrice = await fetchTaoUsdPrice();
      let usdEquiv = null;
      if (usdPrice !== null && finalTaoSpent !== null) {
          usdEquiv = parseFloat((usdPrice * finalTaoSpent).toFixed(2));
      }

      const ledgerEntry = {
          netuid,
          tao_spent: finalTaoSpent,
          usd_equiv: usdEquiv,
          timestamp: new Date().toISOString(),
          tx_hash: txHash || "tx_hash_not_found_in_stdout",
          hotkey: hotkeyName
      };

      await writeToBudgetLedger(ledgerEntry);
      console.log(`[Registration] Completed successfully! Saved to budget ledger.`);
  }
}

run();
