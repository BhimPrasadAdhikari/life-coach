from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import List, Optional
from urllib.parse import urlparse

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from core.config import QDRANT_MEMORY_COLLECTION, SIMILARITY_THRESHOLD


logger = logging.getLogger(__name__)


@dataclass
class Memory:
    """Represents one stored memory."""

    text: str
    metadata: dict
    score: Optional[float] = None

    @property
    def id(self) -> Optional[str]:
        return self.metadata.get("id")

    @property
    def timestamp(self) -> Optional[datetime]:
        value = self.metadata.get("timestamp")
        return datetime.fromisoformat(value) if value else None


def get_user_collection_name(user_id: str) -> str:
    """Return a sanitized, user-namespaced Qdrant collection name."""
    clean_id = "".join(c for c in (user_id or "") if c.isalnum() or c in ("_", "-"))
    if not clean_id:
        clean_id = "default"
    return f"marcus_memory_{clean_id}"


class VectorStore:
    """Synchronous Qdrant-backed store using one user-filtered collection."""

    similarity_threshold = SIMILARITY_THRESHOLD

    def __init__(self) -> None:
        self.available = False
        self.client: Optional[QdrantClient] = None

        # This can load or download the model, so construct VectorStore
        # outside the event loop or inside asyncio.to_thread().
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        raw_url = os.getenv("QDRANT_URL", "").strip()
        api_key = os.getenv("QDRANT_API_KEY", "").strip()

        if not raw_url:
            logger.warning(
                "Qdrant disabled because QDRANT_URL is missing"
            )
            return

        parsed = urlparse(
            raw_url if "://" in raw_url else f"https://{raw_url}"
        )

        if not parsed.hostname:
            logger.error("Invalid QDRANT_URL: %s", raw_url)
            return

        try:
            self.client = QdrantClient(
                host=parsed.hostname,
                port=parsed.port or 6333,
                https=parsed.scheme != "http",
                api_key=api_key,
                timeout=60,
                check_compatibility=False,
            )

            # This is a synchronous network request.
            self.client.get_collections()
            self.available = True

        except Exception as exc:
            logger.error(
                "Qdrant unavailable; long-term memory is disabled: %s",
                exc,
            )

    def _collection_exists(self, collection_name: str) -> bool:
        if not self.available or self.client is None:
            return False

        try:
            collections = self.client.get_collections().collections
            return any(
                collection.name == collection_name
                for collection in collections
            )
        except Exception as exc:
            logger.warning("Qdrant collection check failed: %s", exc)
            self.available = False
            return False

    def _create_collection(self, collection_name: str) -> None:
        if not self.available or self.client is None:
            return

        try:
            sample_embedding = self.model.encode("sample text")

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=len(sample_embedding),
                    distance=Distance.COSINE,
                ),
            )
        except Exception as exc:
            logger.warning("Qdrant collection creation failed: %s", exc)
            self.available = False

    def find_similar_memory(
        self, text: str, user_id: str = "default"
    ) -> Optional[Memory]:
        results = self.search_memories(text, k=1, user_id=user_id)

        if (
            results
            and results[0].score is not None
            and results[0].score >= self.similarity_threshold
        ):
            return results[0]

        return None

    def store_memory(
        self, text: str, metadata: dict, user_id: str = "default"
    ) -> None:
        if not self.available or self.client is None:
            return

        collection_name = QDRANT_MEMORY_COLLECTION

        if not self._collection_exists(collection_name):
            self._create_collection(collection_name)

            if not self.available:
                return

        similar_memory = self.find_similar_memory(text, user_id=user_id)

        if similar_memory and similar_memory.id:
            metadata["id"] = similar_memory.id

        point_id = metadata.get("id") or str(uuid.uuid4())
        embedding = self.model.encode(text).tolist()

        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "text": text,
                **metadata,
                "user_id": user_id,
            },
        )

        try:
            self.client.upsert(
                collection_name=collection_name,
                points=[point],
            )
        except Exception as exc:
            logger.warning("Qdrant upsert failed: %s", exc)
            self.available = False

    def search_memories(
        self,
        query: str,
        k: int = 5,
        user_id: str = "default",
    ) -> List[Memory]:
        if not self.available or self.client is None:
            return []

        collection_name = QDRANT_MEMORY_COLLECTION

        if not self._collection_exists(collection_name):
            return []

        query_embedding = self.model.encode(query).tolist()

        try:
            response = self.client.query_points(
                collection_name=collection_name,
                query=query_embedding,
                limit=k,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=user_id),
                        )
                    ]
                ),
            )
        except Exception as exc:
            logger.warning("Qdrant query failed: %s", exc)
            self.available = False
            return []

        return [
            Memory(
                text=point.payload.get("text", ""),
                metadata={
                    key: value
                    for key, value in point.payload.items()
                    if key != "text"
                },
                score=point.score,
            )
            for point in response.points
        ]


_vector_store: Optional[VectorStore] = None
_vector_store_lock = Lock()


def get_vector_store() -> VectorStore:
    """Return the process-wide VectorStore instance."""

    global _vector_store

    if _vector_store is None:
        with _vector_store_lock:
            if _vector_store is None:
                _vector_store = VectorStore()

    return _vector_store