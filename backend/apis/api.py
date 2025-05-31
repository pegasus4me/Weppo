import logging
import os
import httpx # Added for making HTTP requests to admin dashboard
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from backend.agents.input.speech_input import speech_to_text
from backend.agents.input.websocket_server import WebSocketStream
from backend.agents.orchestrator.agent import PersonalShopperAgent
from elevenlabs import generate, play, set_api_key, stream # stream might not be used directly here anymore
from elevenlabs.client import ElevenLabs


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure ElevenLabs API key is set
eleven_labs_api_key = os.getenv("ELEVENLABS_API_KEY")
if not eleven_labs_api_key:
    logger.warning("ELEVENLABS_API_KEY not set. Text-to-speech will not work.")
else:
    # set_api_key(eleven_labs_api_key) # elevenlabs client is instantiated directly now
    pass

app = FastAPI(
    title="Personal Shopper Agent API",
    description="API for interacting with the Personal Shopper Agent, including text and voice chat.",
    version="0.1.0",
    openapi_tags=[
        {"name": "Agent Interaction", "description": "Endpoints for communicating with the shopping agent."},
        {"name": "Utilities", "description": "Helper functions (internal)."}
    ]
)

# Helper function to create a ticket
async def _create_ticket_in_admin_dashboard(user_query: str, agent_response_text: str, original_input_text: str):
    """
    (Internal) Submits a support ticket to the admin dashboard API.
    This is triggered when the agent determines human assistance is needed.
    """
    ticket_payload = {
        "user_query": user_query, # This is the query that the agent decided needs a ticket
        "conversation_history": [
            f"User: {original_input_text}", # The initial text from user
            f"Agent: {agent_response_text}"  # The agent's textual response
        ]
        # timestamp and status will be set by the admin dashboard
    }
    try:
        async with httpx.AsyncClient() as client:
            # Ensure this URL matches where your admin dashboard is running
            response = await client.post("http://localhost:8001/api/tickets", json=ticket_payload)
            if response.status_code == 200 or response.status_code == 201:
                logger.info(f"Support ticket created successfully: {response.json()}")
            else:
                logger.error(f"Failed to create support ticket: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Error creating support ticket: {e}")


class ChatRequest(BaseModel):
    text: str
    store_domain: str
    thread_id: str | None = None

    class Config:
        schema_extra = {
            "example": {
                "text": "Hi, I'm looking for running shoes.",
                "store_domain": "allbirds.com",
                "thread_id": "user123-session456"
            }
        }

class ChatResponse(BaseModel):
    response: str

    class Config:
        schema_extra = {
            "example": {
                "response": "Hello! We have some great running shoes. What kind are you looking for?"
            }
        }

class ErrorResponse(BaseModel):
    error: str

@app.post("/api/agent/chat",
          response_model=ChatResponse,
          responses={500: {"model": ErrorResponse}},
          tags=["Agent Interaction"],
          summary="Chat with the agent via HTTP POST")
async def agent_chat(request: ChatRequest):
    """
    Send a text query to the Personal Shopper Agent and receive a text response.
    If the agent determines a support ticket is needed, it will be created in the background.
    """
    logger.info(f"Received chat request: {request}")
    try:
        agent = PersonalShopperAgent(store_domain=request.store_domain)
        agent_response_data = await agent.chat(request.text, request.thread_id)

        text_for_user = agent_response_data.get("text_response", "Sorry, I encountered an issue processing your request.")
        logger.info(f"Agent text response for user: {text_for_user}")

        if agent_response_data.get("action") == "create_ticket":
            user_query_for_ticket = agent_response_data.get("ticket_data", {}).get("user_query", request.text)
            logger.info(f"Ticket creation initiated for query: {user_query_for_ticket}")
            # Run ticket creation in background if it's slow, or await if it's quick enough
            await _create_ticket_in_admin_dashboard(
                user_query=user_query_for_ticket,
                agent_response_text=text_for_user,
                original_input_text=request.text
            )

        return {"response": text_for_user}
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        return ErrorResponse(error=str(e)), 500

@app.websocket("/ws/chat", name="WebSocket Chat with Agent")
async def websocket_chat(
    websocket: WebSocket,
    store_domain: str = "allbirds.com",
    thread_id: str | None = None # Optional thread_id for WebSocket
    ):
    """
    Communicate with the Personal Shopper Agent over WebSocket for real-time voice/text interaction.

    - **Query Parameter `store_domain`**: The Shopify domain for the store (e.g., "allbirds.com").
    - **Query Parameter `thread_id`**: Optional session/thread ID for maintaining conversation context.

    **Messages sent by client:**
    - Audio data (bytes) for voice input.

    **Messages received by client:**
    - Text messages (transcripts, agent text responses if TTS is off, or errors).
    - Bytes messages (synthesized audio response from the agent).

    If the agent determines a support ticket is needed, it will be created in the background.
    """
    await websocket.accept()
    logger.info(f"WebSocket connection accepted from {websocket.client} for store {store_domain}, thread_id: {thread_id}")

    try:
        # Initialize agent
        agent = PersonalShopperAgent(store_domain=store_domain)
        # Initialize audio stream
        audio_stream = WebSocketStream(websocket)

        while True:
            # Receive audio data
            audio_data = await audio_stream.receive_audio()
            if not audio_data:
                logger.info("No audio data received, closing connection.")
                break

            logger.info("Received audio data, transcribing...")

            # Transcribe audio to text
            try:
                transcribed_text = await speech_to_text(audio_data)
                logger.info(f"Transcribed text: {transcribed_text}")
            except Exception as e:
                logger.error(f"Error during transcription: {e}")
                await websocket.send_text(f"Error during transcription: {e}")
                continue

            # Get response from agent
            try:
                # Pass thread_id to agent.chat if provided via WebSocket query param
                current_thread_id = thread_id if thread_id else f"ws-{websocket.client.host}-{websocket.client.port}"
                agent_response_data = await agent.chat(transcribed_text, thread_id=current_thread_id) # This now returns a dict
                text_for_user = agent_response_data.get("text_response", "Sorry, I had trouble understanding that.")
                logger.info(f"Agent text response for user: {text_for_user}")

                if agent_response_data.get("action") == "create_ticket":
                    user_query_for_ticket = agent_response_data.get("ticket_data", {}).get("user_query", transcribed_text)
                    logger.info(f"Ticket creation initiated for query: {user_query_for_ticket}")
                    await _create_ticket_in_admin_dashboard(
                        user_query=user_query_for_ticket,
                        agent_response_text=text_for_user,
                        original_input_text=transcribed_text
                    )

            except Exception as e:
                logger.error(f"Error during agent chat: {e}")
                await websocket.send_text(f"Error during agent chat: {e}") # Send text error to client
                continue # Allow for next message

            # Convert agent's textual response to speech and stream back
            if eleven_labs_api_key:
                try:
                    logger.info(f"Generating audio response for: {text_for_user}")
                    # Initialize client here if not globally or if settings per request are needed
                    eleven_client = ElevenLabs(api_key=eleven_labs_api_key)
                    audio_stream_generator = eleven_client.generate(
                        text=text_for_user,
                        stream=True
                    )
                    # Stream audio data
                    for chunk in audio_stream_generator:
                        if chunk:
                            await websocket.send_bytes(chunk)
                    logger.info("Audio response sent.")
                except Exception as e:
                    logger.error(f"Error during ElevenLabs audio generation: {e}")
                    # Fallback: send text if TTS fails
                    await websocket.send_text(f"Error generating audio response. Agent said: {text_for_user}")
            else:
                logger.warning("ElevenLabs API key not set. Sending text response instead.")
                await websocket.send_text(text_for_user)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {websocket.client}")
    except ConnectionRefusedError:
        logger.error("Connection refused by client or an intermediate system for WebSocket.")
        # No websocket to send message to if connection was refused initially.
        # Ensure websocket.close() is called if it was ever accepted.
    except Exception as e:
        logger.error(f"Error in WebSocket chat: {e}")
        try:
            await websocket.send_text(f"An unexpected error occurred: {e}")
        except Exception as send_error: # Handle cases where sending error itself fails
            logger.error(f"Failed to send error to WebSocket: {send_error}")
    finally:
        # Ensure that the websocket state is imported before it's used
        from fastapi.websockets import WebSocketState
        if websocket.client_state != WebSocketState.DISCONNECTED:
             await websocket.close()
        logger.info(f"WebSocket connection closed for {websocket.client}")


@app.post("/api/agent/send")