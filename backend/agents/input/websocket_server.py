import asyncio
import websockets
import queue 
import re
import json
from google.cloud import speech
from backend.agents.input.speech_input import speech_to_text, WebSocketStream
from backend.agents.orchestrator.agent import PersonalShopperAgent

"""
ws connection with client <-> server
"""
# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

class AudioWebSocketServer:
    def __init__(self, host='localhost', port=8000, rate: int = RATE, chunk: int = CHUNK, store_domain: str = "www.allbirds.com"):
        self.host = host
        self.port = port
        self._rate = rate
        self._chunk = chunk
        self.clients = set()
          # Initialize the agent
        self.agent = PersonalShopperAgent(store_domain)
        
    async def handler(self, websocket):
        """Handle individual WebSocket connections."""
        self.clients.add(websocket)
        print(f"DEBUG: New client connected: {websocket.remote_address}")
        process_task = None # Initialize process_task
        
        # Generate a unique thread_id for this client session
        client_thread_id = f"client_{id(websocket)}"
        try:
            # Create WebSocket stream for this connection
            ws_stream = WebSocketStream(self._rate, self._chunk)
            
            # Define speech recognition task
            async def process_audio():
                print(f"INFO: process_audio task started for client {websocket.remote_address}") # Modified
                print("Starting speech recognition in executor...") # Kept

                loop = asyncio.get_running_loop()
                transcript_queue = asyncio.Queue()
                processing_exception = None # To capture exceptions from the executor thread

                # Synchronous wrapper function to run in executor
                def sync_speech_processor(stream, queue_obj): # Renamed queue to queue_obj to avoid conflict
                    nonlocal processing_exception
                    try:
                        # Removed: DEBUG: sync_speech_processor started...
                        for segment in speech_to_text(stream): # This is speech_input.speech_to_text
                            # Removed: DEBUG: sync_speech_processor got segment...
                            queue_obj.put_nowait(segment)
                        queue_obj.put_nowait(None)  # Sentinel to indicate end of processing
                        # Removed: DEBUG: sync_speech_processor finished...
                    except Exception as e:
                        print(f"ERROR: Exception in sync_speech_processor: {e}") # Kept
                        processing_exception = e
                        queue_obj.put_nowait(None) # Ensure consumer loop also terminates on error


                # Run the synchronous generator in an executor
                # The 'ws_stream' and 'transcript_queue' are passed as args to sync_speech_processor
                await loop.run_in_executor(None, sync_speech_processor, ws_stream, transcript_queue)
                # Removed: DEBUG: loop.run_in_executor completed...

                # Consume from the queue
                while True:
                    # Removed: DEBUG: process_audio waiting for transcript from queue...
                    transcript_segment = await transcript_queue.get()
                    # Removed: DEBUG: process_audio got transcript from queue...

                    if transcript_segment is None:  # Sentinel received
                        # Removed: DEBUG: process_audio received sentinel...
                        break

                    if processing_exception:
                        print(f"ERROR: An exception occurred during speech processing: {processing_exception}. Breaking loop.") # Kept
                        # Optionally, send an error message to the client
                        # await websocket.send(json.dumps({"error": str(processing_exception)}))
                        break

                    print(f"Received transcript segment (from queue): {transcript_segment}") # Kept
                    if transcript_segment and transcript_segment.strip():
                        await websocket.send(json.dumps({
                            "transcript": transcript_segment,
                            "is_final": True
                        }))

                     # Process with agent and get response
                        try:
                            print(f"Processing transcript with agent: {transcript_segment}")
                            agent_response = await self.process_with_agent(transcript_segment, client_thread_id)
                            print(f"Agent response: {agent_response}")
                            
                            # Send agent response to client
                            await websocket.send(json.dumps({
                                "agent_response": agent_response,
                                "transcript": transcript_segment
                            }))
                        except Exception as e:
                            print(f"ERROR: Exception processing with agent: {e}")
                            await websocket.send(json.dumps({
                                "error": f"Agent processing error: {str(e)}",
                                "transcript": transcript_segment
                            }))
                    transcript_queue.task_done() # Notify queue item processed

                if processing_exception:
                    # Re-raise or handle the exception as appropriate for the server
                    # For now, just printing it prominently in server logs if it reaches here
                    print(f"ERROR: Final check: Speech processing encountered an error for ws_stream {id(ws_stream)}: {processing_exception}") # Kept

                # Removed: DEBUG: process_audio finished consuming queue...

            # Handle incoming audio chunks
            async for message in websocket:
                print(f"Received audio chunk of size: {len(message)} bytes") # Original print

                if not message:
                    # Empty message check removed as per plan, if it's important, it can be re-added with non-DEBUG prefix.
                    continue

                if process_task is None:
                    print("First audio chunk received. Starting speech recognition task.") # Original print
                    process_task = asyncio.create_task(process_audio())

                ws_stream.put_audio(message)
            
            # Close the stream (signals generator to stop)
            await ws_stream.__exit__(None, None, None)

            # Wait for the processing task to complete, if it was started
            if process_task:
                await process_task
                
        finally:
            self.clients.remove(websocket)
    async def process_with_agent(self, transcript: str, thread_id: str) -> str:
        """Process transcript with the agent in a separate thread to avoid blocking."""
        loop = asyncio.get_running_loop()
        
        # Run the agent chat in an executor since it's synchronous
        def run_agent_chat():
            try:
                return self.agent.chat(transcript, thread_id)
            except Exception as e:
                print(f"ERROR: Agent chat error: {e}")
                return f"I encountered an error processing your request: {str(e)}"
        
        # Execute in thread pool
        response = await loop.run_in_executor(None, run_agent_chat)
        return response   
    async def start(self):
        """Start the WebSocket server."""
        server = await websockets.serve(
            self.handler,
            self.host,
            self.port
        )
        print(f"WebSocket server started at ws://{self.host}:{self.port}")
        print(f"Agent initialized for store domain: www.allbirds.com")
        await server.wait_closed()

if __name__ == "__main__":
    server = AudioWebSocketServer()
    asyncio.run(server.start())