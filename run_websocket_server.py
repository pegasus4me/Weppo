import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.agents.input.websocket_server import AudioWebSocketServer
import asyncio

if __name__ == "__main__":
    server = AudioWebSocketServer()
    asyncio.run(server.start()) 