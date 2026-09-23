"""
graph/nodes/summarization.py — Summarization node module.
"""
from __future__ import annotations
import logging
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from graph.state import State
from graph.utils.llm import get_chat_model_from_config

logger = logging.getLogger(__name__)


async def summarization_node(state: State, config: RunnableConfig) -> dict:
    model = get_chat_model_from_config(config, temperature=0.3)
    summary = state.get("summary", "")
    if summary:
        msg = f"Summary so far: {summary}\n\nExtend it with the new messages above."
    else:
        msg = "Create a concise summary of the conversation between Marcus and the User."

    response = await model.ainvoke(state["messages"] + [HumanMessage(content=msg)])
    return {
        "summary": response.content,
        "messages": [RemoveMessage(id=m.id) for m in state["messages"][:-5]],
        "summary_cooldown": True,
    }
