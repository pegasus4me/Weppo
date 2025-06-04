// WebSocket connection
const ws = new WebSocket('ws://localhost:8000');
console.log('WebSocket instance created');

// Audio context and configuration for recording
let audioContext; // For recording
let mediaStream;
let workletNode;
const SAMPLE_RATE = 16000; // Match backend's RATE for recording
const BUFFER_SIZE = 1024; // Example buffer size for worklet

// TTS Audio Playback Globals
let ttsAudioContext; // Separate AudioContext for TTS playback
let audioBufferQueue = [];
let isStreamingAudio = false;

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
    ws.binaryType = "arraybuffer"; // Important for receiving binary audio data
    console.log('WebSocket binaryType set to arraybuffer');
};

ws.onclose = () => {
    console.log('WebSocket connection closed');
    statusDiv.textContent = 'Status: Disconnected from server';
    startButton.disabled = true;
    stopButton.disabled = true;
    isStreamingAudio = false; // Reset streaming flag
    audioBufferQueue = []; // Clear queue
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    statusDiv.textContent = 'Status: Error connecting to server';
};

ws.onmessage = (event) => {
    if (typeof event.data === 'string') {
        console.log('Received JSON message from server:', event.data);
        try {
            const response = JSON.parse(event.data);
            console.log('Parsed JSON response:', response);

            if (response.type === 'transcript') {
                transcriptDiv.innerHTML = `<strong>You said:</strong> "${response.text}"`;
            }

            if (response.type === 'agent_response') {
                const formattedResponse = formatAgentResponse(response.text);
                agentResponseDiv.innerHTML = `<strong>Assistant:</strong><br><br>${formattedResponse}`;
            }

            if (response.type === 'tts_start') {
                console.log("TTS audio streaming started for input:", response.original_input);
                isStreamingAudio = true;
                audioBufferQueue = [];
                if (!ttsAudioContext || ttsAudioContext.state === 'closed') {
                    ttsAudioContext = new (window.AudioContext || window.webkitAudioContext)();
                }
                voiceOrb.classList.remove('user-speaking');
                voiceOrb.classList.add('agent-speaking');
            }

            if (response.type === 'tts_complete') {
                console.log("TTS audio streaming finished. Chunks sent:", response.chunks_sent);
                isStreamingAudio = false;
                voiceOrb.classList.remove('agent-speaking');
                if (audioBufferQueue.length > 0) {
                    playBufferedAudio();
                }
            }

            if (response.type === 'tts_error') {
                console.error("TTS Error from server:", response.error);
                agentResponseDiv.innerHTML += `<br><strong style="color: #dc3545;">TTS Error:</strong> ${response.error}`;
                isStreamingAudio = false;
                audioBufferQueue = [];
                voiceOrb.classList.remove('agent-speaking');
            }

            if (response.type === 'error') {
                agentResponseDiv.innerHTML = `<strong style="color: #dc3545;">Error:</strong> ${response.message}`;
            }

        } catch (e) {
            console.error('Error parsing JSON message:', e, event.data);
            agentResponseDiv.innerHTML = `<strong style="color: #dc3545;">Error:</strong> Could not parse server response.`;
        }
    } else if (event.data instanceof ArrayBuffer) {
        if (isStreamingAudio) {
            audioBufferQueue.push(event.data);
        }
    } else {
        console.warn("Received unexpected message type from server:", event.data);
    }
};

// Function to play buffered TTS audio
async function playBufferedAudio() {
    if (!ttsAudioContext || ttsAudioContext.state === 'closed') {
        console.error('TTS AudioContext not available or closed.');
        audioBufferQueue = []; // Clear queue as playback is not possible
        return;
    }
    if (audioBufferQueue.length === 0) {
        console.log('Audio buffer queue is empty, nothing to play.');
        return;
    }

    console.log('Playing buffered audio. Chunks to process:', audioBufferQueue.length);

    // Concatenate all ArrayBuffers in the queue into a single ArrayBuffer
    let totalLength = 0;
    audioBufferQueue.forEach(buffer => {
        totalLength += buffer.byteLength;
    });

    const concatenatedBuffer = new Uint8Array(totalLength);
    let offset = 0;
    audioBufferQueue.forEach(buffer => {
        concatenatedBuffer.set(new Uint8Array(buffer), offset);
        offset += buffer.byteLength;
    });

    console.log('Audio chunks concatenated. Total size:', concatenatedBuffer.byteLength);
    audioBufferQueue = []; // Clear queue now that data is concatenated

    try {
        const audioBuffer = await ttsAudioContext.decodeAudioData(concatenatedBuffer.buffer);
        console.log('Audio data decoded successfully.');

        const sourceNode = ttsAudioContext.createBufferSource();
        sourceNode.buffer = audioBuffer;
        sourceNode.connect(ttsAudioContext.destination);
        sourceNode.onended = () => {
            console.log('TTS audio playback finished.');
            // Optionally close ttsAudioContext if no more TTS is expected soon,
            // or keep it alive for subsequent playbacks.
            // For now, keep it alive.
        };
        sourceNode.start(0);
        console.log('TTS audio playback started.');

    } catch (error) {
        console.error('Error decoding or playing TTS audio:', error);
        agentResponseDiv.innerHTML += `<br><strong style="color: orange;">Playback Error:</strong> Could not decode/play audio.`;
    }
}


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
        .replace(/^- (.*$)/gim, '• $1') // Use 'm' flag for multiline
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

        // Create audio context for recording
        if (!audioContext || audioContext.state === 'closed') {
            audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
            console.log('Recording Audio context created with sample rate:', SAMPLE_RATE);
        } else if (audioContext.sampleRate !== SAMPLE_RATE) {
            await audioContext.close(); // Close if existing context has wrong sample rate
            audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
            console.log('Recording Audio context re-created with sample rate:', SAMPLE_RATE);
        }


        // Load and initialize the audio worklet
        // Ensure the path to 'audio-processor.js' is correct relative to your HTML file
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
                const audioData = event.data; // Float32Array
                // console.log('Received audio data from worklet, length:', audioData.length);
                // Convert Float32Array to Int16Array for sending
                const pcmData = new Int16Array(audioData.length);
                for (let i = 0; i < audioData.length; i++) {
                    pcmData[i] = audioData[i] * 0x7FFF; // Max Int16 value
                }
                // console.log('Sending PCM data to server, length:', pcmData.length);
                ws.send(pcmData.buffer);
            } else {
                // console.warn('WebSocket not open, cannot send audio data');
            }
        };

        // Connect the nodes
        source.connect(workletNode);
        // Do not connect workletNode to audioContext.destination for recording,
        // unless you want to hear the raw microphone input.
        // workletNode.connect(audioContext.destination);
        console.log('Audio nodes (source -> worklet) connected for recording.');

        statusDiv.textContent = 'Status: Recording... Speak now!';
        startButton.disabled = true;
        stopButton.disabled = false;
    } catch (error) {
        console.error('Error starting recording:', error);
        statusDiv.textContent = 'Status: Error starting recording - ' + error.message;
    }
}

function stopRecording() {
    console.log('Stopping recording...');
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        console.log('Media stream tracks stopped');
    }
    if (workletNode) {
        workletNode.port.onmessage = null; // Remove listener
        workletNode.disconnect();
        console.log('Worklet node disconnected');
        workletNode = null;
    }
    if (audioContext && audioContext.state !== 'closed') {
        // Close the recording audio context as it might not be needed until next recording
        audioContext.close().then(() => console.log('Recording AudioContext closed.'));
    }
    statusDiv.textContent = 'Status: Connected to server';
    startButton.disabled = false;
    stopButton.disabled = true;
}

// Event listeners
startButton.addEventListener('click', startRecording);
stopButton.addEventListener('click', stopRecording);

// Initialize UI state
startButton.disabled = true; // Disabled until WebSocket connection is open
stopButton.disabled = true;
console.log('UI initialized');

// --- audio-processor.js (Worklet code, ensure this file exists in the same directory or correct path) ---
// This would typically be in a separate file `audio-processor.js`
// For the sake of this task, I'm assuming its existence as per the original script.
// If audio-processor.js needs to be created, it would look something like this:
/*
class AudioProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options);
    this.bufferSize = options.processorOptions && options.processorOptions.bufferSize || 1024; // Example, should match main script if passed
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferPos = 0;
    // Handle messages from the main thread if needed
    this.port.onmessage = (event) => {
      // console.log('[Worklet] Message from main thread:', event.data);
    };
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const inputChannel = input[0]; // Assuming mono input
      if (inputChannel) {
        // Buffer and send data
        for (let i = 0; i < inputChannel.length; i++) {
          this.buffer[this.bufferPos++] = inputChannel[i];
          if (this.bufferPos === this.bufferSize) {
            this.port.postMessage(this.buffer);
            this.bufferPos = 0;
          }
        }
      }
    }
    return true; // Keep processor alive
  }
}

registerProcessor('audio-processor', AudioProcessor);
*/
console.log("Reminder: Ensure 'audio-processor.js' is correctly implemented and accessible.");
console.log("The 'audio-processor.js' content shown here is a basic example.");
