from io import BytesIO
import logging

from modules.image.image_to_text import get_image_to_text_module
from modules.speech.speech_to_text import get_speech_to_text_module
from modules.speech.text_to_speech import get_text_to_speech_module

logger = logging.getLogger(__name__)

class MediaService:
    """
    Channel-agnostic service wrapper for multimodal capabilities 
    (Speech-to-Text, Text-to-Speech, Vision processing).
    """
    def __init__(self):
        self.image_to_text = None
        self.speech_to_text = None
        self.text_to_speech = None

    async def analyze_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        if self.image_to_text is None:
            self.image_to_text = get_image_to_text_module()
        prompt = "Describe this image in detail. Identify main objects, text, and actions visible."
        return await self.image_to_text.analyze_image(image_bytes, prompt, mime_type=mime_type)

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str | None = None) -> str:
        if self.speech_to_text is None:
            self.speech_to_text = get_speech_to_text_module()
        return await self.speech_to_text.transcribe(audio_bytes, mime_type=mime_type)

    async def synthesize_speech(self, text: str) -> BytesIO:
        if self.text_to_speech is None:
            self.text_to_speech = get_text_to_speech_module()
        return await self.text_to_speech.synthesize(text)

media_service = MediaService()