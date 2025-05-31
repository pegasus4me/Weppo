class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        // Match server's chunk size: 1600 samples (100ms at 16kHz)
        this._bufferSize = 1600;
        this._buffer = new Float32Array(this._bufferSize);
        this._bufferIndex = 0;
    }

    process(inputs, outputs) {
        const input = inputs[0];
        const channel = input[0];

        if (!channel) return true;

        // Fill our buffer
        for (let i = 0; i < channel.length; i++) {
            this._buffer[this._bufferIndex++] = channel[i];

            // When buffer is full, send it to the main thread
            if (this._bufferIndex >= this._bufferSize) {
                this.port.postMessage(this._buffer);
                this._bufferIndex = 0;
            }
        }

        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor); 