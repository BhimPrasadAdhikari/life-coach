"""
core/cache.py — Redis cache manager for session state, rate limits, and active skill context caching.
"""
from __future__ import annotations
import os
import logging
import threading
import time
from typing import Optional

from core.config import IDEMPOTENCY_TTL_SECONDS, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS

logger = logging.getLogger(__name__)

try:
    import redis
except ImportError:
    redis = None


class RedisCache:
    """
    Redis cache manager handling session keys, rate limiting, and 5-minute skill context caching.
    Includes an in-memory fallback when Redis server is unavailable.
    """
    _instance: Optional[RedisCache] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> RedisCache:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, host: str = None, port: int = None, url: str = None):
        if self._initialized:
            return

        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.url = url or os.getenv("REDIS_URL", f"redis://{self.host}:{self.port}/0")

        self.client = None
        self._in_memory_fallback = {}
        self._fallback_lock = threading.Lock()

        if redis is not None:
            try:
                self.client = redis.Redis.from_url(
                    self.url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                # Ping to check connection readiness
                self.client.ping()
                logger.info("RedisCache connected successfully to Redis server.")
            except Exception as e:
                logger.warning(f"RedisCache: Redis connection failed ({e}). Falling back to in-memory cache.")
                self.client = None
        else:
            logger.warning("RedisCache: redis package not found. Falling back to in-memory cache.")

        self._initialized = True

    def get_skills_context(self, user_id: str) -> Optional[str]:
        """Fetch cached active skills context string for a given user."""
        key = f"skills_cache:{user_id}"
        if self.client is not None:
            try:
                return self.client.get(key)
            except Exception as e:
                logger.warning(f"RedisCache get error: {e}")
        return self._memory_get(key)

    def set_skills_context(self, user_id: str, skills_text: str, ttl: int = 300) -> None:
        """Cache active skills context string for user_id with specified TTL (default 5 minutes)."""
        key = f"skills_cache:{user_id}"
        if self.client is not None:
            try:
                self.client.setex(key, ttl, skills_text)
                return
            except Exception as e:
                logger.warning(f"RedisCache set error: {e}")
        self._memory_set(key, skills_text, ttl)

    def invalidate_skills_cache(self, user_id: Optional[str] = None) -> None:
        """Invalidate skills cache for a user, or all users if user_id is None."""
        if user_id:
            key = f"skills_cache:{user_id}"
            if self.client is not None:
                try:
                    self.client.delete(key)
                except Exception as e:
                    logger.warning(f"RedisCache delete error: {e}")
            with self._fallback_lock:
                self._in_memory_fallback.pop(key, None)
        else:
            if self.client is not None:
                try:
                    keys = self.client.keys("skills_cache:*")
                    if keys:
                        self.client.delete(*keys)
                except Exception as e:
                    logger.warning(f"RedisCache delete keys error: {e}")
            with self._fallback_lock:
                self._in_memory_fallback.clear()

    def _memory_get(self, key: str):
        with self._fallback_lock:
            entry = self._in_memory_fallback.get(key)
            if not entry:
                return None
            value, expires_at = entry
            if expires_at <= time.monotonic():
                self._in_memory_fallback.pop(key, None)
                return None
            return value

    def _memory_set(self, key: str, value, ttl: int) -> None:
        with self._fallback_lock:
            self._in_memory_fallback[key] = (value, time.monotonic() + ttl)

    def allow_request(
        self,
        user_id: str,
        limit: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ) -> bool:
        """Atomically allow at most `limit` requests per user and time window."""
        key = f"rate_limit:{user_id}:{int(time.time() // window_seconds)}"
        if self.client is not None:
            try:
                count = self.client.incr(key)
                if count == 1:
                    self.client.expire(key, window_seconds)
                return count <= limit
            except Exception as exc:
                logger.warning("Redis rate-limit error: %s", exc)

        current = self._memory_get(key) or 0
        if current >= limit:
            return False
        self._memory_set(key, current + 1, window_seconds)
        return True

    def claim_idempotency(self, key: str, ttl: int = IDEMPOTENCY_TTL_SECONDS) -> bool:
        """Claim an event key; return False when it has already been processed."""
        cache_key = f"idempotency:{key}"
        if self.client is not None:
            try:
                return bool(self.client.set(cache_key, "1", ex=ttl, nx=True))
            except Exception as exc:
                logger.warning("Redis idempotency error: %s", exc)

        with self._fallback_lock:
            entry = self._in_memory_fallback.get(cache_key)
            if entry and entry[1] > time.monotonic():
                return False
            self._in_memory_fallback[cache_key] = ("1", time.monotonic() + ttl)
            return True


def get_redis_cache() -> RedisCache:
    return RedisCache()
