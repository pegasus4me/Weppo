import os
from elevenlabs.client import ElevenLabs
from elevenlabs import play, stream, save

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY environment variable not set.")

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# TODO: Make voice_id and model_id configurable if needed
DEFAULT_VOICE_ID = "tnSpp4vdxKPjI9w0GnoV" # Example, choose an appropriate default or make configurable
DEFAULT_MODEL_ID = "eleven_flash_v2_5" # Or your preferred model

async def text_to_speech_stream(text: str, voice_id: str = None, model_id: str = None):
    """
    Converts text to speech and yields audio chunks.
    """
    if not text:
        print("INFO: text_to_speech_stream called with empty text. Yielding nothing.")
        if False: # This is a trick to make sure it's an async generator
            yield
        return # Now it returns an empty async generator, not None.

    actual_voice_id =  DEFAULT_VOICE_ID
    actual_model_id =  DEFAULT_MODEL_ID

    # Find the voice by name if a string name is provided, otherwise assume it's an ID
    selected_voice = None
    if isinstance(actual_voice_id, str):
        voices = client.voices.get_all().voices
        for voice in voices:
            if voice.name == actual_voice_id:
                selected_voice = voice
                break
        if not selected_voice: # Fallback if name not found, use the first available voice
             if voices:
                selected_voice = voices[0]
                print(f"Warning: Voice '{actual_voice_id}' not found. Using first available voice: {selected_voice.name}")
             else:
                print(f"Error: Voice '{actual_voice_id}' not found and no voices available.")
                raise ValueError(f"Voice '{actual_voice_id}' not found and no voices available.")
    else: # Assuming actual_voice_id is already a Voice object or ID string that API understands
        selected_voice = actual_voice_id


    audio_stream = client.generate(
        text=text,
        voice=selected_voice, # Use the Voice object
        model=actual_model_id,
        stream=True
    )

    if audio_stream:
        for chunk in audio_stream:
            yield chunk
    else:
        print("Error: ElevenLabs audio stream is None.")
        # Optionally, yield a silent chunk or raise an error
        # For now, just returns, resulting in no audio being sent

async def text_to_speech_save_to_file(text: str, file_path: str, voice_id: str = None, model_id: str = None):
    """
    Converts text to speech and saves it to a file.
    """
    actual_voice_id =  DEFAULT_VOICE_ID
    actual_model_id =  DEFAULT_MODEL_ID

    selected_voice = None
    if isinstance(actual_voice_id, str):
        voices = client.voices.get_all().voices
        for voice in voices:
            if voice.name == actual_voice_id:
                selected_voice = voice
                break
        if not selected_voice: # Fallback if name not found
             if voices:
                selected_voice = voices[0]
                print(f"Warning: Voice '{actual_voice_id}' not found. Using first available voice: {selected_voice.name}")
             else:
                print(f"Error: Voice '{actual_voice_id}' not found and no voices available.")
                raise ValueError(f"Voice '{actual_voice_id}' not found and no voices available.")
    else:
        selected_voice = actual_voice_id

    audio = client.generate(
        text=text,
        voice=selected_voice,
        model=actual_model_id
    )
    if audio:
        save(audio, file_path)
        print(f"Audio saved to {file_path}")
    else:
        print(f"Error: Could not generate audio for text: {text}")

# Example Usage (optional, for testing)
if __name__ == "__main__":
    import asyncio

    async def main_stream():
        sample_text = "Hello, this is a test of ElevenLabs streaming."
        print(f"Streaming audio for: '{sample_text}'")
        async for audio_chunk in text_to_speech_stream(sample_text):
            print(f"Received audio chunk of size: {len(audio_chunk)}")
            # In a real application, you would send this chunk over a WebSocket or play it.

    async def main_save():
        sample_text = "Hello, this is a test of ElevenLabs saving to file."
        file = "test_elevenlabs_output.mp3"
        print(f"Saving audio for: '{sample_text}' to {file}")
        await text_to_speech_save_to_file(sample_text, file)

    # asyncio.run(main_stream())
    # To run the save function:
    # asyncio.run(main_save())
