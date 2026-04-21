# Numinous (SN6) Miner

This miner is designed for the Numinous (SN6) subnet on Bittensor. 
Unlike typical subnets, SN6 uses a **code submission** model where miners implement forecasting agents that are evaluated by validators in isolated sandboxes.

## Architecture

The miner is split into three main components to separate concerns and allow for easier iterative development:

1. **Connection Logic (`connection.py`)**: 
   - Handles all communication with the Numinous Event Platform.
   - Manages Bittensor hotkey signatures for authentication.
   - Implements the agent upload protocol via REST API.

2. **Mining Logic (`logic.py`)**: 
   - Responsible for generating the Python code for the forecasting agent.
   - Currently uses a template-based approach but is designed to be easily integrated with an LLM-based refiner that uses previous performance metrics to improve the agent.

3. **Miner Entry Point (`miner.py`)**:
   - The main process that orchestrates the mining cycle.
   - Inherits from `BaseNeuron` to stay consistent with the project's architecture.
   - Periodically triggers agent generation and upload.

## Configuration

To run the SN6 miner, you can use the following command from the root of the repository:

```bash
export PYTHONPATH=.
python neurons/numinous_sn6/miner.py --netuid 6 --wallet.name <your_wallet> --wallet.hotkey <your_hotkey>
```

Optional SN6 specific configurations:
- `--sn6_env`: `production` (default) or `staging`.
- `--sn6_agent_name`: Custom name for your agent.

## Future Work

- **LLM Integration**: Implement an automated agent refiner in `logic.py` that uses an LLM to rewrite the agent based on event data and historical performance.
- **Improved Testing**: Integrate local testing using the official `numi test-agent` logic before uploading to ensuring reliable submissions.
