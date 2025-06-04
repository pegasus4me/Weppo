import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.agents.input.websocket_server import ImprovedAudioWebSocketServer
import asyncio

if __name__ == "__main__":
    server = ImprovedAudioWebSocketServer()
    asyncio.run(server.start()) 