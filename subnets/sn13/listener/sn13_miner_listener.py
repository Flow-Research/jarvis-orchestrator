#!/usr/bin/env python3
"""
Simple SN13 miner listener - receives and logs validator queries.
"""

import asyncio
import traceback
import bittensor as bt
from bittensor_wallet import Wallet

try:
    from .sn13_decomposition import DEFAULT_TESTNET, SN13_NETUID
except ModuleNotFoundError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sn13_decomposition import DEFAULT_TESTNET, SN13_NETUID


async def forward_get_miner_index(synapse: bt.Synapse) -> bt.Synapse:
    print(f"[QUERY] GetMinerIndex received")
    print(f"  - from axon: {synapse.axon}")
    print(f"  - dendrite: {synapse.dendrite}")
    return synapse


async def main():
    try:
        wallet = Wallet(name="sn13miner_nopw")
        print(f"Wallet: {wallet.name}")

        subtensor = bt.Subtensor(network=DEFAULT_TESTNET)
        print(f"Connected to subtensor network: {DEFAULT_TESTNET}")

        print("Creating axon...")
        axon = bt.Axon(wallet=wallet, port=8091)
        print("Axon created")

        print("Attaching...")
        axon.attach(forward_fn=forward_get_miner_index)
        print("Attached")

        print("Serving to subnet...")
        axon.serve(netuid=SN13_NETUID, subtensor=subtensor)
        print(f"Served, external_ip: {axon.external_ip}")

        print("Starting server...")
        axon.start()
        print("Started")

        print("Listening for validator queries on port 8091...")
        print(f"External IP: {axon.external_ip}:{axon.external_port}")

        while True:
            await asyncio.sleep(30)
            print(".", end="", flush=True)
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
