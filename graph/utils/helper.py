import os
from modules.speech.text_to_speech import TextToSpeech
from modules.image.text_to_image import TextToImage

def get_text_to_speech_module():
    return TextToSpeech()

def get_text_to_image_module():
    return TextToImage()
