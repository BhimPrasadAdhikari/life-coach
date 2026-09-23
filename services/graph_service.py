import logging
import os
from typing import AsyncGenerator, Any
from core.asyncio_compat import configure_event_loop_policy
from langchain_core.messages import HumanMessage, AIMessageChunk
from graph.graph import create_graph
from core.config import CHECKPOINT_DATABASE_URL

configure_event_loop_policy()

logger = logging.getLogger(__name__)

class GraphService:
    """
    Channel-agnostic service for initializing, compiling, and running 
    the LangGraph agent state engine with persistent check-pointing.
    """
    _instance = None

    def __init__(self, db_url: str = CHECKPOINT_DATABASE_URL):
        self.db_url = db_url
        self._cm = None  # Holds the context manager reference to prevent GC / GeneratorExit
        self._saver = None
        self._compiled_app = None

    async def initialize(self) -> None:
        """Initialize the shared PostgreSQL checkpointer and compile the graph once."""
        if not self._compiled_app:
            if not self.db_url:
                raise RuntimeError(
                    "CHECKPOINT_DATABASE_URL or DATABASE_URL must be configured "
                    "for PostgreSQL checkpointing"
                )

            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            postgres_url = self.db_url.replace("postgres://", "postgresql://", 1)
            postgres_url = postgres_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            self._cm = AsyncPostgresSaver.from_conn_string(postgres_url)
            self._saver = await self._cm.__aenter__()
            await self._saver.setup()
            self._compiled_app = create_graph().compile(checkpointer=self._saver)
            logger.info("LangGraph state engine compiled with PostgreSQL checkpointer.")

    async def close(self) -> None:
        """Gracefully closes the SQLite checkpointer context manager upon shutdown."""
        if self._cm:
            await self._cm.__aexit__(None, None, None)
            self._cm = None
            self._saver = None
            self._compiled_app = None

    async def stream_conversation(
        self, content: str, thread_id: str, model_key: str
    ) -> AsyncGenerator[str, None]:
        """Streams conversation tokens from conversation_node, audio_node, and image_node workflows."""
        if not self._compiled_app:
            await self.initialize()

        from gateway.stream_manager import stream_manager
        async for token in stream_manager.astream_tokens(
            self._compiled_app, content, thread_id, model_key
        ):
            yield token

    async def invoke_graph(
        self,
        content: str,
        thread_id: str,
        model_key: str,
        user_id: str = "default",
        channel: str = "api",
    ) -> dict[str, Any]:
        """Invoke one graph turn with shared persistence and channel context."""
        if not self._compiled_app:
            await self.initialize()

        config = {"configurable": {"thread_id": thread_id, "model_key": model_key}}
        return await self._compiled_app.ainvoke(
            {
                "messages": [HumanMessage(content=content)],
                "user_id": user_id,
                "thread_id": thread_id,
                "channel": channel,
            },
            config,
        )

    async def get_state(self, thread_id: str, model_key: str) -> Any:
        """Retrieves current state checkpoint for a thread."""
        if not self._compiled_app:
            await self.initialize()

        config = {"configurable": {"thread_id": thread_id, "model_key": model_key}}
        return await self._compiled_app.aget_state(config)

graph_service = GraphService()