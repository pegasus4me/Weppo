"""
    Speech input from user 
    This module is responsible for:
    Capturing audio input (e.g., via a microphone or API endpoint).
    Sending the audio to Eleven Labs' STT service.
    Returning the transcribed text.
"""

from dotenv import load_dotenv
from typing import List
from google.cloud import speech
from google.protobuf.duration_pb2 import Duration
from backend.agents.input.microphone_stream import MicrophoneStream
import os
from backend.agents.input.microphone_stream import listen_print_loop
load_dotenv()
# load google credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

def speech_to_text() -> str:
    """Transcribe speech from audio file and return the transcribed text."""
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
            single_utterance=True,
            enable_voice_activity_events=True, 
            # =speech.StreamingRecognitionConfig.VoiceActivityTimeout(speech_end_timeout=timeout, speech_start_timeout=Duration(seconds=10))
    )

    with MicrophoneStream(RATE, CHUNK) as stream:
                audio_generator = stream.generator()
                requests = (
                    speech.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator
                )
                responses = client.streaming_recognize(streaming_config, requests)
                # Get the transcribed text
                transcribed_text = listen_print_loop(responses)
                return transcribed_text if transcribed_text else ""                
