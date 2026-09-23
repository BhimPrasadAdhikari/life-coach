"""
gateway/stream_manager.py — Event and token stream manager for WebSocket, SSE, and gateway clients.
"""
from __future__ import annotations
import logging
from typing import AsyncGenerator, Any
from langchain_core.messages import HumanMessage, AIMessageChunk

logger = logging.getLogger(__name__)

# Response nodes that generate text content to stream
STREAMABLE_NODES = {"conversation_node", "audio_node", "image_node"}


class StreamManager:
    """
    Manages event and token streaming from the compiled LangGraph orchestration engine
    for all client channels (WebSocket, HTTP SSE, Chainlit, Webhooks).
    """

    async def astream_tokens(
        self,
        compiled_app: Any,
        content: str,
        thread_id: str,
        model_key: str,
    ) -> AsyncGenerator[str, None]:
        """
        Streams AIMessage tokens across conversation_node, audio_node, and image_node workflows.
        """
        config = {"configurable": {"thread_id": thread_id, "model_key": model_key}}
        input_data = {"messages": [HumanMessage(content=content)]}

        try:
            # Use LangGraph astream with stream_mode="messages"
            async for chunk in compiled_app.astream(input_data, config, stream_mode="messages"):
                message_chunk, metadata = chunk[0], chunk[1]
                node_name = metadata.get("langgraph_node", "")

                if node_name in STREAMABLE_NODES and isinstance(message_chunk, AIMessageChunk):
                    if message_chunk.content:
                        yield str(message_chunk.content)
        except Exception as e:
            logger.error(f"StreamManager streaming error: {e}", exc_info=True)
            raise


stream_manager = StreamManager()
