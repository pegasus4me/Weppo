import { useState, useEffect, useCallback } from 'react';
import { handleCallAgent, handleStopCall, addMessageToDisplay, displayMessage as directDisplayMessage } from '../utils/chatbot';

// Configuration
const STORE_DOMAIN = "allbirds.com"; // Or dynamically get this

export default function ChatbotPage() {
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false); // WebSocket connection status
  const [buttonText, setButtonText] = useState('Call Agent');
  const [isButtonDisabled, setIsButtonDisabled] = useState(false);
  const [messages, setMessages] = useState([]); // Store chat messages {sender, text, id}

  // Callback to add a message to the chat display
  const addMessage = useCallback((sender, text) => {
    addMessageToDisplay(sender, text, messages, setMessages);
  }, [messages]); // Include messages in dependency array if addMessageToDisplay uses it directly

  // Define uiCallbacks to pass to utility functions
  const uiCallbacks = {
    setIsRecording,
    setIsConnected,
    setButtonText,
    setIsButtonDisabled,
    addMessage, // Use the memoized version
  };

  // Effect to clean up resources on component unmount
  useEffect(() => {
    return () => {
      if (isRecording || isConnected) { // If recording or connected, try to clean up
        handleStopCall(uiCallbacks);
      }
    };
  }, [isRecording, isConnected, uiCallbacks]); // Add dependencies

  const toggleCall = () => {
    if (isRecording || (isConnected && mediaRecorder && mediaRecorder.state === "recording")) { // check isConnected as well for safety
      handleStopCall(uiCallbacks);
    } else {
      // Clear previous messages if desired, or keep history
      // setMessages([{ sender: 'System', text: 'Starting new call...', id: Date.now() }]);
      handleCallAgent(STORE_DOMAIN, uiCallbacks);
    }
  };

  // Scroll to bottom of chat display when messages change
  useEffect(() => {
    const chatDisplay = document.getElementById('chatDisplay');
    if (chatDisplay) {
      chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }
  }, [messages]);

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', maxWidth: '600px', margin: 'auto', padding: '20px' }}>
      <h1 style={{ textAlign: 'center', color: '#333' }}>Shopify Voice Agent</h1>

      <div
        id="chatDisplay"
        style={{
          border: '1px solid #ccc',
          height: '400px',
          overflowY: 'scroll',
          padding: '15px',
          marginBottom: '20px',
          backgroundColor: '#f9f9f9',
          borderRadius: '5px'
        }}
      >
        {messages.map((msg) => (
          <p key={msg.id} style={{ margin: '5px 0' }}>
            <strong style={{ color: msg.sender === 'Agent' ? '#007bff' : '#28a745' }}>
              {msg.sender}:
            </strong> {msg.text}
          </p>
        ))}
      </div>

      <button
        id="callAgentButton"
        onClick={toggleCall}
        disabled={isButtonDisabled}
        style={{
          backgroundColor: (isRecording || (isConnected && !isButtonDisabled)) ? '#dc3545' : '#007bff', // Red when recording, blue otherwise
          color: 'white',
          padding: '10px 20px',
          border: 'none',
          borderRadius: '5px',
          cursor: isButtonDisabled ? 'not-allowed' : 'pointer',
          fontSize: '16px',
          width: '100%'
        }}
      >
        {buttonText}
      </button>

      {/* For testing direct displayMessage (not part of main flow) */}
      {/* <button onClick={() => directDisplayMessage('Test', 'Direct DOM message test')}>Test Direct Display</button> */}
    </div>
  );
}
