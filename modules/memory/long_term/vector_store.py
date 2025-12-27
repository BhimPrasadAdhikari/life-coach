import os 
from dataclasses import dataclass 
from datetime import datetime 

from typing import List, Optional 
from qdrant_client import QdrantClient 
from qdrant_client.models import Distance, PointStruct, VectorParams, ScoredPoint 
from sentence_transformers import SentenceTransformer 

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
    similarity_threshold: float = 0.9 
    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            self.client = QdrantClient(
                url=os.getenv("QDRANT_URL"),
                api_key=os.getenv("QDRANT_API_KEY"),
                timeout=60,  # Increase timeout for slow connections
            )
    def _collection_exists(self) -> bool:
        collections = self.client.get_collections().collections
        return any(col.name == self.collection_name for col in collections)
    
    def _create_collection(self) -> None:
        sample_embedding = self.model.encode("sample text")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=len(sample_embedding),
                distance=Distance.COSINE,
            ),
        )

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
        if not self._collection_exists():
            self._create_collection()

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

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )
    
    def search_memories(self, query: str, k: int = 5) -> List[Memory]:
        if not self._collection_exists():
            return []

        query_embedding = self.model.encode(query).tolist()

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=k,
        )

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




