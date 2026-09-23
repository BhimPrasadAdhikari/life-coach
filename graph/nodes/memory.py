"""
graph/nodes/memory.py — Memory saving and retrieval nodes.
"""
from __future__ import annotations
import asyncio
import logging
from graph.state import State
from modules.memory.long_term.memory_manager import get_memory_manager

logger = logging.getLogger(__name__)


async def memory_saving_node(state: State) -> dict:
    """
    Saves important user memories post-response.
    Uses user_id for Qdrant collection isolation.
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "default")
    human_messages = [m for m in messages if m.type == "human"]

    if not human_messages:
        return {}

    last_text = str(human_messages[-1].content).strip()
    words = last_text.split()
    clean_lower = last_text.lower().strip("!.,? ")

    # Skip extraction for short messages / generic pleasantries to save latency & tokens
    TRIVIAL_PHRASES = {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "good morning", "goodnight", "cool", "got it"}
    if len(words) < 4 or clean_lower in TRIVIAL_PHRASES:
        logger.debug(f"Skipping memory extraction for trivial message: '{last_text}'")
        return {}

    memory_manager = await asyncio.to_thread(get_memory_manager)
    await memory_manager.extract_and_save_context(
        human_messages[-1],
        user_id=user_id,
    )
    return {}


async def memory_retrieval_node(state: State) -> dict:
    """
    Retrieves user memories using user_id-namespaced vector search.
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "default")
    recent = " ".join(str(m.content) for m in messages[-3:])

    memory_manager = await asyncio.to_thread(get_memory_manager)
    memories = await memory_manager.get_relevant_memories(
        recent,
        user_id=user_id,
    )
    return {"memory_context": memory_manager.format_memories_for_prompt(memories)}
