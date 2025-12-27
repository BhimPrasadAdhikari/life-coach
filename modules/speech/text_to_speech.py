import os 
from typing import Optional 

from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

from core.exceptions import TextToSpeechError 

class TextToSpeech:

    def __init__(self):
        self._client: Optional[ElevenLabs] = None

    @property
    def client(self) -> ElevenLabs:
        if self._client is None:
            self._client = ElevenLabs(
                api_key=os.getenv("ELEVENLABS_API_KEY")
            )
        return self._client
    
    async def synthesize(self, text: str) -> bytes:
        """Converts text to speech.

        Args:
            text (str): The text to convert to speech.

        Returns:
            bytes: The audio data of the synthesized speech.

        Raises:
            ValueError: If the text is empty or too long.
            TextToSpeechError: If the text to speech conversion fails.
        """
        if not text.strip():
            raise ValueError("Text cannot be empty.")
        
        if len(text) > 5000: # ElevanLabs typical limit 
            raise ValueError("Text is too long.")
        
        try:
            audio_generator = self.client.text_to_speech.convert(
                voice_id="IKne3meq5aSn9XLyUdCD",
                text=text,
                model_id="eleven_turbo_v2",
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.5,
                )
            )

            audio_bytes = b"".join(audio_generator)
            if not audio_bytes:
                raise TextToSpeechError("Generated audio is empty")

            return audio_bytes

        except Exception as e:
            raise TextToSpeechError(f"Failed to synthesize text: {str(e)}") from e