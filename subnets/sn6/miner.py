import time
import sys
import os
from pathlib import Path

# Add the project root to the python path
root = str(Path(__file__).resolve().parent.parent.parent)
if root not in sys.path:
    sys.path.append(root)

import bittensor as bt
from typing import Optional
from template.base.neuron import BaseNeuron
from neurons.numinous_sn6.connection import SN6Connection
from neurons.numinous_sn6.logic import SN6MiningLogic

class NuminousSN6Miner(BaseNeuron):
    """
    Miner for Numinous (SN6). 
    This miner is submission-based (not axon-based).
    It periodically generates, tests, and uploads a forecasting agent.
    """
    
    neuron_type: str = "NuminousSN6Miner"

    def __init__(self, config=None):
        super().__init__(config=config)
        
        # Initialize connection logic
        self.connection = SN6Connection(
            wallet=self.wallet,
            environment=self.config.get("sn6_env", "production")
        )
        
        # Initialize mining logic
        self.mining_logic = SN6MiningLogic(
            agent_name=self.config.get("sn6_agent_name", f"miner_{self.uid}"),
            agent_dir="numinous_agents"
        )
        
        # State tracking
        self.last_upload_time: float = 0
        self.upload_interval: int = 3600 * 24  # Upload once per day by default

    async def forward(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        SN6 is not axon-based, so we don't process incoming synapses.
        We fulfill the abstract requirement here.
        """
        bt.logging.warning("Received a synapse request but SN6 is submission-based. Ignoring.")
        return synapse

    def run(self):
        """
        Main loop for the SN6 miner.
        """
        bt.logging.info("Numinous (SN6) Miner started.")
        
        try:
            while not getattr(self, "should_exit", False):
                # 1. Sync metagraph to stay updated with the network
                self.sync()

                # 2. Check if it's time to upload a new agent
                current_time = time.time()
                if (current_time - self.last_upload_time) >= self.upload_interval:
                    bt.logging.info("Periodic upload triggered for SN6.")
                    
                    # Prepare agent
                    agent_file_path = self.mining_logic.get_and_prepare_agent()
                    
                    # Upload agent
                    result = self.connection.upload_agent(
                        agent_name=self.mining_logic.agent_name,
                        track="general",  # Track could be configurable
                        agent_file_path=agent_file_path
                    )
                    
                    if "error" not in result:
                        self.last_upload_time = current_time
                        bt.logging.success(f"Agent successfully uploaded for SN6: {result}")
                    else:
                        bt.logging.error(f"Failed to upload agent for SN6: {result}")
                
                # 3. Sleep until the next check
                # We can check more frequently (e.g., every 5 minutes)
                bt.logging.debug(f"Miner sleeping for 300 seconds... Step: {self.step}")
                time.sleep(300)
                self.step += 1
                
        except KeyboardInterrupt:
            bt.logging.success("Miner stopping via KeyboardInterrupt.")
        except Exception as e:
            bt.logging.error(f"Unexpected error in miner run loop: {str(e)}")
            import traceback
            bt.logging.error(traceback.format_exc())

# This allows running this script directly
if __name__ == "__main__":
    from template.utils.config import config
    
    # We use the generic BaseNeuron config parser
    # but we can add SN6 specific arguments if needed.
    conf = BaseNeuron.config()
    with NuminousSN6Miner(config=conf) as miner:
        miner.run()
