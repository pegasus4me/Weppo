// WebSocket connection
const ws = new WebSocket('ws://localhost:8000');
console.log('WebSocket instance created');

// Audio context and configuration
let audioContext;
let mediaStream;
let workletNode;
const SAMPLE_RATE = 16000; // Match backend's RATE
const BUFFER_SIZE = 1024;

// UI Elements
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const statusDiv = document.getElementById('status');
const transcriptDiv = document.getElementById('transcript');
const agentResponseDiv = document.getElementById('agentResponse');

// WebSocket event handlers
ws.onopen = () => {
    console.log('WebSocket connection established');
    statusDiv.textContent = 'Status: Connected to server';
    startButton.disabled = false;
};

ws.onclose = () => {
    console.log('WebSocket connection closed');
    statusDiv.textContent = 'Status: Disconnected from server';
    startButton.disabled = true;
    stopButton.disabled = true;
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    statusDiv.textContent = 'Status: Error connecting to server';
};

ws.onmessage = (event) => {
    console.log('Received message from server:', event.data);
    try {
        const response = JSON.parse(event.data);
        console.log('Parsed response:', response);
        
        // Handle transcript updates
        if (response.transcript) {
            transcriptDiv.innerHTML = `<strong>You said:</strong> ${response.transcript}`;
        }
        
        // Handle agent responses
        if (response.agent_response) {
            // Convert markdown-like formatting to HTML for better display
            const formattedResponse = formatAgentResponse(response.agent_response);
            agentResponseDiv.innerHTML = `<strong>Agent:</strong><br>${formattedResponse}`;
        }
        
        // Handle errors
        if (response.error) {
            agentResponseDiv.innerHTML = `<strong style="color: red;">Error:</strong> ${response.error}`;
        }
        
    } catch (e) {
        console.error('Error parsing message:', e);
        agentResponseDiv.innerHTML = `<strong style="color: red;">Error:</strong> Could not parse server response`;
    }
};

// Function to format agent response for better display
function formatAgentResponse(response) {
    // Convert markdown-style headers to HTML
    let formatted = response
        .replace(/### (.*?)(?=\n|$)/g, '<h4>$1</h4>')
        .replace(/## (.*?)(?=\n|$)/g, '<h3>$1</h3>')
        .replace(/# (.*?)(?=\n|$)/g, '<h2>$1</h2>')
        // Convert markdown links to HTML links
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        // Convert bold text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // Convert bullet points
        .replace(/^- (.*$)/gim, '• $1')
        // Convert line breaks to HTML
        .replace(/\n/g, '<br>');
    
    return formatted;
}

// Audio capture functions
async function startRecording() {
    console.log('Starting recording...');
    try {
        // Clear previous responses
        transcriptDiv.textContent = '';
        agentResponseDiv.textContent = '';
        
        // Request microphone access
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('Microphone access granted');
        
        // Create audio context
        audioContext = new AudioContext({
            sampleRate: SAMPLE_RATE
        });
        console.log('Audio context created with sample rate:', SAMPLE_RATE);

        // Load and initialize the audio worklet
        await audioContext.audioWorklet.addModule('audio-processor.js');
        console.log('Audio worklet loaded');
        
        // Create audio source from microphone
        const source = audioContext.createMediaStreamSource(mediaStream);
        console.log('Audio source created from media stream');
        
        // Create worklet node
        workletNode = new AudioWorkletNode(audioContext, 'audio-processor');
        console.log('Audio worklet node created');
        
        // Handle audio data from the worklet
        workletNode.port.onmessage = (event) => {
            if (ws.readyState === WebSocket.OPEN) {
                const audioData = event.data;
                console.log('Received audio data from worklet, length:', audioData.length);
                // Convert Float32Array to Int16Array for sending
                const pcmData = new Int16Array(audioData.length);
                for (let i = 0; i < audioData.length; i++) {
                    pcmData[i] = audioData[i] * 0x7FFF;
                }
                console.log('Sending PCM data to server, length:', pcmData.length);
                ws.send(pcmData.buffer);
            } else {
                console.warn('WebSocket not open, cannot send audio data');
            }
        };
        
        // Connect the nodes
        source.connect(workletNode);
        workletNode.connect(audioContext.destination);
        console.log('Audio nodes connected');
        
        statusDiv.textContent = 'Status: Recording... Speak now!';
        startButton.disabled = true;
        stopButton.disabled = false;
    } catch (error) {
        console.error('Error starting recording:', error);
        statusDiv.textContent = 'Status: Error starting recording';
    }
}

function stopRecording() {
    console.log('Stopping recording...');
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        console.log('Media stream tracks stopped');
    }
    if (workletNode) {
        workletNode.disconnect();
        console.log('Worklet node disconnected');
    }
    if (audioContext) {
        audioContext.close();
        console.log('Audio context closed');
    }
    statusDiv.textContent = 'Status: Connected to server';
    startButton.disabled = false;
    stopButton.disabled = true;
}

// Event listeners
startButton.addEventListener('click', startRecording);
stopButton.addEventListener('click', stopRecording);

// Initialize UI state
startButton.disabled = true;
stopButton.disabled = true;
console.log('UI initialized');