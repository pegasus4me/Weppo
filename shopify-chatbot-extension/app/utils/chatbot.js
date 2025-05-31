// Client-side chatbot logic

let mediaRecorder;
let socket;
let audioChunks = []; // We'll try to stream directly, but this can be a fallback or for short recordings.

// --- WebSocket Connection ---
function connectWebSocket(storeDomain, uiCallbacks) {
  const { setIsConnected, setButtonText, addMessage } = uiCallbacks;
  const wsUrl = `ws://localhost:8000/ws/chat?store_domain=${storeDomain}`;
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log('WebSocket connection established.');
    setIsConnected(true);
    setButtonText('Recording... (Click to Stop)');
    addMessage('System', 'Connected to agent. You can start speaking.');
    // Start sending audio data (this will be triggered by MediaRecorder's ondataavailable)
  };

  socket.onmessage = async (event) => {
    if (event.data instanceof Blob) { // Assuming backend sends audio as Blob, might be ArrayBuffer
      console.log('Received audio data from server.');
      const audioData = await event.data.arrayBuffer(); // Convert Blob to ArrayBuffer
      playAudio(audioData);
    } else if (typeof event.data === 'string') {
      try {
        const message = JSON.parse(event.data);
        if (message.transcript) {
          addMessage('Transcript', message.transcript + (message.is_final ? " (final)" : ""));
        } else if (message.response) {
          addMessage('Agent', message.response);
        } else if (message.error) {
          addMessage('Error', message.error);
        } else {
          addMessage('System', event.data); // Fallback for other text messages
        }
      } catch (e) {
        console.warn('Received non-JSON text message or unknown JSON structure:', event.data);
        // If ElevenLabs is off, the backend might send plain text directly
        addMessage('Agent', event.data);
      }
    }
  };

  socket.onerror = (error) => {
    console.error('WebSocket error:', error);
    addMessage('Error', 'WebSocket connection error. Please try again.');
    setIsConnected(false);
    setButtonText('Call Agent');
    // Potentially call handleStopCall here to clean up MediaRecorder if it was started
  };

  socket.onclose = (event) => {
    console.log('WebSocket connection closed:', event.reason, event.code);
    setIsConnected(false);
    setButtonText('Call Agent');
    addMessage('System', `Connection closed: ${event.reason || "Normal closure"}`);
    // Ensure MediaRecorder is stopped if it was running
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
    }
  };
  return socket;
}


// --- Audio Recording and Streaming ---
export async function handleCallAgent(storeDomain, uiCallbacks) {
  const { setIsRecording, setButtonText, setButtonDisabled, addMessage } = uiCallbacks;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addMessage('Error', 'getUserMedia not supported on your browser!');
    return;
  }

  setButtonText('Connecting...');
  setButtonDisabled(true);

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000 } }); // Request 16kHz audio

    // Establish WebSocket connection first
    socket = connectWebSocket(storeDomain, {
        ...uiCallbacks,
        setIsConnected: (isConnected) => {
            uiCallbacks.setIsConnected(isConnected);
            if (isConnected) {
                // Start MediaRecorder only after WebSocket is open
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' }); // Or 'audio/wav' if backend prefers

                mediaRecorder.ondataavailable = (event) => {
                  if (event.data.size > 0 && socket && socket.readyState === WebSocket.OPEN) {
                    // audioChunks.push(event.data); // Not strictly needed if streaming directly
                    console.log("Sending audio data chunk");
                    socket.send(event.data); // Send Blob directly, backend will handle it
                  }
                };

                mediaRecorder.onstart = () => {
                  console.log('MediaRecorder started');
                  setIsRecording(true);
                  setButtonText('Recording... (Click to Stop)');
                  setButtonDisabled(false);
                  audioChunks = []; // Clear any previous chunks
                };

                mediaRecorder.onstop = ()_ => {
                  console.log('MediaRecorder stopped');
                  setIsRecording(false);
                  setButtonText('Call Agent');
                  setButtonDisabled(false);
                  // If socket is still open, could send a final message or close, handled by onclose mostly
                };

                mediaRecorder.onerror = (event) => {
                  console.error('MediaRecorder error:', event.error);
                  addMessage('Error', `MediaRecorder error: ${event.error.name}`);
                  handleStopCall(uiCallbacks); // Stop everything on recorder error
                };

                mediaRecorder.start(250); // Start recording, collect data every 250ms
            } else {
                // WebSocket connection failed
                addMessage('Error', 'Failed to connect to agent. Please try again.');
                setButtonText('Call Agent');
                setButtonDisabled(false);
                stream.getTracks().forEach(track => track.stop()); // Release microphone
            }
        }
    });


  } catch (err) {
    console.error('Error getting media stream or starting recording:', err);
    addMessage('Error', `Could not access microphone: ${err.message}. Please ensure permission is granted.`);
    setButtonText('Call Agent');
    setButtonDisabled(false);
    setIsRecording(false);
  }
}

export function handleStopCall(uiCallbacks) {
  const { setIsRecording, setButtonText, setButtonDisabled, setIsConnected, addMessage } = uiCallbacks;

  addMessage('System', 'Call ended.');

  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }
  // Stop microphone tracks
  if (mediaRecorder && mediaRecorder.stream) {
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
  }

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close();
  }

  setIsRecording(false);
  setIsConnected(false); // Ensure connection state is updated
  setButtonText('Call Agent');
  setButtonDisabled(false);
  audioChunks = []; // Clear any stored chunks
}

// This is the one used by chatbot.jsx for rendering messages
export function addMessageToDisplay(sender, messageText, messages, setMessages) {
  console.log(`addMessageToDisplay called: sender=${sender}, message=${messageText}`);
  setMessages(prevMessages => [...prevMessages, { sender, text: messageText, id: Date.now() }]);
}

// This is the original displayMessage, kept for direct DOM manipulation if needed elsewhere,
// but addMessageToDisplay is preferred for React components.
export function displayMessage(sender, message) {
  console.log(`displayMessage (direct DOM) called: sender=${sender}, message=${message}`);
  const chatDisplay = document.getElementById('chatDisplay'); // This will only work if chatDisplay is a static element outside React's render cycle or managed carefully.
  if (chatDisplay) {
    const messageElement = document.createElement('p');
    messageElement.innerHTML = `<strong>${sender}:</strong> ${message}`;
    chatDisplay.appendChild(messageElement);
    chatDisplay.scrollTop = chatDisplay.scrollHeight; // Scroll to the bottom
  } else {
    console.error('Chat display element not found');
  }
}

let audioContext;
const audioQueue = [];
let isPlaying = false;

function getAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioContext;
}

async function playNextInQueue() {
  if (audioQueue.length === 0 || isPlaying) {
    return;
  }
  isPlaying = true;
  const audioData = audioQueue.shift();
  const currentAudioContext = getAudioContext();

  try {
    const audioBuffer = await currentAudioContext.decodeAudioData(audioData);
    const source = currentAudioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(currentAudioContext.destination);
    source.onended = () => {
      isPlaying = false;
      playNextInQueue(); // Play next audio in queue
    };
    source.start(0);
  } catch (error) {
    console.error('Error decoding or playing audio:', error);
    // Potentially use uiCallbacks.addMessage to display this error
    // displayMessage('Error', 'Could not play audio response.'); // This might not be available if not passed
    isPlaying = false;
    playNextInQueue(); // Try next one even if current fails
  }
}

export function playAudio(audioData) { // audioData is expected to be an ArrayBuffer
  if (!(audioData instanceof ArrayBuffer)) {
    console.error("playAudio expects an ArrayBuffer, received:", typeof audioData);
    return;
  }
  console.log('Audio data received for playback:', audioData.byteLength + " bytes");
  audioQueue.push(audioData);
  if (!isPlaying) {
    playNextInQueue();
  }
  // Intentionally not calling displayMessage here to avoid cluttering chat with "playing audio" messages
  // unless it's a specific UI requirement. The audio itself is the notification.
}

// Example function to simulate receiving a message from the agent
export function receiveAgentMessage(message) {
  displayMessage('Agent', message);
}

// Example function to simulate receiving audio from the agent
export function receiveAgentAudio(audioBytes) {
  playAudio(audioBytes); // audioBytes would be ArrayBuffer or similar
}
