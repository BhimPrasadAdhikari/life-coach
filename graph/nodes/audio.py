"""
graph/nodes/audio.py — Audio speech synthesis response node.
"""
from __future__ import annotations
import logging
import uuid
from langchain_core.runnables import RunnableConfig

from graph.state import State
from graph.utils.chains import get_character_response_chain
from modules.speech.text_to_speech import get_text_to_speech_module
from core.paths import AUDIO_OUTPUT_DIR

logger = logging.getLogger(__name__)


async def audio_node(state: State, config: RunnableConfig) -> dict:
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

    audio_path = AUDIO_OUTPUT_DIR / f"audio_{uuid.uuid4()}.mp3"
    tts = get_text_to_speech_module()

    await tts.synthesize(
        str(response.content),
        str(audio_path),
    )

    return {
        "messages": response,
        "audio_path": str(audio_path),
        "evolved_context": "",
    }
