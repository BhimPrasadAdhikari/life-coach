from langgraph.graph import END
from typing import Literal
from ..state import State


def route_after_evolve_check(
    state: State,
) -> Literal["self_evolve_node", "router_node"]:
    """After the self-evolve check, route to creation or normal router."""
    if state.get("workflow") == "self_evolve":
        return "self_evolve_node"
    return "router_node"


def select_workflow(
    state: State,
) -> Literal["conversation_node", "audio_node", "image_node"]:
    workflow = state.get("workflow", "conversation")
    if workflow == "audio":
        return "audio_node"
    elif workflow == "image":
        return "image_node"
    return "conversation_node"


def should_summarize_conversation(
    state: State,
) -> Literal["summarization_node", "__end__"]:
    messages = state["messages"]
    if len(messages) > 20:
        return "summarization_node"
    return END
