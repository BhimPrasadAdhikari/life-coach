import os
from langchain_groq import ChatGroq
from modules.speech.text_to_speech import TextToSpeech
from modules.image.text_to_image import TextToImage

def get_chat_model(temperature: float = 0.7):
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model="llama-3.1-8b-instant",
        temperature=temperature,
    )

def get_text_to_speech_module():
    return TextToSpeech()

def get_text_to_image_module():
    return TextToImage()
