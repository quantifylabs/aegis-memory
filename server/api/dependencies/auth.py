"""Auth dependencies for API routers."""
from auth import get_project_id, AuthPolicy
from database import get_db
from fastapi import Depends, HTTPException, Response, status
from rate_limiter import RateLimitExceeded, create_rate_limiter

rate_limiter = create_rate_limiter()


async def check_rate_limit(
    response: Response,
    project_id: str = Depends(get_project_id),
):
    """Rate limit check as dependency. Injects X-RateLimit-* headers."""
    try:
        await rate_limiter.check(project_id)
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)},
        ) from e

    remaining = rate_limiter.get_remaining(project_id)
    response.headers["X-RateLimit-Limit-Minute"] = str(rate_limiter.config.requests_per_minute)
    response.headers["X-RateLimit-Remaining-Minute"] = str(remaining["minute_remaining"])
    response.headers["X-RateLimit-Limit-Hour"] = str(rate_limiter.config.requests_per_hour)
    response.headers["X-RateLimit-Remaining-Hour"] = str(remaining["hour_remaining"])
    return project_id


__all__ = ["get_project_id", "check_rate_limit", "AuthPolicy"]
