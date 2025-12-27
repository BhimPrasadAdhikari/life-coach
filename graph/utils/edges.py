from typing import Literal
from ..state import State

def select_workflow(state: State) -> Literal["conversation_node", "audio_node", "image_node"]:
    workflow = state["workflow"]

    if workflow == "audio":
        return "audio_node"
    elif workflow == "image":
        return "image_node"
    
    return "conversation_node"
