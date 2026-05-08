from langgraph.graph import MessagesState 
from typing import Literal, Optional

class State(MessagesState):
    summary: str
    memory_context: str
    workflow: Literal["conversation", "audio", "image", "self_evolve"]
    audio_buffer: bytes
    image_path: str
    # Self-evolution fields
    evolved_context: str    # Describes what Marcus just created/learned this turn
    active_skills_context: str  # Accumulated skills injected into system prompt
