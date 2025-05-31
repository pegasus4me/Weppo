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
        try:
            # Create WebSocket stream for this connection
            ws_stream = WebSocketStream(self._rate, self._chunk)
            
            # Start speech recognition in a separate task
            async def process_audio():
                print("Starting speech recognition...")
                for transcript_segment in speech_to_text(ws_stream):
                    print("Received transcript segment:", transcript_segment)
                    if transcript_segment and transcript_segment.strip():
                        await websocket.send(json.dumps({
                            "transcript": transcript_segment,
                            "is_final": True  # Each yielded segment is considered final for this message
                        }))
            
            # Start the audio processing task
            process_task = asyncio.create_task(process_audio())
            
            # Handle incoming audio chunks
            async for message in websocket:
                print(f"Received audio chunk of size: {len(message)} bytes")
                ws_stream.put_audio(message)
            
            # Close the stream
            await ws_stream.__exit__(None, None, None)
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