from langgraph.graph import END
from typing import Literal
from ..state import State

def select_workflow(state: State) -> Literal["conversation_node", "audio_node", "image_node"]:
    workflow = state["workflow"]

    if workflow == "audio":
        return "audio_node"
    elif workflow == "image":
        return "image_node"
    
    return "conversation_node"

def should_summarize_conversation(state: State) -> Literal["summarization_node", "__end__"]:
    messages = state["messages"]

    if len(messages) > 20:
        return "summarization_node"
    
    return END


