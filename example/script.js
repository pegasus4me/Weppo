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
const callButton = document.getElementById('callButton');
const statusDiv = document.getElementById('status');
const transcriptDiv = document.getElementById('transcript');
const agentResponseDiv = document.getElementById('agentResponse');
// It seems voiceOrb was referenced in the onmessage but not declared here.
// This was likely an oversight when script.js was originally written, assuming it was for file.html
// I will add it, assuming it's needed for the UI in file.html
const voiceOrb = document.getElementById('voiceOrb');


// WebSocket event handlers
ws.onopen = () => {
    console.log('WebSocket connection established');
    statusDiv.textContent = 'Status: Connected to server';
    if (callButton) { callButton.disabled = false; callButton.textContent = '📞 Call Agent'; } // Check if element exists
    ws.binaryType = "arraybuffer";
    console.log('WebSocket binaryType set to arraybuffer');
};

ws.onclose = () => {
    console.log('WebSocket connection closed');
    statusDiv.textContent = 'Status: Disconnected from server';
    if (callButton) { callButton.disabled = true; callButton.textContent = '📞 Call Agent'; }
    isCallActive = false;
    isStreamingAudio = false;
    audioBufferQueue = [];
    if (voiceOrb) voiceOrb.classList.remove('user-speaking', 'agent-speaking');
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    statusDiv.textContent = 'Status: Error connecting to server';
    if (callButton) { callButton.disabled = true; callButton.textContent = '📞 Call Agent'; }
    isCallActive = false;
    if (voiceOrb) voiceOrb.classList.remove('user-speaking', 'agent-speaking');
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
                if (voiceOrb) {
                    voiceOrb.classList.remove('user-speaking');
                    voiceOrb.classList.add('agent-speaking');
                }
            }

            if (response.type === 'tts_complete') {
                console.log("TTS audio streaming finished. Chunks sent:", response.chunks_sent);
                isStreamingAudio = false;
                if (voiceOrb) voiceOrb.classList.remove('agent-speaking');
                if (audioBufferQueue.length > 0) {
                    playBufferedAudio();
                }
            }

            if (response.type === 'tts_error') {
                console.error("TTS Error from server:", response.error);
                agentResponseDiv.innerHTML += `<br><strong style="color: #dc3545;">TTS Error:</strong> ${response.error}`;
                isStreamingAudio = false;
                audioBufferQueue = [];
                if (voiceOrb) voiceOrb.classList.remove('agent-speaking');
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

async function playBufferedAudio() {
    if (!ttsAudioContext || ttsAudioContext.state === 'closed') {
        console.error('TTS AudioContext not available or closed.');
        audioBufferQueue = [];
        return;
    }
    if (audioBufferQueue.length === 0) {
        console.log('Audio buffer queue is empty, nothing to play.');
        return;
    }

    console.log('Playing buffered audio. Chunks to process:', audioBufferQueue.length);

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
    audioBufferQueue = [];

    try {
        const audioBuffer = await ttsAudioContext.decodeAudioData(concatenatedBuffer.buffer);
        console.log('Audio data decoded successfully.');

        const sourceNode = ttsAudioContext.createBufferSource();
        sourceNode.buffer = audioBuffer;
        sourceNode.connect(ttsAudioContext.destination);
        sourceNode.onended = () => {
            console.log('TTS audio playback finished.');
            if (voiceOrb && !isStreamingAudio) voiceOrb.classList.remove('agent-speaking');
        };
        sourceNode.start(0);
        console.log('TTS audio playback started.');

    } catch (error) {
        console.error('Error decoding or playing TTS audio:', error);
        agentResponseDiv.innerHTML += `<br><strong style="color: orange;">Playback Error:</strong> Could not decode/play audio.`;
        if (voiceOrb) voiceOrb.classList.remove('agent-speaking');
    }
}

function formatAgentResponse(response) {
    let formatted = response
        .replace(/### (.*?)(?=\n|$)/g, '<h4>$1</h4>')
        .replace(/## (.*?)(?=\n|$)/g, '<h3>$1</h3>')
        .replace(/# (.*?)(?=\n|$)/g, '<h2>$1</h2>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.*$)/gim, '• $1')
        .replace(/\n/g, '<br>');
    return formatted;
}

async function startCall() {
    console.log('Starting call...');
    if (callButton) callButton.disabled = true;
    if (ws.readyState !== WebSocket.OPEN) {
        statusDiv.textContent = 'Status: ⚠️ WebSocket not connected. Please wait.';
        return;
    }
    try {
        transcriptDiv.textContent = '';
        agentResponseDiv.textContent = '';
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('Microphone access granted');

        if (!audioContext || audioContext.state === 'closed') {
            audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
            console.log('Recording Audio context created with sample rate:', SAMPLE_RATE);
        } else if (audioContext.sampleRate !== SAMPLE_RATE) {
            await audioContext.close();
            audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
            console.log('Recording Audio context re-created with sample rate:', SAMPLE_RATE);
        }

        await audioContext.audioWorklet.addModule('audio-processor.js');
        console.log('Audio worklet loaded');
        const source = audioContext.createMediaStreamSource(mediaStream);
        console.log('Audio source created from media stream');
        workletNode = new AudioWorkletNode(audioContext, 'audio-processor');
        console.log('Audio worklet node created');

        workletNode.port.onmessage = (event) => {
            if (ws.readyState === WebSocket.OPEN) {
                const audioData = event.data;
                const pcmData = new Int16Array(audioData.length);
                for (let i = 0; i < audioData.length; i++) {
                    pcmData[i] = audioData[i] * 0x7FFF;
                }
                ws.send(pcmData.buffer);
            }
        };

        source.connect(workletNode);
        console.log('Audio nodes (source -> worklet) connected for recording.');

        // IMPORTANT: Send start_listening message
        ws.send(JSON.stringify({ type: 'start_listening' }));
        console.log('Sent start_listening message to server.');

        isCallActive = true;
        statusDiv.textContent = 'Status: 🎤 Call Active... Speak now!';
        if (callButton) {
            callButton.textContent = '🛑 End Call';
            callButton.disabled = false;
        }
        if (voiceOrb) {
            voiceOrb.classList.remove('agent-speaking');
            voiceOrb.classList.add('user-speaking');
        }
    } catch (error) {
        console.error('Error starting call:', error);
        statusDiv.textContent = 'Status: Error starting call - ' + error.message;
        isCallActive = false;
        if (callButton) {
            callButton.textContent = '📞 Call Agent';
            callButton.disabled = (ws.readyState !== WebSocket.OPEN);
        }
        if (voiceOrb) voiceOrb.classList.remove('user-speaking', 'agent-speaking');
    }
}

function endCall() {
    isCallActive = false;
    console.log('Ending call...');
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        console.log('Media stream tracks stopped');
    }
    if (workletNode) {
        workletNode.port.onmessage = null;
        workletNode.disconnect();
        console.log('Worklet node disconnected');
        workletNode = null;
    }
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close().then(() => console.log('Recording AudioContext closed.'));
    }

    // IMPORTANT: Send stop_listening message
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop_listening' }));
        console.log('Sent stop_listening message to server.');
    }

    statusDiv.textContent = 'Status: ✅ Call Ended. Ready for new call.';
    if (callButton) {
        callButton.textContent = '📞 Call Agent';
        callButton.disabled = (ws.readyState !== WebSocket.OPEN);
    }
    if (voiceOrb) voiceOrb.classList.remove('user-speaking');
    // Do not remove agent-speaking here, as TTS might still be playing
}

// Event listeners
if (callButton) {
    callButton.addEventListener('click', () => {
        if (!isCallActive) {
            startCall(); // Use new function name
        } else {
            endCall();   // Use new function name
        }
    });
}

// Initialize UI state
if (callButton) callButton.disabled = true;
console.log('UI initialized in script.js');
console.log("Reminder: Ensure 'audio-processor.js' is correctly implemented and accessible.");
