from __future__ import annotations

import asyncio
import os 
from pathlib import Path
from typing import Optional, Any 

from core.exceptions import TextToSpeechError 

class TextToSpeech:

    def __init__(self):
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from elevenlabs.client import AsyncElevenLabs
            except ImportError as e:
                raise TextToSpeechError("elevenlabs package is not installed.") from e

            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                raise ValueError("ELEVENLABS_API_KEY environment variable is not set.")

            self._client = AsyncElevenLabs(
                api_key=api_key
            )

        return self._client
    
    async def synthesize(self, text: str, output_path: str | Path) -> str:
        """Converts text to speech.

        Args:
            text (str): The text to convert to speech.

        Returns:
            str: The audio path.

        Raises:
            ValueError: If the text is empty or too long.
            TextToSpeechError: If the text to speech conversion fails.
        """
        if not text.strip():
            raise ValueError("Text cannot be empty.")
        
        if len(text) > 5000: # ElevenLabs typical limit 
            raise ValueError("Text is too long.")
        
        try:
            from elevenlabs import VoiceSettings
            audio_generator = await self.client.text_to_speech.convert(
                voice_id="IKne3meq5aSn9XLyUdCD",
                output_format="mp3_44100_128",
                text=text,
                model_id="eleven_turbo_v2",
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.5,
                )
            )

            chunks: list[bytes] = []

            async for chunk in audio_generator:
                if chunk:
                    chunks.append(chunk)

            audio_bytes = b"".join(chunks)

            if not audio_bytes:
                raise TextToSpeechError("Generated audio is empty")
            
            await asyncio.to_thread(
                self._save_audio,
                output_path,
                audio_bytes,
            )

            return str(output_path)
        except TextToSpeechError:
            raise
        except Exception as e:
            raise TextToSpeechError(f"Failed to synthesize text: {str(e)}") from e
        
    @staticmethod
    def _save_audio(
        output_path: str,
        audio_bytes: bytes,
    ) -> None:
        path = Path(output_path)

        if not path.parent.exists():
            raise TextToSpeechError(
                f"Audio output directory does not exist: {path.parent}"
            )
        
        path.write_bytes(audio_bytes)

_tts_instance: Optional[TextToSpeech] = None

def get_text_to_speech_module() -> TextToSpeech:
    """Returns a singleton instance of the TextToSpeech class."""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TextToSpeech()
    return _tts_instance