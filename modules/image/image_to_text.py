import base64
import logging
import os
from typing import Optional, Union 

from core.exceptions import ImageToTextError

from groq import Groq 

class ImageToText:
    """A class to handle image-to-text conversion."""

    def __init__(self):
        self._client: Optional[Groq] = None 
        self.logger = logging.getLogger(__name__)

    @property
    def client(self):
        if self._client is None:
            self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return self._client

    async def analyze_image(self, image_bytes:bytes, prompt: str = "", mime_type: str = "image/jpeg") -> str:
        """Analyze an image and return the text decription

        Args:
            image_bytes (bytes): The image to analyze.
            prompt (str, optional): A prompt to guide the image analysis. Defaults to "".
            mime_type (str, optional): The mime type of the image. Defaults to "image/jpeg".

        Returns:
            str: The text description of the image.
        Raises:
            ValueError: If the image_bytes is empty.
        """
        try:
            if not image_bytes:
                raise ValueError("Image bytes cannot be empty")

            # convert image to base64 (must use encode, not decode)
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            # default prompt if not provided
            if not prompt:
                prompt = "Describe this image in detail. Focus on the main subjects, setting, and any text visible."

            # Create the messages for the Vision API
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                            },
                        },
                    ],
                }
            ]

            # Make the API call 
            response = self.client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=messages,
                max_tokens=1000,
            )

            if not response.choices:
                raise ImageToTextError("No response from the API")

            description = response.choices[0].message.content
            self.logger.info(f"Image description: {description}")
            return description
        except Exception as e:
            raise ImageToTextError(f"Failed to analyze image: {e}") from e

           
            
