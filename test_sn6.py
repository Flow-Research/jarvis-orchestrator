import hashlib
import base64
import bittensor as bt
from neurons.numinous_sn6.connection import SN6Connection
from neurons.numinous_sn6.logic import SN6MiningLogic
import os
import sys
from pathlib import Path

# Add project root to path
root = str(Path(__file__).resolve().parent)
if root not in sys.path:
    sys.path.append(root)

class MockKeypair:
    def __init__(self):
        self.ss58_address = "5HEV7y3x8888888888888888888888888888888888888888"
        self.public_key = b"\x00" * 32
    def sign(self, data):
        return b"\x00" * 64
    def hex(self):
        return self.public_key.hex()

class MockWallet:
    def __init__(self):
        self.hotkey = MockKeypair()

def test_sn6_miner_components():
    print("--- Starting SN6 Component Test ---")
    
    # 1. Initialize Mock Wallet
    wallet = MockWallet()
    print(f"Mock Wallet initialized: {wallet.hotkey.ss58_address}")

    # 2. Test Mining Logic
    print("\n[1/3] Testing Mining Logic...")
    logic = SN6MiningLogic(agent_name="test_agent", agent_dir="test_agents")
    agent_path = logic.get_and_prepare_agent()
    
    if os.path.exists(agent_path):
        print(f"PASS: Agent generated at {agent_path}")
    else:
        print("FAIL: Agent not generated.")
        return

    # 3. Test Connection Logic (Signing)
    print("\n[2/3] Testing Connection Logic (Signing)...")
    conn = SN6Connection(wallet=wallet, environment="staging")
    
    with open(agent_path, "rb") as f:
        file_content = f.read()
    
    headers = conn.get_upload_headers(file_content)
    
    print(f"Generated Payload: {headers['X-Payload']}")
    print(f"Generated Public Key: {headers['Miner-Public-Key']}")
    print(f"Signature (base64): {headers['Authorization'][:20]}...")
    
    if headers['Miner'] == wallet.hotkey.ss58_address:
        print("PASS: Header address matches wallet.")
    else:
        print(f"FAIL: Header address mismatch!")
        return

    # 4. Success message
    print("\nLocal tests passed! Your miner logic and connection modules are correctly implemented.")
    print("To run a full simulation with Bittensor's built-in mock mode, use:")
    print("python neurons/numinous_sn6/miner.py --mock --netuid 6 --logging.trace")

if __name__ == "__main__":
    test_sn6_miner_components()
