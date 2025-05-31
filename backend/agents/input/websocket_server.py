import asyncio
import websockets
import queue 
import re
import json
from google.cloud import speech
from backend.agents.input.speech_input import speech_to_text, WebSocketStream
"""
ws connection with client <-> server
"""
# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

class AudioWebSocketServer:
    def __init__(self, host='localhost', port=8000, rate: int = RATE, chunk: int = CHUNK):
        self.host = host
        self.port = port
        self._rate = rate
        self._chunk = chunk
        self.clients = set()
        
    async def handler(self, websocket):
        """Handle individual WebSocket connections."""
        self.clients.add(websocket)
        print(f"DEBUG: New client connected: {websocket.remote_address}")
        process_task = None # Initialize process_task
        try:
            # Create WebSocket stream for this connection
            ws_stream = WebSocketStream(self._rate, self._chunk)
            print(f"DEBUG: ws_stream created: {id(ws_stream)} for client {websocket.remote_address}")
            
            # Define speech recognition task
            async def process_audio():
                print(f"DEBUG: process_audio() CALLED for ws_stream: {id(ws_stream)} client: {websocket.remote_address}")
                print("Starting speech recognition...") # Original print
                for transcript_segment in speech_to_text(ws_stream):
                    print("Received transcript segment:", transcript_segment) # Original print
                    if transcript_segment and transcript_segment.strip():
                        await websocket.send(json.dumps({
                            "transcript": transcript_segment,
                            "is_final": True  # Each yielded segment is considered final for this message
                        }))
            
            print(f"DEBUG: Entering 'async for message in websocket' loop for client {websocket.remote_address}.")
            # Handle incoming audio chunks
            async for message in websocket:
                print(f"Received audio chunk of size: {len(message)} bytes") # Original print

                if not message:
                    print(f"DEBUG: Received empty message from {websocket.remote_address}. Ignoring.")
                    continue

                if process_task is None:
                    print(f"DEBUG: First valid audio chunk received. Creating process_audio task for ws_stream: {id(ws_stream)} client: {websocket.remote_address}.")
                    print("First audio chunk received. Starting speech recognition task.") # Original print
                    process_task = asyncio.create_task(process_audio())

                ws_stream.put_audio(message)
            
            print(f"DEBUG: Exited 'async for message in websocket' loop for client {websocket.remote_address}.")
            # Close the stream (signals generator to stop)
            await ws_stream.__exit__(None, None, None)

            # Wait for the processing task to complete, if it was started
            if process_task:
                await process_task
                
        finally:
            self.clients.remove(websocket)
        
    async def start(self):
        """Start the WebSocket server."""
        server = await websockets.serve(
            self.handler,
            self.host,
            self.port
        )
        print(f"WebSocket server started at ws://{self.host}:{self.port}")
        await server.wait_closed()

if __name__ == "__main__":
    server = AudioWebSocketServer()
    asyncio.run(server.start())