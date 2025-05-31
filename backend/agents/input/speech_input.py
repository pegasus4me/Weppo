"""
    Speech input from user 
    This module is responsible for:
    Capturing audio input (e.g., via a microphone or API endpoint).
    Sending the audio to Eleven Labs' STT service.
    Returning the transcribed text.
"""

from dotenv import load_dotenv
from typing import List, Optional, Generator
from google.cloud import speech
from google.protobuf.duration_pb2 import Duration
from backend.agents.input.microphone_stream import MicrophoneStream
import os
import re
import sys
import queue
load_dotenv()
# load google credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

class WebSocketStream:
    """Handles audio streaming from WebSocket connection."""
    def __init__(self, rate: int = RATE, chunk: int = CHUNK):
        self._rate = rate
        self._chunk = chunk
        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self.closed = False
        return self

    def __exit__(self, type, value, traceback):
        """Closes the stream, regardless of whether the connection was lost or not."""
        self.closed = True
        # Signal the generator to terminate
        self._buff.put(None)

    def put_audio(self, audio_chunk):
        """Put an audio chunk into the buffer."""
        if not self.closed:
            self._buff.put(audio_chunk)

    def generator(self):
        """Generates audio chunks from the stream of audio data in chunks.
        
        Returns:
            A generator that outputs audio chunks.
        """
        print("DEBUG:WebSocketStream.generator: Starting audio generator.")
        while not self.closed:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            print("DEBUG:WebSocketStream.generator: Waiting for audio chunk...")
            chunk = self._buff.get()
            print(f"DEBUG:WebSocketStream.generator: Received chunk, size: {len(chunk) if chunk else 'None'}.")
            if chunk is None:
                print("DEBUG:WebSocketStream.generator: Received None chunk, exiting generator.")
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    # Attempt to get subsequent chunks without blocking
                    chunk = self._buff.get(block=False)
                    print(f"DEBUG:WebSocketStream.generator: Received chunk from buffer, size: {len(chunk) if chunk else 'None'}.")
                    if chunk is None:
                        # This case should ideally not be reached if None is only put on close,
                        # and self.closed would be true, exiting the outer loop.
                        # However, if it can happen, log and exit.
                        print("DEBUG:WebSocketStream.generator: Received None chunk from buffer, exiting generator.")
                        return
                    data.append(chunk)
                except queue.Empty:
                    print("DEBUG:WebSocketStream.generator: Emptied buffer for current yield batch.")
                    break

            joined_data = b"".join(data)
            print(f"DEBUG:WebSocketStream.generator: Yielding combined audio data, size: {len(joined_data)}.")
            yield joined_data

def speech_to_text(audio_stream: Optional[WebSocketStream] = None) -> Generator[str, None, None]:
    """Transcribe speech from audio stream and return the transcribed text."""
    print("DEBUG:speech_to_text: Entered function.")
    timeout = Duration(seconds=7)
    language_code = "en-US"
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code=language_code,
    )

    streaming_config = speech.StreamingRecognitionConfig(
            config=config, 
            interim_results=True,
            single_utterance=False,
            enable_voice_activity_events=True, 
    )

    # Use provided WebSocket stream or create new MicrophoneStream
    if audio_stream is None:
        print("DEBUG:speech_to_text: audio_stream is None, using 'error' stream placeholder.")
    stream = audio_stream if audio_stream else "error"
    print(f"DEBUG:speech_to_text: Starting with stream: {type(stream)}")
    with stream:
        print("DEBUG:speech_to_text: Creating audio generator from stream.")
        audio_generator = stream.generator()
        print("DEBUG:speech_to_text: Creating requests for Speech API.")
        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in audio_generator
        )
        print("DEBUG:speech_to_text: Calling client.streaming_recognize...")
        responses = client.streaming_recognize(streaming_config, requests)
        print("DEBUG:speech_to_text: client.streaming_recognize returned. Iterating over responses with listen_print_loop.")

        # Iterate over the transcripts yielded by listen_print_loop
        print("DEBUG:speech_to_text: Starting iteration over listen_print_loop.")
        for transcript in listen_print_loop(responses):
            print(f"DEBUG:speech_to_text: Yielding transcript from listen_print_loop: '{transcript}'")
            yield transcript
        print("DEBUG:speech_to_text: Finished iteration over listen_print_loop.")

def listen_print_loop(responses: object) -> Generator[str, None, None]:
    """Iterates through server responses and prints them.
    The responses passed is a generator that will block until a response
    is provided by the server.
    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU. Here we
    print only the transcription for the top alternative of the top result.
    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    Args:
        responses: List of server responses
    Returns:
        The transcribed text.
    """
    print("DEBUG:listen_print_loop: Entered function.")
    num_chars_printed = 0
    
    for response in responses:
        print(f"DEBUG:listen_print_loop: Received response: {response}")
        if not response.results:
            print("DEBUG:listen_print_loop: Response has no results. Continuing to next response.")
            continue
            
        # The `results` list is consecutive. For streaming, we only care about
        # the first result being considered, since once it's `is_final`, it
        # moves on to considering the next utterance.
        print(f"DEBUG:listen_print_loop: Processing result: {response.results[0]}")
        result = response.results[0]
        if not result.alternatives:
            print("DEBUG:listen_print_loop: Result has no alternatives. Continuing to next response.")
            continue
            
        # Display the transcription of the top alternative.
        current_transcript = result.alternatives[0].transcript
        print(f"DEBUG:listen_print_loop: Got alternatives. Top alternative: '{current_transcript}', Is final: {result.is_final}")
        
        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.
        #
        # If the previous result was longer than this one, we need to print
        # some extra spaces to overwrite the previous result
        overwrite_chars = " " * (num_chars_printed - len(current_transcript))
        
        if not result.is_final:
            print(f"DEBUG:listen_print_loop: Interim transcript: '{current_transcript}'.")
            sys.stdout.write(current_transcript + overwrite_chars + "\r")
            sys.stdout.flush()
            num_chars_printed = len(current_transcript)
        else:
            print(f"DEBUG:listen_print_loop: Final transcript: '{current_transcript}'. Yielding.")
            sys.stdout.write(current_transcript + overwrite_chars + "\n")
            sys.stdout.flush()
            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            if re.search(r"\b(exit|quit)\b", current_transcript, re.I):
                print("DEBUG:listen_print_loop: 'exit' or 'quit' detected.") # No break here anymore
                print("Exiting..") # Original print
                # If we want to stop the generator on "exit" or "quit", we might `return` here.
                # For now, per instructions, we remove the break to allow continuous processing.

            yield current_transcript
            num_chars_printed = 0
    print("DEBUG:listen_print_loop: Exiting function normally after loop completion.")
