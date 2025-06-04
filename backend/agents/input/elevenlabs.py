import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

class ElevenLabsTTS:
    def __init__(self):
        """
        Initializes the ElevenLabs client using the API key from the
        ELEVENLABS_API_KEY environment variable.
        """
        load_dotenv()
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable not found.")
        self.client = ElevenLabs(api_key=api_key)

    def stream_audio(
        self,
        text: str,
        voice_id: str = "vBKc2FfBKJfcZNyEt1n6",
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
    ):
        """
        Takes text as input and yields audio chunks.

        Args:
            text: The text to convert to speech.
            voice_id: The ID of the voice to use.
            model_id: The ID of the model to use.
            output_format: The desired output format for the audio.

        Yields:
            Audio chunks from the ElevenLabs API.
        """
        audio_stream = self.client.text_to_speech.convert_as_stream(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
        )
        for chunk in audio_stream:
            yield chunk

if __name__ == '__main__':
    # Example usage (optional, for testing)
    try:
        tts = ElevenLabsTTS()
        text_to_speak = "Hello, this is a test of the ElevenLabs streaming functionality."
        audio_generator = tts.stream_audio(text_to_speak)

        print(f"Streaming audio for: '{text_to_speak}'")
        output_filename = "test_audio_stream.mp3"
        with open(output_filename, "wb") as f:
            for i, chunk in enumerate(audio_generator):
                print(f"Received chunk {i+1}, size: {len(chunk)} bytes")
                f.write(chunk)
        print(f"Finished streaming. Audio saved to {output_filename}")

    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
