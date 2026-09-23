"""
graph/nodes/image.py — Image generation response node.
"""
from __future__ import annotations
import logging
import uuid
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from graph.state import State
from modules.image.text_to_image import get_text_to_image_module
from core.paths import IMAGE_OUTPUT_DIR

logger = logging.getLogger(__name__)


async def image_node(state: State, config: RunnableConfig) -> dict:
    tti = get_text_to_image_module()
    scenario = await tti.create_scenario(state["messages"][-5:])
    enhanced = await tti.enhance_prompt(scenario.image_prompt)

    img_path = IMAGE_OUTPUT_DIR / f"image_{uuid.uuid4()}.png"
    await tti.generate_image(enhanced, str(img_path))

    return {
        "messages": [
            AIMessage(content="Here is the picture."),
        ],
        "image_path": str(img_path),
    }
