"""Focused tests for Redis-backed rate limiter boundaries."""

import pytest

from rate_limiter import RateLimitConfig, RateLimitExceeded, RedisRateLimiter


class FakePipeline:
    """Minimal async Redis pipeline stub used by RedisRateLimiter tests."""

    def __init__(self, minute_count: int, hour_count: int):
        self.minute_count = minute_count
        self.hour_count = hour_count

    def zremrangebyscore(self, *_args, **_kwargs):
        return self

    def zcard(self, key: str):
        if ":minute:" in key:
            self.minute_count = self.minute_count
        elif ":hour:" in key:
            self.hour_count = self.hour_count
        return self

    def zadd(self, *_args, **_kwargs):
        return self

    def expire(self, *_args, **_kwargs):
        return self

    async def execute(self):
        # Matches RedisRateLimiter expected result ordering.
        return [0, 0, self.minute_count, self.hour_count, 1, 1, 1, 1]


class FakeRedis:
    def __init__(self, minute_count: int, hour_count: int):
        self.minute_count = minute_count
        self.hour_count = hour_count

    def pipeline(self):
        return FakePipeline(minute_count=self.minute_count, hour_count=self.hour_count)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_count", "should_raise"),
    [
        (8, False),  # one below cap
        (9, False),  # exactly at cap after current request
        (10, True),  # one above cap with current request
    ],
)
async def test_redis_rate_limiter_minute_boundary(existing_count: int, should_raise: bool):
    limiter = RedisRateLimiter(
        redis_client=FakeRedis(minute_count=existing_count, hour_count=0),
        config=RateLimitConfig(requests_per_minute=10, requests_per_hour=100),
    )

    if should_raise:
        with pytest.raises(RateLimitExceeded, match="10/minute"):
            await limiter.check("project-minute")
    else:
        assert await limiter.check("project-minute") is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_count", "should_raise"),
    [
        (98, False),  # one below cap
        (99, False),  # exactly at cap after current request
        (100, True),  # one above cap with current request
    ],
)
async def test_redis_rate_limiter_hour_boundary(existing_count: int, should_raise: bool):
    limiter = RedisRateLimiter(
        redis_client=FakeRedis(minute_count=0, hour_count=existing_count),
        config=RateLimitConfig(requests_per_minute=10, requests_per_hour=100),
    )

    if should_raise:
        with pytest.raises(RateLimitExceeded, match="100/hour"):
            await limiter.check("project-hour")
    else:
        assert await limiter.check("project-hour") is True
