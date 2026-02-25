"""Auth dependencies for API routers."""

from dataclasses import dataclass

from auth import get_project_id, AuthPolicy, TokenVerifier
from config import get_settings
from database import get_db
from fastapi import Depends, HTTPException, Request, Response, status
from rate_limiter import RateLimitExceeded, create_rate_limiter

rate_limiter = create_rate_limiter()
settings = get_settings()


@dataclass
class AuthContext:
    """Full authentication context including trust level and agent binding."""
    project_id: str
    trust_level: str = "internal"
    bound_agent_id: str | None = None
    auth_method: str = "legacy"
    key_id: str | None = None


async def get_auth_context(request: Request) -> AuthContext:
    """
    FastAPI dependency: extract full auth context from bearer token.

    New routers that need trust_level or agent binding should depend on this.
    Existing routers continue using check_rate_limit() which returns project_id str.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
        )
    token = auth[7:].strip()

    if settings.enable_project_auth:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await TokenVerifier.verify(token, db)
    else:
        result = TokenVerifier._verify_legacy_key(token)

    return AuthContext(
        project_id=result["project_id"],
        trust_level=result.get("trust_level", "internal"),
        bound_agent_id=result.get("bound_agent_id"),
        auth_method=result.get("auth_method", "legacy"),
        key_id=result.get("key_id"),
    )


def enforce_agent_binding(auth: AuthContext, request_agent_id: str | None):
    """
    If the API key is bound to a specific agent_id, ensure the request
    is coming from that agent. Prevents agent ID spoofing.

    Only enforced when bound_agent_id is set on the API key.
    Unbound keys (bound_agent_id=None) allow any agent_id.
    """
    if auth.bound_agent_id and request_agent_id and request_agent_id != auth.bound_agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent ID mismatch: API key is bound to '{auth.bound_agent_id}' "
                   f"but request claims agent_id='{request_agent_id}'",
        )


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


__all__ = ["get_project_id", "check_rate_limit", "AuthPolicy", "AuthContext", "get_auth_context", "enforce_agent_binding"]
