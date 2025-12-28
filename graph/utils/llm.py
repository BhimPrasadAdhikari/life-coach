import os
from langchain_groq import ChatGroq

def get_chat_model(temperature: float = 0.7):
    """Factory function to get default ChatGroq model."""
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model="llama-3.1-8b-instant",
        temperature=temperature,
    )
