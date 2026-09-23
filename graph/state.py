from typing import Literal, Optional, Any
from langgraph.graph import MessagesState


class State(MessagesState):
    user_id: str
    thread_id: str
    workflow: Literal["conversation", "audio", "image", "self_evolve"]
    memory_context: str
    active_skills_context: str
    summary: str
    summary_cooldown: Optional[bool]
    evolution_pending: bool
    audio_path: Optional[str]
    image_path: Optional[str]
    pending_action: Optional[dict[str, Any]]
    evolved_context: str

