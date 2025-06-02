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
                print(f"INFO: process_audio task started for client {websocket.remote_address}")
                print("Starting speech recognition in executor...")

                loop = asyncio.get_running_loop()
                transcript_queue = asyncio.Queue()
                processing_exception = None

                # Synchronous wrapper function to run in executor
                def sync_speech_processor(stream, queue_obj):
                    nonlocal processing_exception
                    try:
                        print("DEBUG: sync_speech_processor started...")
                        for segment in speech_to_text(stream):
                            print(f"DEBUG: sync_speech_processor got segment: {segment}")
                            queue_obj.put_nowait(segment)
                        queue_obj.put_nowait(None)  # Sentinel to indicate end of processing
                        print("DEBUG: sync_speech_processor finished...")
                    except Exception as e:
                        print(f"ERROR: Exception in sync_speech_processor: {e}")
                        processing_exception = e
                        queue_obj.put_nowait(None)

                print("DEBUG LE SANG 🇬🇧")

                # Start the synchronous generator in an executor (don't await it yet)
                executor_task = loop.run_in_executor(None, sync_speech_processor, ws_stream, transcript_queue)
                
                # Create a task to consume from the queue concurrently
                async def consume_transcripts():
                    while True:
                        try:
                            # Wait for transcript with a timeout to check if executor is done
                            transcript_segment = await asyncio.wait_for(transcript_queue.get(), timeout=1.0)
                            
                            if transcript_segment is None:  # Sentinel received
                                print("DEBUG: Received sentinel, breaking consume loop")
                                break

                            if processing_exception:
                                print(f"ERROR: An exception occurred during speech processing: {processing_exception}. Breaking loop.")
                                break

                            print(f"Received transcript segment (from queue): {transcript_segment}")
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
                            
                            transcript_queue.task_done()
                            
                        except asyncio.TimeoutError:
                            # Check if the executor task is done
                            if executor_task.done():
                                # Executor finished, check for any remaining items in queue
                                try:
                                    transcript_segment = transcript_queue.get_nowait()
                                    if transcript_segment is None:
                                        break
                                    # Process the remaining segment...
                                    # (same processing logic as above)
                                except asyncio.QueueEmpty:
                                    break
                            # Continue waiting if executor is still running
                            continue

                # Start consuming transcripts concurrently
                consume_task = asyncio.create_task(consume_transcripts())
                
                # Wait for both the executor and consumer to complete
                await asyncio.gather(executor_task, consume_task, return_exceptions=True)
                
                print("DEBUG: Both executor and consumer tasks completed")

                if processing_exception:
                    print(f"ERROR: Final check: Speech processing encountered an error for ws_stream {id(ws_stream)}: {processing_exception}")

            # Handle incoming audio chunks
            async for message in websocket:
                if not message:
                    continue

                if process_task is None:
                    print("First audio chunk received. Starting speech recognition task.")
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
        print(f"TESTPRINT:")
        
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