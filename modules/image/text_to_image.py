import os
import logging
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from huggingface_hub import InferenceClient
from graph.utils.llm import get_chat_model
from core.exceptions import TextToImageError
from pydantic import BaseModel, Field

from core.prompts import IMAGE_SCENARIO_PROMPT, IMAGE_ENHANCEMENT_PROMPT

class ScenarioPrompt(BaseModel):
    """Class for the scenario prompt"""

    narrative: str = Field(..., description="Narrative of the scenario")
    image_prompt: str = Field(..., description="Image prompt for the scenario")

class EnhancedPrompt(BaseModel):
    """Class for the text prompt"""

    content: str = Field(..., description="The enhanced text prompt to generate the image")

class TextToImage:
    """Handles text-to-image generation using Hugging Face's free Inference API."""
    
    # Free SDXL model available on Hugging Face
    MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
    
    def __init__(self):
        self._client: Optional[InferenceClient] = None
        self.logger = logging.getLogger(__name__)

    async def create_scenario(self, chat_history: list = None) -> ScenarioPrompt:
        """Creates a first-person narrative scenario prompt and corresponding image prompt from the chat history."""

        try:
            formatted_history = "\n".join([f"{msg.type.title()}: {msg.content}" for msg in chat_history[-5:]])
            self.logger.info(f"Creating Scenario form chat history: {formatted_history}")

            llm = get_chat_model(temperature=0.4).with_structured_output(ScenarioPrompt)
            
            chain = (ChatPromptTemplate.from_template(IMAGE_SCENARIO_PROMPT) | llm)

            scenario = await chain.ainvoke({"chat_history": formatted_history})
            self.logger.info(f"Created scenario: {scenario}")

            return scenario

        except Exception as e:
            raise TextToImageError(f"Failed to create scenario: {str(e)}") from e

    async def enhance_prompt(self, prompt: str) -> str:
        """Enhances the simple prompt with additonal details and context"""

        try:
            self.logger.info(f"Enhancing prompt: {prompt}")

            llm = get_chat_model(temperature=0.4).with_structured_output(EnhancedPrompt)

            chain = (ChatPromptTemplate.from_template(IMAGE_ENHANCEMENT_PROMPT) | llm)

            enhanced_prompt = await chain.ainvoke({"prompt": prompt})
            self.logger.info(f"Enhanced prompt: {enhanced_prompt.content}")

            return enhanced_prompt.content

        except Exception as e:
            raise TextToImageError(f"Failed to enhance prompt: {str(e)}") from e
    
    @property
    def client(self) -> InferenceClient:
        """Lazy initialization of the Hugging Face client."""
        if self._client is None:
            token = os.getenv("HF_TOKEN")
            if not token:
                raise TextToImageError("HF_TOKEN environment variable not set")
            self._client = InferenceClient(token=token)
        return self._client
    
    async def generate_image(self, prompt: str, output_path: str = "" ) -> bytes:
        """Generate an image from a text prompt.
        
        Args:
            prompt: The text description of the image to generate.
            output_path: The path to save the generated image.
            
        Returns:
            bytes: The generated image as PNG bytes.
            
        Raises:
            TextToImageError: If image generation fails.
        """
        if not prompt.strip():
            raise TextToImageError("Prompt cannot be empty")
        
        try:
            # Generate image using Hugging Face Inference API
            self.logger.info(f"Generating image for prompt: {prompt}")
            image = self.client.text_to_image(
                prompt=prompt,
                model=self.MODEL_ID,
            )
            
            # Convert PIL Image to bytes
            import io
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            
            if not image_bytes:
                raise TextToImageError("Generated image is empty")
                
            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                image.save(output_path)
            
            return image_bytes
            
        except Exception as e:
            raise TextToImageError(f"Failed to generate image: {str(e)}") from e


def get_text_to_image_module() -> TextToImage:
    """Factory function to get TextToImage instance."""
    return TextToImage()


