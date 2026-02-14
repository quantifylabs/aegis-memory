"""Rate limiting dependency for API routers."""
from api.dependencies.auth import check_rate_limit, rate_limiter

__all__ = ["check_rate_limit", "rate_limiter"]
