import asyncio
import websockets
import queue 
import re
import json
from google.cloud import speech
from backend.agents.input.speech_input import speech_to_text, WebSocketStream
from backend.agents.orchestrator.agent import PersonalShopperAgent
from backend.agents.input.elevenlabs import ElevenLabsTTS

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
        # Initialize ElevenLabsTTS client
        self.tts_client = None
        try:
            self.tts_client = ElevenLabsTTS()
            print("ElevenLabsTTS client initialized successfully.")
        except ValueError as e:
            print(f"WARNING: ElevenLabsTTS client initialization failed: {e}. TTS will not be available.")
        except Exception as e: # Catch any other unexpected errors during init
            print(f"WARNING: An unexpected error occurred during ElevenLabsTTS initialization: {e}. TTS will not be available.")
        
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

                                    # Start TTS streaming if client is available
                                    if self.tts_client:
                                        try:
                                            # TTS Streaming Protocol:
                                            # The client will receive a sequence of messages related to TTS streaming for the agent's response.
                                            # It's crucial to handle these messages in order and appropriately.
                                            #
                                            # 1. TTS Starting Notification (JSON):
                                            #    Before any audio data is sent, a JSON message indicates the start of TTS:
                                            #    {
                                            #        "status": "tts_starting",
                                            #        "transcript": "The original transcript segment that prompted this agent response and TTS."
                                            #    }
                                            #    The client can use this to prepare for receiving audio data.
                                            #
                                            # 2. Binary Audio Chunks (WebSocket Binary Frames):
                                            #    Following the "tts_starting" message, a series of binary WebSocket frames will be sent.
                                            #    Each frame contains a chunk of the audio data.
                                            #    The format of this audio (e.g., MP3, PCM) is determined by the `output_format`
                                            #    parameter used in the ElevenLabsTTS class (default is "mp3_44100_128").
                                            #    The client *must* be able to handle this specific audio format.
                                            #
                                            #    Client-side Handling of Audio Chunks:
                                            #    - Buffer the Chunks: The client should accumulate these binary chunks.
                                            #    - Concatenation: Once all chunks are received (signaled by "tts_finished"),
                                            #      concatenate them into a single ArrayBuffer or Blob.
                                            #    - Web Audio API for Playback:
                                            #      - Use `AudioContext.decodeAudioData()` to decode the complete audio data.
                                            #      - Then, play it back using an `AudioBufferSourceNode`.
                                            #    - Advanced Streaming: For lower latency, more advanced techniques could be used,
                                            #      such as Media Source Extensions (MSE) or libraries that abstract away the complexities
                                            #      of streaming playback, but simple buffering and playback after "tts_finished" is a robust start.
                                            #
                                            # 3. TTS Finished Notification (JSON):
                                            #    After all audio chunks for the current agent response have been sent, a JSON message indicates completion:
                                            #    {
                                            #        "status": "tts_finished",
                                            #        "transcript": "The original transcript segment."
                                            #    }
                                            #    At this point, the client should have all the audio data and can proceed with decoding and playback
                                            #    if it hasn't already started a streaming playback.
                                            #
                                            # 4. TTS Error Notification (JSON, Optional):
                                            #    If an error occurs during the TTS process on the server-side, a JSON message will be sent:
                                            #    {
                                            #        "status": "tts_error",
                                            #        "error": "A description of the error.",
                                            #        "transcript": "The original transcript segment."
                                            #    }
                                            #    The client should handle this gracefully, perhaps by informing the user that audio playback failed.
                                            #
                                            # The `transcript` field in these messages helps associate the TTS audio with the specific part of the conversation.
                                            await websocket.send(json.dumps({"status": "tts_starting", "transcript": transcript_segment}))
                                            print(f"Streaming TTS for agent response: '{agent_response}' related to transcript: '{transcript_segment}'")

                                            # Define sentinel and helper for more robust TTS stream handling
                                            _TTS_STREAM_DONE = object()
                                            def _get_next_chunk_sync(iterator, sentinel_on_done):
                                                try:
                                                    return next(iterator)
                                                except StopIteration:
                                                    return sentinel_on_done
                                                # Other exceptions from the iterator will propagate

                                            # Get audio stream from ElevenLabsTTS (which is a synchronous iterator)
                                            loop = asyncio.get_running_loop()
                                            audio_iterator = self.tts_client.stream_audio(agent_response)

                                            # Stream audio chunks to client
                                            while True:
                                                audio_chunk_or_sentinel = await loop.run_in_executor(
                                                    None, _get_next_chunk_sync, audio_iterator, _TTS_STREAM_DONE
                                                )

                                                if audio_chunk_or_sentinel is _TTS_STREAM_DONE:
                                                    # End of audio stream
                                                    break

                                                # If not sentinel, it's an audio chunk
                                                if audio_chunk_or_sentinel: # Ensure chunk has content
                                                    await websocket.send(audio_chunk_or_sentinel)

                                            await websocket.send(json.dumps({"status": "tts_finished", "transcript": transcript_segment}))
                                            print(f"TTS streaming finished for transcript: '{transcript_segment}'")
                                        except Exception as e_tts:
                                            # Catches errors from run_in_executor (if _get_next_chunk_sync itself fails, or underlying iterator fails)
                                            # or from websocket.send()
                                            print(f"ERROR: TTS streaming error for transcript '{transcript_segment}': {e_tts}")
                                            # No need to check for StopIteration here as it's handled by the sentinel
                                            await websocket.send(json.dumps({
                                                "status": "tts_error",
                                                    "error": str(e_tts),
                                                    "transcript": transcript_segment
                                                }))
                                    else:
                                        print(f"Skipping TTS for transcript '{transcript_segment}' because TTS client is not available.")

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