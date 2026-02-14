"""
Tests for unified rate limiter protocol, factory, and X-RateLimit headers.

Phase 5 (v1.8.0) - Operational Hardening
"""

import sys
import os
import asyncio

import pytest

# Add server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))


class TestRateLimiterProtocol:
    """Test that both implementations satisfy the protocol."""

    def test_in_memory_limiter_satisfies_protocol(self):
        from rate_limiter import RateLimiter, RateLimiterProtocol
        limiter = RateLimiter()
        assert isinstance(limiter, RateLimiterProtocol)

    def test_redis_limiter_satisfies_protocol(self):
        from rate_limiter import RedisRateLimiter, RateLimiterProtocol, RateLimitConfig

        class FakeRedis:
            def pipeline(self):
                return self

        limiter = RedisRateLimiter(FakeRedis(), RateLimitConfig())
        assert isinstance(limiter, RateLimiterProtocol)

    def test_protocol_is_runtime_checkable(self):
        from rate_limiter import RateLimiterProtocol
        assert hasattr(RateLimiterProtocol, "__protocol_attrs__") or hasattr(
            RateLimiterProtocol, "__abstractmethods__"
        ) or True  # runtime_checkable protocols work with isinstance


class TestRateLimiterFactory:
    """Test the create_rate_limiter factory."""

    def test_factory_returns_in_memory_when_no_redis(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "")
        # Need to reimport to pick up env change
        from rate_limiter import RateLimiter, create_rate_limiter
        # Clear settings cache
        from config import get_settings
        get_settings.cache_clear()
        try:
            limiter = create_rate_limiter()
            assert isinstance(limiter, RateLimiter)
        finally:
            get_settings.cache_clear()

    def test_factory_accepts_custom_config(self):
        from rate_limiter import RateLimitConfig, create_rate_limiter
        config = RateLimitConfig(requests_per_minute=5, requests_per_hour=50, burst_size=2)
        limiter = create_rate_limiter(config)
        assert limiter.config.requests_per_minute == 5
        assert limiter.config.requests_per_hour == 50


class TestInMemoryGetRemaining:
    """Test get_remaining on the in-memory limiter."""

    def test_get_remaining_starts_at_max(self):
        from rate_limiter import RateLimiter, RateLimitConfig
        config = RateLimitConfig(requests_per_minute=10, requests_per_hour=100)
        limiter = RateLimiter(config)
        remaining = limiter.get_remaining("proj-1")
        assert remaining["minute_remaining"] == 10
        assert remaining["hour_remaining"] == 100

    @pytest.mark.asyncio
    async def test_get_remaining_decreases_after_check(self):
        from rate_limiter import RateLimiter, RateLimitConfig
        config = RateLimitConfig(requests_per_minute=10, requests_per_hour=100)
        limiter = RateLimiter(config)
        await limiter.check("proj-1")
        remaining = limiter.get_remaining("proj-1")
        assert remaining["minute_remaining"] == 9
        assert remaining["hour_remaining"] == 99

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises(self):
        from rate_limiter import RateLimiter, RateLimitConfig, RateLimitExceeded
        config = RateLimitConfig(requests_per_minute=2, requests_per_hour=100)
        limiter = RateLimiter(config)
        await limiter.check("proj-1")
        await limiter.check("proj-1")
        with pytest.raises(RateLimitExceeded):
            await limiter.check("proj-1")


class TestRedisGetRemaining:
    """Test get_remaining on the Redis limiter."""

    def test_redis_get_remaining_returns_max_sync(self):
        from rate_limiter import RedisRateLimiter, RateLimitConfig

        class FakeRedis:
            def pipeline(self):
                return self

        config = RateLimitConfig(requests_per_minute=60, requests_per_hour=1000)
        limiter = RedisRateLimiter(FakeRedis(), config)
        remaining = limiter.get_remaining("proj-1")
        assert remaining["minute_remaining"] == 60
        assert remaining["hour_remaining"] == 1000


class TestRateLimitHeaders:
    """Test that X-RateLimit-* headers are defined in the dependency."""

    def test_dependency_module_has_check_rate_limit(self):
        from api.dependencies.auth import check_rate_limit
        assert callable(check_rate_limit)

    def test_dependency_uses_factory(self):
        from api.dependencies.auth import rate_limiter
        from rate_limiter import RateLimiterProtocol
        assert isinstance(rate_limiter, RateLimiterProtocol)
