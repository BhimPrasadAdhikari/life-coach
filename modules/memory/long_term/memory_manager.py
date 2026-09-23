from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from threading import Lock
from typing import List, Optional

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from core.prompts import MEMORY_ANALYSIS_PROMPT
from graph.utils.llm import make_llm, with_resilience

from .vector_store import get_vector_store


logger = logging.getLogger(__name__)


class MemoryAnalysis(BaseModel):
    """Result of deciding whether a message should be remembered."""

    is_important: bool = Field(
        description=(
            "Whether the message is important enough to store as memory"
        )
    )

    formatted_memory: Optional[str] = Field(
        default=None,
        description="The formatted memory to store",
    )


class MemoryManager:
    """Handles memory extraction, retrieval, and storage."""

    def __init__(self) -> None:
        self.vector_store = get_vector_store()

        from core.config import MEMORY_ANALYSIS_MODEL_KEY

        model = make_llm(
            MEMORY_ANALYSIS_MODEL_KEY,
            temperature=0.1,
        ).with_structured_output(MemoryAnalysis)
        self.llm = with_resilience(
            model,
            MEMORY_ANALYSIS_MODEL_KEY,
            temperature=0.1,
        )

    async def _analyze_memory(
        self,
        message: str,
    ) -> MemoryAnalysis:
        prompt = MEMORY_ANALYSIS_PROMPT.format(message=message)
        return await self.llm.ainvoke(prompt)

    async def extract_and_save_context(
        self,
        message: BaseMessage,
        user_id: str = "default",
    ) -> None:
        if message.type != "human":
            return

        analysis = await self._analyze_memory(str(message.content))

        if not (
            analysis.is_important
            and analysis.formatted_memory
        ):
            return

        formatted_memory = analysis.formatted_memory

        # SentenceTransformer and QdrantClient are synchronous.
        similar = await asyncio.to_thread(
            self.vector_store.find_similar_memory,
            formatted_memory,
            user_id,
        )

        if similar:
            logger.info(
                "Memory already exists: %r",
                formatted_memory,
            )
            return

        logger.info("Storing new memory for user %s: %r", user_id, formatted_memory)

        await asyncio.to_thread(
            self.vector_store.store_memory,
            formatted_memory,
            {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
            },
            user_id,
        )

    async def get_relevant_memories(
        self,
        context: str,
        user_id: str = "default",
        k: int = 6,
    ) -> List[str]:
        memories = await asyncio.to_thread(
            self.vector_store.search_memories,
            context,
            k,
            user_id,
        )

        for memory in memories:
            score = (
                f"{memory.score:.2f}"
                if memory.score is not None
                else "unknown"
            )
            logger.info(
                "Found memory %r with score %s for user %s",
                memory.text,
                score,
                user_id,
            )

        return [memory.text for memory in memories]

    @staticmethod
    def format_memories_for_prompt(
        memories: List[str],
    ) -> str:
        if not memories:
            return ""

        return "\n".join(
            f"- {memory}"
            for memory in memories
        )


_memory_manager: Optional[MemoryManager] = None
_memory_manager_lock = Lock()


def get_memory_manager() -> MemoryManager:
    """Return the process-wide MemoryManager instance."""

    global _memory_manager

    if _memory_manager is None:
        with _memory_manager_lock:
            if _memory_manager is None:
                _memory_manager = MemoryManager()

    return _memory_manager