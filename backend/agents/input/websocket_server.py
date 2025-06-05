import asyncio
import websockets
import queue 
import json
from backend.agents.input.speech_input import speech_to_text, WebSocketStream
from backend.agents.orchestrator.agent import PersonalShopperAgent
from backend.agents.input.elevenlabs import ElevenLabsTTS

class ImprovedAudioWebSocketServer:
    def __init__(self, host='localhost', port=8000, rate: int = 16000, chunk: int = 1600, store_domain: str = "www.allbirds.com"):
        self.host = host
        self.port = port
        self._rate = rate
        self._chunk = chunk
        self.clients = {}  # Track client sessions
        
        # Initialize the agent
        self.agent = PersonalShopperAgent(store_domain)
        
        # Initialize ElevenLabsTTS client
        self.tts_client = None
        try:
            self.tts_client = ElevenLabsTTS()
            print("ElevenLabsTTS client initialized successfully.")
        except Exception as e:
            print(f"WARNING: ElevenLabsTTS initialization failed: {e}")

    async def handler(self, websocket):
        """Handle individual WebSocket connections with persistent session."""
        client_id = id(websocket)
        client_thread_id = f"client_{client_id}"
        
        # Initialize client session
        self.clients[client_id] = {
            'websocket': websocket,
            'thread_id': client_thread_id,
            'audio_stream': None,
            'stt_task': None,
            'conversation_active': True
        }
        
        print(f"New client connected: {websocket.remote_address}")
        
        try:
            await self.handle_client_session(client_id)
        except websockets.exceptions.ConnectionClosed:
            print(f"Client {client_id} disconnected")
        except Exception as e:
            print(f"Error handling client {client_id}: {e}")
        finally:
            # Cleanup
            if client_id in self.clients:
                await self.cleanup_client(client_id)

    async def handle_client_session(self, client_id):
        """Handle the entire client session with persistent connection."""
        client = self.clients[client_id]
        websocket = client['websocket']
        
        # Send initial greeting
        await websocket.send(json.dumps({
            "type": "greeting",
            "message": "Connected to Personal Shopping Assistant. Start speaking!"
        }))
        
        # Process messages continuously
        async for message in websocket:
            try:
                # Handle different message types
                if isinstance(message, bytes):
                    # Audio data
                    await self.handle_audio_chunk(client_id, message)
                else:
                    # JSON control messages
                    data = json.loads(message)
                    await self.handle_control_message(client_id, data)
                    
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid message format"
                }))
            except Exception as e:
                print(f"Error processing message for client {client_id}: {e}")

    async def handle_audio_chunk(self, client_id, audio_data):
        """Handle incoming audio chunks."""
        client = self.clients[client_id]
        
        # Initialize audio stream if not exists
        if client['audio_stream'] is None:
            client['audio_stream'] = WebSocketStream(self._rate, self._chunk)
            # Start STT processing
            client['stt_task'] = asyncio.create_task(
                self.process_speech_to_text(client_id)
            )
        
        # Add audio data to stream
        client['audio_stream'].put_audio(audio_data)

    async def handle_control_message(self, client_id, data):
        """Handle control messages from client."""
        client = self.clients[client_id]
        websocket = client['websocket']
        
        message_type = data.get('type')
        
        if message_type == 'start_listening':
            await websocket.send(json.dumps({
                "type": "listening_started",
                "message": "Listening for audio..."
            }))
            
        elif message_type == 'stop_listening':
            await self.stop_current_stt(client_id)
            
        elif message_type == 'text_input':
            # Handle text input directly
            text = data.get('text', '')
            if text.strip():
                await self.process_user_input(client_id, text)

    async def process_speech_to_text(self, client_id):
        """Process speech to text for a client."""
        client = self.clients[client_id]
        websocket = client['websocket']
        audio_stream = client['audio_stream']
        
        try:
            # Use the speech_to_text generator
            async for transcript in self.async_speech_to_text(audio_stream):
                if transcript and transcript.strip():
                    # Send transcript to client
                    await websocket.send(json.dumps({
                        "type": "transcript",
                        "text": transcript,
                        "is_final": True
                    }))
                    
                    # Process with agent
                    await self.process_user_input(client_id, transcript)
                    
        except Exception as e:
            print(f"STT processing error for client {client_id}: {e}")
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Speech recognition error: {str(e)}"
            }))

    async def async_speech_to_text(self, audio_stream):
        """Async wrapper for speech_to_text generator."""
        loop = asyncio.get_running_loop()
        
        def sync_stt_worker(): # Renamed for clarity, as it's the worker function
            try:
                # This function runs in the executor thread.
                # It consumes the entire sync generator and returns a list of transcripts.
                return list(speech_to_text(audio_stream))
            except Exception as e:
                print(f"STT error in executor thread: {e}") # More specific error message
                return [] # Return an empty list on error to prevent breaking the caller
        
        # Directly await the Future returned by run_in_executor.
        # 'results' will be the list of transcripts once sync_stt_worker completes.
        results = await loop.run_in_executor(None, sync_stt_worker)
        
        # Yield each transcript from the collected list.
        for transcript in results:
            yield transcript

    async def process_user_input(self, client_id, user_input):
        """Process user input with the agent."""
        client = self.clients[client_id]
        websocket = client['websocket']
        thread_id = client['thread_id']
        
        try:
            # Get agent response
            loop = asyncio.get_running_loop()
            agent_response = await loop.run_in_executor(
                None, 
                lambda: self.agent.chat(user_input, thread_id)
            )
            
            # Send agent response to client
            await websocket.send(json.dumps({
                "type": "agent_response",
                "text": agent_response,
                "user_input": user_input
            }))
            
            # Generate and stream TTS
            if self.tts_client and agent_response:
                await self.stream_tts_response(client_id, agent_response, user_input)
                
        except Exception as e:
            print(f"Error processing user input for client {client_id}: {e}")
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Processing error: {str(e)}"
            }))

    async def stream_tts_response(self, client_id, text, original_input):
        """Stream TTS response to client."""
        client = self.clients[client_id]
        websocket = client['websocket']
        
        try:
            # Send TTS start notification
            await websocket.send(json.dumps({
                "type": "tts_start",
                "text": text,
                "original_input": original_input
            }))
            
            # Stream audio chunks
            loop = asyncio.get_running_loop()
            audio_stream = self.tts_client.stream_audio(text)
            
            chunk_count = 0
            async for audio_chunk in self.async_audio_stream(audio_stream):
                if audio_chunk:
                    await websocket.send(audio_chunk)  # Send binary data
                    chunk_count += 1
            
            # Send TTS completion notification
            await websocket.send(json.dumps({
                "type": "tts_complete",
                "chunks_sent": chunk_count,
                "original_input": original_input
            }))
            
            print(f"TTS streaming complete for client {client_id}: {chunk_count} chunks")
            
        except Exception as e:
            print(f"TTS streaming error for client {client_id}: {e}")
            await websocket.send(json.dumps({
                "type": "tts_error",
                "error": str(e),
                "original_input": original_input
            }))

    async def async_audio_stream(self, audio_stream):
        """Async wrapper for audio stream."""
        loop = asyncio.get_running_loop()
        
        def get_next_chunk():
            try:
                return next(audio_stream)
            except StopIteration:
                return None
        
        while True:
            chunk = await loop.run_in_executor(None, get_next_chunk)
            if chunk is None:
                break
            yield chunk

    async def stop_current_stt(self, client_id):
        """Stop current STT processing for a client."""
        client = self.clients[client_id]
        
        if client['stt_task'] and not client['stt_task'].done():
            client['stt_task'].cancel()
            
        if client['audio_stream']:
            await client['audio_stream'].__exit__(None, None, None)
            client['audio_stream'] = None
            
        client['stt_task'] = None

    async def cleanup_client(self, client_id):
        """Clean up client resources."""
        if client_id in self.clients:
            client = self.clients[client_id]
            
            # Stop STT processing
            await self.stop_current_stt(client_id)
            
            # Remove from clients
            del self.clients[client_id]
            print(f"Client {client_id} cleaned up")

    async def start(self):
        """Start the WebSocket server."""
        server = await websockets.serve(
            self.handler,
            self.host,
            self.port,
            ping_interval=20,  # Keep connection alive
            ping_timeout=10,
            close_timeout=10
        )
        print(f"Improved WebSocket server started at ws://{self.host}:{self.port}")
        await server.wait_closed()

# Usage
if __name__ == "__main__":
    server = ImprovedAudioWebSocketServer()
    asyncio.run(server.start())