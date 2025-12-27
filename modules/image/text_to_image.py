"""Text to Image generation using Hugging Face Inference API."""
import os
from typing import Optional

from huggingface_hub import InferenceClient

from core.exceptions import TextToImageError


class TextToImage:
    """Handles text-to-image generation using Hugging Face's free Inference API."""
    
    # Free SDXL model available on Hugging Face
    MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
    
    def __init__(self):
        self._client: Optional[InferenceClient] = None
    
    @property
    def client(self) -> InferenceClient:
        """Lazy initialization of the Hugging Face client."""
        if self._client is None:
            token = os.getenv("HF_TOKEN")
            if not token:
                raise TextToImageError("HF_TOKEN environment variable not set")
            self._client = InferenceClient(token=token)
        return self._client
    
    async def generate(self, prompt: str) -> bytes:
        """Generate an image from a text prompt.
        
        Args:
            prompt: The text description of the image to generate.
            
        Returns:
            bytes: The generated image as PNG bytes.
            
        Raises:
            TextToImageError: If image generation fails.
        """
        if not prompt.strip():
            raise TextToImageError("Prompt cannot be empty")
        
        try:
            # Enhance prompt for better results
            enhanced_prompt = f"{prompt}, high quality, detailed, professional"
            
            # Generate image using Hugging Face Inference API
            image = self.client.text_to_image(
                prompt=enhanced_prompt,
                model=self.MODEL_ID,
            )
            
            # Convert PIL Image to bytes
            import io
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            
            if not image_bytes:
                raise TextToImageError("Generated image is empty")
            
            return image_bytes
            
        except Exception as e:
            raise TextToImageError(f"Failed to generate image: {str(e)}") from e


def get_text_to_image_module() -> TextToImage:
    """Factory function to get TextToImage instance."""
    return TextToImage()
