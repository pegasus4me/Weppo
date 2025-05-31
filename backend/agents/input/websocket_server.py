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
                print("Starting speech recognition in executor...") # New log

                loop = asyncio.get_running_loop()
                transcript_queue = asyncio.Queue()
                processing_exception = None # To capture exceptions from the executor thread

                # Synchronous wrapper function to run in executor
                def sync_speech_processor(stream, queue_obj): # Renamed queue to queue_obj to avoid conflict
                    nonlocal processing_exception
                    try:
                        print(f"DEBUG: sync_speech_processor started for ws_stream: {id(stream)}")
                        for segment in speech_to_text(stream): # This is speech_input.speech_to_text
                            print(f"DEBUG: sync_speech_processor got segment: '{segment}', putting to queue.")
                            queue_obj.put_nowait(segment)
                        queue_obj.put_nowait(None)  # Sentinel to indicate end of processing
                        print(f"DEBUG: sync_speech_processor finished for ws_stream: {id(stream)}")
                    except Exception as e:
                        print(f"ERROR: Exception in sync_speech_processor: {e}")
                        processing_exception = e
                        queue_obj.put_nowait(None) # Ensure consumer loop also terminates on error


                # Run the synchronous generator in an executor
                # The 'ws_stream' and 'transcript_queue' are passed as args to sync_speech_processor
                await loop.run_in_executor(None, sync_speech_processor, ws_stream, transcript_queue)
                print(f"DEBUG: loop.run_in_executor completed for ws_stream: {id(ws_stream)}")

                # Consume from the queue
                while True:
                    print(f"DEBUG: process_audio waiting for transcript from queue for ws_stream: {id(ws_stream)}")
                    transcript_segment = await transcript_queue.get()
                    print(f"DEBUG: process_audio got transcript from queue: '{transcript_segment}' for ws_stream: {id(ws_stream)}")

                    if transcript_segment is None:  # Sentinel received
                        print(f"DEBUG: process_audio received sentinel, breaking loop for ws_stream: {id(ws_stream)}")
                        break

                    if processing_exception:
                        print(f"ERROR: An exception occurred during speech processing: {processing_exception}. Breaking loop.")
                        # Optionally, send an error message to the client
                        # await websocket.send(json.dumps({"error": str(processing_exception)}))
                        break

                    # Original print was "Received transcript segment:", now using a more specific one
                    print(f"Received transcript segment (from queue): {transcript_segment}")
                    if transcript_segment and transcript_segment.strip():
                        await websocket.send(json.dumps({
                            "transcript": transcript_segment,
                            "is_final": True
                        }))

                    transcript_queue.task_done() # Notify queue item processed

                if processing_exception:
                    # Re-raise or handle the exception as appropriate for the server
                    # For now, just printing it prominently in server logs if it reaches here
                    print(f"ERROR: Final check: Speech processing encountered an error for ws_stream {id(ws_stream)}: {processing_exception}")

                print(f"DEBUG: process_audio finished consuming queue for ws_stream: {id(ws_stream)}")

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