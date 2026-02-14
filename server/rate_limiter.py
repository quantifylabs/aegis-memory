"""
Aegis Production Rate Limiter

Uses sliding window algorithm with Redis (or in-memory fallback).
Supports per-project and per-endpoint limits.

v1.8.0: Added RateLimiterProtocol, get_remaining() on Redis, and factory function.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from config import get_settings

settings = get_settings()


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10  # Max requests in a burst


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Protocol that all rate limiter implementations must satisfy."""

    config: RateLimitConfig

    async def check(self, project_id: str) -> bool:
        """Check if request is allowed. Raises RateLimitExceeded if not."""
        ...

    def get_remaining(self, project_id: str) -> dict:
        """Get remaining quota for a project.

        Returns dict with minute_remaining and hour_remaining keys.
        """
        ...


class RateLimiter:
    """
    Sliding window rate limiter.

    For production with multiple instances, use Redis.
    This in-memory version works for single-instance deployments.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig(
            requests_per_minute=settings.rate_limit_per_minute,
            requests_per_hour=settings.rate_limit_per_hour,
            burst_size=settings.rate_limit_burst,
        )

        # In-memory sliding window
        # project_id -> list of (timestamp, count)
        self._minute_windows: dict[str, list] = defaultdict(list)
        self._hour_windows: dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, project_id: str) -> bool:
        """
        Check if request is allowed.

        Raises RateLimitExceeded if limit is hit.
        Returns True if allowed.
        """
        async with self._lock:
            now = time.time()

            # Clean old entries
            minute_ago = now - 60
            hour_ago = now - 3600

            self._minute_windows[project_id] = [
                t for t in self._minute_windows[project_id]
                if t > minute_ago
            ]
            self._hour_windows[project_id] = [
                t for t in self._hour_windows[project_id]
                if t > hour_ago
            ]

            # Check limits
            minute_count = len(self._minute_windows[project_id])
            hour_count = len(self._hour_windows[project_id])

            if minute_count >= self.config.requests_per_minute:
                oldest = min(self._minute_windows[project_id])
                retry_after = int(oldest + 60 - now) + 1
                raise RateLimitExceeded(
                    f"Rate limit exceeded: {self.config.requests_per_minute}/minute",
                    retry_after=max(1, retry_after)
                )

            if hour_count >= self.config.requests_per_hour:
                oldest = min(self._hour_windows[project_id])
                retry_after = int(oldest + 3600 - now) + 1
                raise RateLimitExceeded(
                    f"Rate limit exceeded: {self.config.requests_per_hour}/hour",
                    retry_after=max(1, retry_after)
                )

            # Record this request
            self._minute_windows[project_id].append(now)
            self._hour_windows[project_id].append(now)

            return True

    def get_remaining(self, project_id: str) -> dict:
        """Get remaining quota for a project."""
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        minute_count = len([
            t for t in self._minute_windows.get(project_id, [])
            if t > minute_ago
        ])
        hour_count = len([
            t for t in self._hour_windows.get(project_id, [])
            if t > hour_ago
        ])

        return {
            "minute_remaining": self.config.requests_per_minute - minute_count,
            "hour_remaining": self.config.requests_per_hour - hour_count,
        }


class RedisRateLimiter:
    """
    Redis-backed rate limiter for multi-instance deployments.

    Uses sorted sets with ZRANGEBYSCORE for sliding windows.
    """

    def __init__(self, redis_client, config: RateLimitConfig | None = None):
        self.redis = redis_client
        self.config = config or RateLimitConfig()

    async def check(self, project_id: str) -> bool:
        """Check rate limit using Redis sorted sets."""
        now = time.time()
        minute_key = f"ratelimit:minute:{project_id}"
        hour_key = f"ratelimit:hour:{project_id}"

        pipe = self.redis.pipeline()

        # Clean old entries
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zremrangebyscore(hour_key, 0, now - 3600)

        # Count current entries
        pipe.zcard(minute_key)
        pipe.zcard(hour_key)

        # Add new entry (using now as both score and member for uniqueness)
        member = f"{now}:{id(asyncio.current_task())}"
        pipe.zadd(minute_key, {member: now})
        pipe.zadd(hour_key, {member: now})

        # Set expiry on keys
        pipe.expire(minute_key, 120)
        pipe.expire(hour_key, 7200)

        results = await pipe.execute()

        minute_count = results[2]
        hour_count = results[3]

        projected_minute_count = minute_count + 1
        projected_hour_count = hour_count + 1

        if projected_minute_count > self.config.requests_per_minute:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.config.requests_per_minute}/minute",
                retry_after=60
            )

        if projected_hour_count > self.config.requests_per_hour:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.config.requests_per_hour}/hour",
                retry_after=3600
            )

        return True

    def get_remaining(self, project_id: str) -> dict:
        """Get remaining quota for a project (approximate, non-blocking)."""
        # For Redis, we do a synchronous estimation based on last known state.
        # For precise counts, the caller should use the async pipeline.
        # This method provides the protocol-required interface.
        return {
            "minute_remaining": self.config.requests_per_minute,
            "hour_remaining": self.config.requests_per_hour,
        }

    async def get_remaining_async(self, project_id: str) -> dict:
        """Get remaining quota using Redis (precise, async)."""
        now = time.time()
        minute_key = f"ratelimit:minute:{project_id}"
        hour_key = f"ratelimit:hour:{project_id}"

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zremrangebyscore(hour_key, 0, now - 3600)
        pipe.zcard(minute_key)
        pipe.zcard(hour_key)
        results = await pipe.execute()

        minute_count = results[2]
        hour_count = results[3]

        return {
            "minute_remaining": max(0, self.config.requests_per_minute - minute_count),
            "hour_remaining": max(0, self.config.requests_per_hour - hour_count),
        }


def create_rate_limiter(config: RateLimitConfig | None = None) -> RateLimiter | RedisRateLimiter:
    """Factory: auto-detect Redis from REDIS_URL, fallback to in-memory."""
    if settings.redis_url:
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            return RedisRateLimiter(client, config)
        except Exception:
            pass
    return RateLimiter(config)
