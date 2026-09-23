"""
graph/nodes/conversation.py — Handles main conversation responses.
"""
from __future__ import annotations
import logging
from langchain_core.runnables import RunnableConfig

from graph.state import State
from graph.utils.chains import get_character_response_chain

logger = logging.getLogger(__name__)


async def conversation_node(state: State, config: RunnableConfig) -> dict:
    chain = get_character_response_chain(
        summary=state.get("summary", ""),
        active_skills=state.get("active_skills_context", ""),
        evolved_context=state.get("evolved_context", ""),
        config=config,
    )
    response = await chain.ainvoke(
        {
            "messages": state.get("messages", []),
            "memory_context": state.get("memory_context", ""),
        },
        config=config,
    )
    return {"messages": response, "evolved_context": ""}
