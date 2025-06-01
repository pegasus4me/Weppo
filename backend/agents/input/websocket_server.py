import asyncio
import websockets
import queue 
import re
import json
import httpx # Added for making API calls
import os # Added for os.path and getenv in main
from google.cloud import speech
from backend.agents.input.speech_input import speech_to_text, WebSocketStream
from backend.services.tts import text_to_speech_stream # Added for TTS

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

# Define the base URL for your FastAPI agent API
# This should ideally come from a config or env variable
AGENT_API_URL = "http://localhost:8000/api/agent/process"

class AudioWebSocketServer:
    def __init__(self, host='localhost', port=8765, rate: int = RATE, chunk: int = CHUNK): # Changed default port for clarity if main API runs on 8000
        self.host = host
        self.port = port
        self._rate = rate
        self._chunk = chunk
        self.clients = set()
        # Initialize httpx client session for reuse
        self.http_client = httpx.AsyncClient()
        print(f"AudioWebSocketServer listening on ws://{self.host}:{self.port}")


    async def _call_agent_api(self, text: str, thread_id: str = "default_websocket_thread") -> str:
        """Helper function to call the agent API."""
        try:
            payload = {"user_query": text, "thread_id": thread_id}
            response = await self.http_client.post(AGENT_API_URL, json=payload)
            response.raise_for_status()  # Raise an exception for bad status codes
            response_data = response.json()
            return response_data.get("response", "Error: No response field in agent output.")
        except httpx.RequestError as e:
            print(f"ERROR: HTTP request to agent API failed: {e}")
            return f"Error: Could not connect to the agent: {e}"
        except httpx.HTTPStatusError as e:
            print(f"ERROR: Agent API returned an error: {e.response.status_code} - {e.response.text}")
            return f"Error: Agent processing failed with status {e.response.status_code}."
        except Exception as e:
            print(f"ERROR: Unexpected error calling agent API: {e}")
            return f"Error: An unexpected error occurred while processing your request with the agent."

    async def handler(self, websocket):
        """Handle individual WebSocket connections for the full audio_in -> agent -> audio_out loop."""
        self.clients.add(websocket)
        print(f"DEBUG: New client connected: {websocket.remote_address}")

        ws_stream = WebSocketStream(self._rate, self._chunk)
        stt_active = False # Flag to control STT processing

        try:
            async for message in websocket:
                if isinstance(message, str):
                    # Handle control messages if any (e.g., start/stop STT)
                    print(f"DEBUG: Received text message: {message}")
                    if message == "START_STT":
                        stt_active = True
                        print("INFO: STT processing activated by client.")
                        # Initialize or reset ws_stream if needed for multiple STT sessions on one connection
                        ws_stream = WebSocketStream(self._rate, self._chunk)
                    elif message == "STOP_STT":
                        stt_active = False
                        print("INFO: STT processing deactivated by client.")
                        ws_stream.__exit__(None, None, None) # Properly close current stream
                         # Process accumulated audio after STOP_STT
                        print("INFO: STOP_STT received. Processing accumulated audio.")
                        # This block is duplicated below for when connection closes. Consider refactoring.
                        await self._process_stt_agent_tts(websocket, ws_stream, is_connection_active=True)
                        ws_stream = WebSocketStream(self._rate, self._chunk) # Reset stream for potential next START_STT
                    continue # Don't process strings as audio

                if not stt_active or not isinstance(message, bytes):
                    if not stt_active:
                        print("DEBUG: Received audio data but STT is not active. Ignoring.")
                    else:
                        print(f"DEBUG: Received non-bytes message while STT active. Type: {type(message)}. Ignoring.")
                    continue
                print(f"GOT AUDIO BYTES: size {len(message)}") # <--- ADD THIS LINE MANUALLY
                ws_stream.put_audio(message)

            # This part executes if the `async for message in websocket:` loop terminates,
            # which usually means the client disconnected.
            if stt_active:
                print("INFO: WebSocket connection closed by client. Processing any pending audio for STT.")
                ws_stream.__exit__(None, None, None) # Ensure all audio is flushed to stream
                await self._process_stt_agent_tts(websocket, ws_stream, is_connection_active=False)


        except websockets.exceptions.ConnectionClosedOK:
            print(f"INFO: Client {websocket.remote_address} disconnected gracefully.")
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"ERROR: Client {websocket.remote_address} connection closed with error: {e}")
        except Exception as e:
            print(f"ERROR: Unexpected error in WebSocket handler for {websocket.remote_address}: {e}")
        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)
            print(f"DEBUG: Client {websocket.remote_address} removed. Total clients: {len(self.clients)}")

    async def _process_stt_agent_tts(self, websocket, ws_stream: WebSocketStream, is_connection_active: bool = True):
        """Helper function to process STT, call agent, and stream TTS response."""
        final_transcript = ""
        loop = asyncio.get_running_loop()
        transcript_segments_queue = asyncio.Queue()
        stt_exception = None

        def sync_stt_runner(stream, t_queue):
            nonlocal stt_exception
            try:
                for segment in speech_to_text(stream): # speech_input.speech_to_text (sync generator)
                    t_queue.put_nowait(segment)
                t_queue.put_nowait(None) # Sentinel
            except Exception as e:
                print(f"ERROR: Exception in STT sync_stt_runner: {e}")
                stt_exception = e
                t_queue.put_nowait(None)

        stt_task = loop.run_in_executor(None, sync_stt_runner, ws_stream, transcript_segments_queue)

        try:
            while True:
                segment = await transcript_segments_queue.get()
                if segment is None:
                    transcript_segments_queue.task_done()
                    break

                print(f"DEBUG: STT segment: {segment}")
                if segment and segment.strip():
                    final_transcript += segment + " "
                transcript_segments_queue.task_done()
            
            await stt_task

            if stt_exception:
                raise stt_exception

            final_transcript = final_transcript.strip()
            print(f"INFO: Final transcript: '{final_transcript}'")

            if final_transcript:
                if is_connection_active:
                    try:
                        if websocket.open: 
                            await websocket.send(json.dumps({"transcript": final_transcript, "is_final": True, "status": "processing_agent"}))
                    except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                        print(f"DEBUG: Failed to send 'transcript' to websocket, connection likely closed or stale: {e}")
                    except Exception as e:
                        print(f"ERROR: Unexpected error during websocket.send (transcript): {e}")
                
                agent_response_text = await self._call_agent_api(final_transcript)
                print(f"INFO: Agent response: '{agent_response_text}'")
                if is_connection_active:
                    try:
                        if websocket.open:
                            await websocket.send(json.dumps({"agent_response": agent_response_text, "status": "processing_tts"}))
                    except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                        print(f"DEBUG: Failed to send 'agent_response' to websocket, connection likely closed or stale: {e}")
                    except Exception as e:
                        print(f"ERROR: Unexpected error during websocket.send (agent_response): {e}")

                if agent_response_text and not agent_response_text.startswith("Error:"):
                    audio_chunk_count = 0
                    async for audio_chunk in text_to_speech_stream(agent_response_text):
                        if audio_chunk and is_connection_active:
                            try:
                                if websocket.open: # Check open before each send
                                    await websocket.send(audio_chunk)
                                    audio_chunk_count += 1 # Increment only on successful send attempt
                                else:
                                    print(f"DEBUG: WebSocket no longer open, skipping send of TTS chunk.")
                                    break # Exit loop if not open
                            except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                                print(f"DEBUG: Failed to send TTS audio chunk, connection likely closed or stale: {e}")
                                break # Exit loop on error
                            except Exception as e:
                                print(f"ERROR: Unexpected error during websocket.send (TTS audio chunk): {e}")
                                break # Exit loop on error
                    print(f"INFO: Sent {audio_chunk_count} audio chunks for TTS.")
                    if is_connection_active:
                        try:
                            if websocket.open:
                                await websocket.send(json.dumps({"status": "tts_complete"}))
                        except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                            print(f"DEBUG: Failed to send 'tts_complete' status to websocket, connection likely closed or stale: {e}")
                        except Exception as e:
                            print(f"ERROR: Unexpected error during websocket.send (tts_complete): {e}")
                elif agent_response_text.startswith("Error:"):
                    if is_connection_active:
                        try:
                            if websocket.open:
                                await websocket.send(json.dumps({"error": agent_response_text, "status": "error_agent"}))
                        except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                            print(f"DEBUG: Failed to send 'error_agent' status to websocket, connection likely closed or stale: {e}")
                        except Exception as e:
                            print(f"ERROR: Unexpected error during websocket.send (error_agent): {e}")
                else:
                    print("INFO: Empty agent response. Nothing to TTS.")
                    if is_connection_active:
                        try:
                            if websocket.open:
                                await websocket.send(json.dumps({"status": "tts_skipped_empty_agent_response"}))
                        except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                            print(f"DEBUG: Failed to send 'tts_skipped_empty_agent_response' status to websocket, connection likely closed or stale: {e}")
                        except Exception as e:
                            print(f"ERROR: Unexpected error during websocket.send (tts_skipped_empty_agent_response): {e}")
            else:
                print("INFO: Empty transcript. Nothing to send to agent.")
                if is_connection_active:
                    try:
                        if websocket.open:
                            await websocket.send(json.dumps({"status": "stt_empty_transcript"}))
                    except (websockets.exceptions.ConnectionClosed, AttributeError) as e:
                        print(f"DEBUG: Failed to send 'stt_empty_transcript' status to websocket, connection likely closed or stale: {e}")
                    except Exception as e:
                        print(f"ERROR: Unexpected error during websocket.send (stt_empty_transcript): {e}")

        except ConnectionResetError:
            print("ERROR: WebSocket connection reset by client during STT/Agent/TTS processing.")
        except websockets.exceptions.ConnectionClosed: # This might be redundant now with specific checks, but good as a fallback
            print("ERROR: WebSocket connection closed unexpectedly during STT/Agent/TTS processing.")
        except Exception as e:
            print(f"ERROR: Error during STT/Agent/TTS processing: {e}")
            if is_connection_active: # Check before attempting to send error
                try:
                    if websocket.open:
                        await websocket.send(json.dumps({"error": str(e), "status": "error_processing"}))
                except (websockets.exceptions.ConnectionClosed, AttributeError) as send_e: # Specific exceptions for send
                    print(f"DEBUG: Failed to send 'error_processing' status to client, connection likely closed or stale: {send_e}")
                except Exception as send_err: 
                    print(f"ERROR: Failed to send error_processing status to client: {send_err}")


    async def start(self):
        """Start the WebSocket server."""
        try:
            server = await websockets.serve(
                self.handler,
                self.host,
                self.port
            )
            print(f"Full Audio Processing WebSocket server started at ws://{self.host}:{self.port}")
            await server.wait_closed()
        finally:
            await self.http_client.aclose()
            print("INFO: HTTP client closed.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    # Determine path to .env file relative to this script's location or project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # .env is expected in 'backend/' directory, script is in 'backend/agents/input/'
    dotenv_path = os.path.join(script_dir, '..', '..', '.env')

    print(f"DEBUG: Loading .env file from: {dotenv_path}")
    if not load_dotenv(dotenv_path=dotenv_path):
        print(f"WARNING: Could not load .env file from {dotenv_path}. Attempting to load from current working directory's .env or system environment.")
        load_dotenv() # Try loading .env from CWD or rely on system env vars

    required_vars = ["ELEVENLABS_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "XAI_API_KEY", "SHOPIFY_STORE_DOMAIN", "GOOGLE_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"ERROR: Missing critical environment variables: {', '.join(missing_vars)}")
        print("Please ensure .env file is correctly set up in the 'backend' directory or variables are set in the environment.")
        # Consider exiting if critical vars are missing, depending on desired behavior
        # exit(1)

    server = AudioWebSocketServer(host='localhost', port=8765)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("INFO: WebSocket server shutting down...")
    except Exception as e:
        print(f"ERROR: Failed to run WebSocket server: {e}")