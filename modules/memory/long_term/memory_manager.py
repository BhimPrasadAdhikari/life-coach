import os 
import uuid 
from datetime import datetime 
import logging 


from typing import Optional, List
from pydantic import BaseModel, Field

from langchain_groq import ChatGroq 
from langchain_core.messages import BaseMessage 

from .vector_store import get_vector_store 
from core.prompts import MEMORY_ANALYSIS_PROMPT
class MemoryAnalysis(BaseModel):
    """Memory analysis result"""

    is_important: bool = Field(
        ...,
        description="Whether the message is important enough to be stored as a memory",
    )

    formatted_memory: Optional[str] = Field(
        ...,
        description="Formatted memory to be stored",
    )

class MemoryManager:
    """Manager class for handling memory extraction and storage"""
    def __init__(self):
        self.vector_store = get_vector_store()
        self.logger = logging.getLogger(__name__)
        self.llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.1,
            max_retries=2,
        ).with_structured_output(MemoryAnalysis)

    async def _analyze_memory(self, message: str) -> MemoryAnalysis:
        prompt = MEMORY_ANALYSIS_PROMPT.format(message=message)
        return await self.llm.ainvoke(prompt)
    
    async def extract_and_save_context(self, message: BaseMessage) -> None:
        if message.type != "human":
            return 
        
        analysis = await self._analyze_memory(message.content)
        if analysis.is_important and analysis.formatted_memory:
            similar = self.vector_store.find_similar_memory(analysis.formatted_memory)
            if similar:
                self.logger.info(f"Memory already exists: '{analysis.formatted_memory}'")
                return

            # store new memory 
            self.logger.info(f"Storing new memory: '{analysis.formatted_memory}'")
            self.vector_store.store_memory(
                text=analysis.formatted_memory,
                metadata={
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.now().isoformat(), 
                })

    def get_relevant_memories(self, context: str) -> List[str]:

        memories = self.vector_store.search_memories(context, k=6)
        if memories:
            for memory in memories:
                self.logger.info(f"Found memory: '{memory.text}' with score: {memory.score:.2f}")
            return [memory.text for memory in memories]

    def format_memories_for_prompt(self, memories: List[str]) -> str:
        if not memories:
            return ""

        return "\n".join(f"- {memory}" for memory in memories)



def get_memory_manager() -> MemoryManager:
    return MemoryManager()
