import os 
from dataclasses import dataclass 
from datetime import datetime 
from urllib.parse import urlparse

from typing import List, Optional 
from qdrant_client import QdrantClient 
from qdrant_client.models import Distance, PointStruct, VectorParams, ScoredPoint 
from sentence_transformers import SentenceTransformer 
import logging

@dataclass
class Memory:
    "Represents a memory entry in the vector store"
    text: str 
    metadata: dict 
    score: Optional[float] = None 

    @property 
    def id(self) -> Optional[str]:
        return self.metadata.get("id") 

    @property
    def timestamp(self) -> Optional[datetime]:
        ts = self.metadata.get("timestamp")
        return datetime.fromisoformat(ts) if ts else None 

class VectorStore:
    """ A class to handle vector storage operations using Qdrant""" 
    _initialized: bool = False 
    collection_name: str = "lifecoach_memory"
    from core.config import SIMILARITY_THRESHOLD
    similarity_threshold: float = SIMILARITY_THRESHOLD
    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self.logger = logging.getLogger(__name__)
            self.available = False
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            raw_url = os.getenv("QDRANT_URL", "").strip()
            api_key = os.getenv("QDRANT_API_KEY")

            if not raw_url or not api_key:
                self.logger.warning("Qdrant disabled: missing QDRANT_URL or QDRANT_API_KEY")
                return

            parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
            host = parsed.hostname
            https = parsed.scheme != "http"
            port = parsed.port if parsed.port else (6333 if https else 6333)

            if not host:
                self.logger.error(f"Qdrant disabled: invalid QDRANT_URL '{raw_url}'")
                return

            try:
                self.client = QdrantClient(
                    host=host,
                    port=port,
                    https=https,
                    api_key=api_key,
                    timeout=60,
                    check_compatibility=False,
                )
                self.client.get_collections()
                self.available = True
            except Exception as e:
                self.logger.error(f"Qdrant unavailable, continuing without long-term memory: {e}")

    def _collection_exists(self) -> bool:
        if not self.available:
            return False
        try:
            collections = self.client.get_collections().collections
            return any(col.name == self.collection_name for col in collections)
        except Exception as e:
            self.logger.warning(f"Qdrant collection check failed: {e}")
            self.available = False
            return False
    
    def _create_collection(self) -> None:
        if not self.available:
            return
        sample_embedding = self.model.encode("sample text")
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=len(sample_embedding),
                    distance=Distance.COSINE,
                ),
            )
        except Exception as e:
            self.logger.warning(f"Qdrant create_collection failed: {e}")
            self.available = False

    def find_similar_memory(self, text: str) -> Optional[Memory]:
        """Find if a similar memory already exists.

        Args: 
         text: The text to search for.
        
        Returns:
         Optional Memory if a similar one is found
        """

        results = self.search_memories(text, k=1)
        if results and results[0].score >= self.similarity_threshold:
            return results[0]
        return None

    def store_memory(self, text: str, metadata: dict) -> None:
        """Store a new memory in the vector store.
        Args:
         text: The text of the memory.
         metadata: The metadata associated with the memory.
        """ 
        if not self.available:
            return
        if not self._collection_exists():
            self._create_collection()
            if not self.available:
                return

        similar_memory = self.find_similar_memory(text)
        if similar_memory and similar_memory.id:
            metadata["id"] = similar_memory.id 
        
        # Generate UUID if no ID provided (Qdrant requires unsigned int or UUID)
        import uuid
        point_id = metadata.get("id") or str(uuid.uuid4())
        
        embedding = self.model.encode(text).tolist()
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "text": text,
                **metadata,
            }
        )

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
        except Exception as e:
            self.logger.warning(f"Qdrant upsert failed: {e}")
            self.available = False
    
    def search_memories(self, query: str, k: int = 5) -> List[Memory]:
        if not self.available:
            return []
        if not self._collection_exists():
            return []

        query_embedding = self.model.encode(query).tolist()

        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=k,
            )
        except Exception as e:
            self.logger.warning(f"Qdrant query failed: {e}")
            self.available = False
            return []

        points = response.points

        return [
            Memory(
                text=point.payload["text"],
                metadata={key: val for key, val in point.payload.items() if key != "text"},
                score=point.score,
            )
            for point in points
        ]



def get_vector_store() -> VectorStore:
    """Get or create the VectorStore singleton instance."""
    return VectorStore()




