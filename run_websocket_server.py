import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.agents.input.websocket_server import AudioWebSocketServer
from backend.agents.orchestrator.agent import PersonalShopperAgent
import asyncio

if __name__ == "__main__":
    # Initialize the PersonalShopperAgent
    # You might need to configure the store_domain, e.g., from environment variables or a config file
    store_domain = "www.allbirds.com" # Replace with actual domain or config mechanism
    print(f"Initializing PersonalShopperAgent for store: {store_domain}")
    agent = PersonalShopperAgent(store_domain=store_domain)
    print("PersonalShopperAgent initialized.")

    server = AudioWebSocketServer(agent=agent)
    asyncio.run(server.start())