# Integration Test Outline: Client-Server Audio Streaming and Response

This document outlines basic integration tests for the main backend's WebSocket audio streaming functionality. These tests aim to verify the end-to-end flow from a client sending audio to receiving a response (transcript and/or synthesized audio).

**Pre-requisites:**
*   The main backend server (`backend/apis/api.py`) must be running.
*   Configuration for STT (e.g., Google Cloud Speech) should be in place.
*   Configuration for TTS (e.g., ElevenLabs API key) should be in place if testing audio responses. If not, expect text responses.
*   A sample audio file (e.g., a short WAV file containing a simple voice query like "Hello") for the client to send.

**Test Environment:**
*   A Python testing environment with libraries like `websockets` (for the client) and `pytest` (for test structure, optional for this outline).

**Test Case 1: Successful Audio Query and Response (Text/Audio)**

1.  **Objective:** Verify that the system can receive streamed audio, transcribe it, get an agent response, and send back a meaningful reply (text transcript and either synthesized audio or agent's text response).
2.  **Steps:**
    *   **Start Server:** Ensure the main backend FastAPI server is running.
    *   **Client Connect:**
        *   Use a WebSocket client (e.g., Python `websockets` library) to connect to the `/ws/chat?store_domain=test.com&thread_id=integration_test_1` endpoint.
        *   Verify successful connection (HTTP 101 Switching Protocols).
    *   **Send Audio:**
        *   Read the sample audio WAV file.
        *   Stream its content in reasonably sized chunks (e.g., 1024 or 4096 bytes per message) over the WebSocket connection to the server.
        *   Send a final "end-of-stream" message if your client/server protocol requires it (not explicitly in current backend, but good practice for some streaming STT). The current backend `WebSocketStream` accumulates bytes until a pause or a certain amount of data is received.
    *   **Receive Messages:**
        *   Listen for messages from the server.
        *   **Expected Message 1 (Optional but common - Transcript):**
            *   Type: Text (JSON string).
            *   Content: A JSON object containing the transcript, e.g., `{"transcript": "Hello", "is_final": true}`. Assert the transcript matches the content of the sample audio.
        *   **Expected Message 2 (Agent Response):**
            *   If ElevenLabs (TTS) is active and working:
                *   Type: Bytes.
                *   Content: Audio data representing the agent's spoken response. (Verifying the *content* of this audio is complex in automated tests; for now, confirming receipt of non-empty byte stream is a start. Advanced tests might use STT on this received audio to check its content).
            *   If ElevenLabs (TTS) is inactive or fails:
                *   Type: Text.
                *   Content: The agent's textual response (string). Assert this is a plausible agent response.
    *   **Client Disconnect:** Close the WebSocket connection from the client side.
    *   **Server Log Check (Optional):** Check server logs for any errors during the interaction.
3.  **Success Criteria:**
    *   Client connects successfully.
    *   Server receives audio data without error.
    *   Client receives a plausible transcript (if sent separately).
    *   Client receives either an audio stream (bytes) or a text message representing the agent's response.
    *   No errors logged on the server related to this interaction.

**Test Case 2: Handling Connection Errors or Invalid Audio**

1.  **Objective:** Verify graceful error handling. (This is broad; specific sub-cases would be needed).
2.  **Examples:**
    *   **Client sends non-audio data:** Server should ideally not crash and might send an error message back.
    *   **Client disconnects abruptly:** Server should handle the `WebSocketDisconnect` gracefully.
    *   **STT/TTS service errors:** If dependent services (STT, TTS, Agent LLM) fail, the server should ideally send an appropriate error message to the client.

**Notes on Automation:**
*   Fully automating these tests requires careful synchronization, especially when dealing with streamed data and asynchronous responses.
*   Mocking external services (STT, TTS, LLM for the agent itself) can make these tests more reliable and focused on the API/WebSocket plumbing, but then they become less "integration" tests. For true integration, live services (even sandboxed ones) would be used.
*   The complexity of verifying received audio content often means that for automated CI, one might only check for the *presence* of an audio stream, and rely on manual QA or more sophisticated audio analysis tools for content verification.

This outline provides a basis for developing more detailed integration test scripts.
