import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

# Import the FastAPI app and the helper function from your API file
# Adjust the import path according to your project structure
from backend.apis.api import _create_ticket_in_admin_dashboard, app as fastapi_app
from backend.agents.orchestrator.agent import PersonalShopperAgent

# Fixture for TestClient
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    return TestClient(fastapi_app)

@pytest.mark.asyncio
async def test_create_ticket_in_admin_dashboard_success():
    """Test successful ticket creation call to admin dashboard."""
    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_post = AsyncMock()
        mock_post.status_code = 201 # Simulate successful creation
        mock_post.json.return_value = {"id": "ticket123", "status": "open"}

        # Configure the context manager 'aenter' and 'aexit' for AsyncClient
        mock_async_client_instance = MockAsyncClient.return_value
        mock_async_client_instance.__aenter__.return_value.post = mock_post

        await _create_ticket_in_admin_dashboard(
            user_query="Need help with order",
            agent_response_text="I'll create a ticket.",
            original_input_text="Help me!"
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:8001/api/tickets"
        assert kwargs["json"]["user_query"] == "Need help with order"
        assert "User: Help me!" in kwargs["json"]["conversation_history"]
        assert "Agent: I'll create a ticket." in kwargs["json"]["conversation_history"]

@pytest.mark.asyncio
async def test_create_ticket_in_admin_dashboard_failure():
    """Test failed ticket creation call to admin dashboard."""
    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_post = AsyncMock()
        mock_post.status_code = 500 # Simulate server error
        mock_post.text = "Internal Server Error"

        mock_async_client_instance = MockAsyncClient.return_value
        mock_async_client_instance.__aenter__.return_value.post = mock_post

        # (Optional: Check for logging of the error, would require capturing logs)
        await _create_ticket_in_admin_dashboard(
            user_query="Another query",
            agent_response_text="Ticket time.",
            original_input_text="Problem!"
        )
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_create_ticket_in_admin_dashboard_exception():
    """Test exception during ticket creation call."""
    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        mock_async_client_instance = MockAsyncClient.return_value
        mock_async_client_instance.__aenter__.return_value.post = mock_post

        # (Optional: Check for logging of the exception)
        await _create_ticket_in_admin_dashboard(
            user_query="Exception test",
            agent_response_text="Oh no.",
            original_input_text="Error incoming!"
        )
        mock_post.assert_called_once()

# Tests for the /api/agent/chat endpoint
@patch('backend.apis.api.PersonalShopperAgent') # Patch the agent class where it's used
@patch('backend.apis.api.httpx.AsyncClient')    # Patch AsyncClient where it's used
def test_chat_creates_ticket_when_signaled(MockAsyncClient, MockAgent, client):
    """Test POST /api/agent/chat creates a ticket when agent signals."""
    # Mock PersonalShopperAgent instance and its chat method
    mock_agent_instance = MockAgent.return_value
    mock_agent_instance.chat = AsyncMock(return_value={
        "text_response": "I've created a ticket for you.",
        "action": "create_ticket",
        "ticket_data": {"user_query": "My order #123 is missing."}
    })

    # Mock httpx.AsyncClient for ticket creation
    mock_ticket_post = AsyncMock()
    mock_ticket_post.status_code = 201
    mock_ticket_post.json.return_value = {"id": "ticket-xyz", "status": "open"}

    mock_async_client_instance = MockAsyncClient.return_value
    mock_async_client_instance.__aenter__.return_value.post = mock_ticket_post

    # Make the request to the endpoint
    chat_payload = {"text": "My order #123 is missing.", "store_domain": "test.com"}
    response = client.post("/api/agent/chat", json=chat_payload)

    assert response.status_code == 200
    assert response.json()["response"] == "I've created a ticket for you."

    # Verify agent was called
    mock_agent_instance.chat.assert_called_once_with(chat_payload["text"], None) # Assuming default thread_id is None

    # Verify ticket creation was attempted
    mock_ticket_post.assert_called_once()
    args, kwargs = mock_ticket_post.call_args
    assert args[0] == "http://localhost:8001/api/tickets"
    assert kwargs["json"]["user_query"] == "My order #123 is missing."
    assert f"User: {chat_payload['text']}" in kwargs["json"]["conversation_history"]
    assert f"Agent: I've created a ticket for you." in kwargs["json"]["conversation_history"]


@patch('backend.apis.api.PersonalShopperAgent')
@patch('backend.apis.api.httpx.AsyncClient')
def test_chat_does_not_create_ticket_when_not_signaled(MockAsyncClient, MockAgent, client):
    """Test POST /api/agent/chat does NOT create a ticket for normal responses."""
    # Mock PersonalShopperAgent
    mock_agent_instance = MockAgent.return_value
    mock_agent_instance.chat = AsyncMock(return_value={
        "text_response": "Here is some information about product X.",
        "action": None
        # No ticket_data needed if action is None
    })

    # Mock httpx.AsyncClient (post method for ticket creation)
    mock_ticket_post = mock_async_client_instance = MockAsyncClient.return_value.__aenter__.return_value.post = AsyncMock()


    # Make the request
    chat_payload = {"text": "Tell me about product X.", "store_domain": "test.com"}
    response = client.post("/api/agent/chat", json=chat_payload)

    assert response.status_code == 200
    assert response.json()["response"] == "Here is some information about product X."

    mock_agent_instance.chat.assert_called_once_with(chat_payload["text"], None)

    # Verify ticket creation was NOT attempted
    mock_ticket_post.assert_not_called()

# Note on WebSocket testing:
# Testing WebSockets with TestClient can be more involved.
# For `pytest-fastapi-deps`, you might use `WebSocketTestSession`.
# However, since the ticket creation logic is factored out into
# `_create_ticket_in_admin_dashboard`, testing that helper function (as done above)
# covers the core logic for ticket creation, which is also used by the WebSocket endpoint.
# A full WebSocket endpoint test would involve simulating WebSocket connect, send, receive,
# which is possible but adds more complexity than might be needed if the core logic
# is already tested via the helper and the HTTP endpoint.
# If specific WebSocket interactions leading to ticket creation need testing,
# those would be additional tests.
#
# Example of how you might start a WebSocket test (if dependencies are set up):
# def test_websocket_creates_ticket(client):
#     with patch('backend.apis.api.PersonalShopperAgent') as MockAgent, \
#          patch('backend.apis.api.speech_to_text', new_callable=AsyncMock) as mock_stt, \
#          patch('backend.apis.api.httpx.AsyncClient') as MockTicketClient:
#
#         # Setup mocks for agent, stt, ticket client (similar to HTTP test)
#         mock_agent_instance = MockAgent.return_value
#         mock_agent_instance.chat = AsyncMock(return_value={
#             "text_response": "WS Ticket created.", "action": "create_ticket",
#             "ticket_data": {"user_query": "WS query"}
#         })
#         mock_stt.return_value = "WS query"
#
#         mock_ticket_post = AsyncMock(status_code=201, json={"id": "ws-ticket"})
#         MockTicketClient.return_value.__aenter__.return_value.post = mock_ticket_post
#
#         with client.websocket_connect("/ws/chat?store_domain=test.com") as websocket:
#             websocket.send_bytes(b"fake audio data")
#             # Need to handle how the server sends messages back.
#             # If it sends text first (e.g. transcript), then audio, or just audio.
#             # For this test, we care about the ticket creation.
#             # This part is tricky because the audio generation and sending is async
#             # and might happen after ticket creation.
#             # Await some condition or add a delay, or check mocks after closing.
#
#             # This is a simplified check, real scenario needs to handle multiple possible messages.
#             # For example, if TTS is on, it will send bytes. If off, text.
#             # We might just check that our mock_ticket_post was called.
#             # Forcing the test to wait a bit for async operations to complete if needed.
#             import asyncio
#             async def wait_for_mocks():
#                 await asyncio.sleep(0.1) # Small delay
#
#             # This is not ideal, but shows the challenge of testing async internal calls in websockets
#             # Better to test the helper function directly.
#
#             # After some interaction that should trigger ticket:
#             # (Need a way to know when the server-side processing is done)
#             # For now, assume the helper test is sufficient for the ticket logic itself.
#
#         # Assert mock_ticket_post was called (this might require more sophisticated handling of async websocket flow)
#         # mock_ticket_post.assert_called_once()
#         pass # Placeholder for more complex WebSocket test structure

# To run tests from project root:
# Ensure backend/tests is a Python package (add __init__.py if needed)
# Ensure backend is a Python package (add __init__.py if needed)
# PYTHONPATH=. pytest backend/tests/test_api_ticket_creation.py
# or
# python -m pytest backend/tests/test_api_ticket_creation.py
