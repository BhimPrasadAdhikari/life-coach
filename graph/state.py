from langgraph.graph import MessagesState 
from typing import Literal, Optional

class State(MessagesState):
    summary: str 
    memory_context: str 
    workflow: Literal["conversation", "audio", "image"]
    audio_buffer: bytes
    image_buffer: bytes
