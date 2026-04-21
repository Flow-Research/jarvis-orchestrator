import requests
import hashlib
import base64
import bittensor as bt
from typing import Dict, Any

class SN6Connection:
    """
    Handles communication with the Numinous (SN6) Event Platform.
    This encapsulates the 'connection logic' as requested.
    """
    
    BASE_URLS = {
        "production": "https://numinous.earth/api/v3",
        "staging": "https://stg.numinous.earth/api/v3"
    }

    def __init__(self, wallet: bt.Wallet, environment: str = "production"):
        self.wallet = wallet
        self.base_url = self.BASE_URLS.get(environment, environment)
        self.hotkey = wallet.hotkey

    def get_upload_headers(self, file_content: bytes) -> Dict[str, str]:
        """
        Generates the headers required for uploading an agent, including the Bittensor signature.
        """
        ss58_address = self.hotkey.ss58_address
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Payload: {miner_ss58_address}:{file_hash}
        payload = f"{ss58_address}:{file_hash}"
        
        # Sign the payload
        signature = self.hotkey.sign(payload.encode())
        signature_base64 = base64.b64encode(signature).decode()
        
        headers = {
            "Authorization": f"Bearer {signature_base64}",
            "Miner-Public-Key": self.hotkey.public_key.hex(),
            "Miner": ss58_address,
            "X-Payload": payload
        }
        return headers

    def upload_agent(self, agent_name: str, track: str, agent_file_path: str) -> Dict[str, Any]:
        """
        Uploads the agent code to the SN6 platform.
        """
        url = f"{self.base_url}/miner/upload_agent"
        
        try:
            with open(agent_file_path, "rb") as f:
                file_content = f.read()
                
            headers = self.get_upload_headers(file_content)
            
            data = {
                "name": agent_name,
                "track": track
            }
            
            files = {
                "agent_file": (agent_file_path.split("/")[-1], file_content, "text/x-python")
            }
            
            bt.logging.info(f"Uploading agent {agent_name} to {url}...")
            response = requests.post(url, headers=headers, data=data, files=files)
            
            if response.status_code == 200:
                bt.logging.success(f"Successfully uploaded agent: {agent_name}")
                return response.json()
            else:
                bt.logging.error(f"Failed to upload agent: {response.status_code} - {response.text}")
                return {"error": response.text, "status_code": response.status_code}
                
        except Exception as e:
            bt.logging.error(f"Error during agent upload: {str(e)}")
            return {"error": str(e)}
