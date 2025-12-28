import os
import logging
import wave
import struct
from typing import Optional 
from groq import Groq
import tempfile

from core.exceptions import SpeechToTextError

logger = logging.getLogger(__name__)

class SpeechToText:
    """A class to handle speech to text conversion"""

    def __init__(self):
        self._client: Optional[Groq] = None
    
    @property
    def client(self) -> Groq:
        """Get or create Groq client instance using singleton pattern"""
        if self._client is None:
            self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return self._client

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/wav") -> str:
        """Transcribe audio data to text.
        
        Args:
            audio_data (bytes): The audio data to transcribe.
            mime_type (str): The mime type of the audio data.
        
        Returns:
            str: The transcribed text.

        Raises:
            ValueError: If the audio file is empty or invalid.
            RuntimeError: If the transcription fails.
        """
        
        if not audio_data:
            raise ValueError("Audio data cannot be empty")
        
        try:
            logger.info(f"Transcribing audio: size={len(audio_data)} bytes, mime_type={mime_type}")
            
            # Handle raw PCM16 audio - need to convert to proper WAV
            if mime_type and ("pcm" in mime_type.lower() or mime_type == "pcm16"):
                logger.info("Detected raw PCM16 audio, converting to WAV...")
                
                # PCM16 parameters (Chainlit default)
                sample_rate = 24000  # Common sample rate for voice
                channels = 1
                sample_width = 2  # 16-bit = 2 bytes
                
                # Create a proper WAV file with headers
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_file_path = temp_file.name
                
                with wave.open(temp_file_path, 'wb') as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(sample_width)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_data)
                
                logger.info(f"WAV file created: {temp_file_path}")
            else:
                # Determine extension from mime type
                ext = ".wav"
                if mime_type:
                    if "webm" in mime_type:
                        ext = ".webm"
                    elif "mp4" in mime_type:
                        ext = ".mp4"
                    elif "mpeg" in mime_type or "mp3" in mime_type:
                        ext = ".mp3"
                    elif "ogg" in mime_type:
                         ext = ".ogg"

                logger.info(f"Using file extension: {ext}")
                
                # Create a temporary file with correct extension
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_file_path = temp_file.name
                
                logger.info(f"Temp file created: {temp_file_path}")

            try:
                # Open the temporary file and transcribe it
                with open(temp_file_path, "rb") as audio_file:
                    transcription = self.client.audio.transcriptions.create(
                        file=audio_file,
                        model="whisper-large-v3-turbo",
                        language="en",
                        response_format="text",
                    )
                
                if not transcription:
                    raise SpeechToTextError("Transcription result is empty")
                
                return transcription

            finally:
                # Clean up the temporary file.
                os.unlink(temp_file_path)

        except Exception as e:
            raise SpeechToTextError(f"Failed to transcribe audio: {str(e)}") from e



    