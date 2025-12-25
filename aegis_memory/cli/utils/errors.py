"""
Aegis CLI Error Handling

Consistent error handling and user-friendly error messages.
"""

import sys
from typing import NoReturn

import httpx
from rich.console import Console

console = Console()


class CLIError(Exception):
    """Base CLI error with exit code."""

    def __init__(self, message: str, exit_code: int = 1, hint: str | None = None):
        self.message = message
        self.exit_code = exit_code
        self.hint = hint
        super().__init__(message)


class ConnectionError(CLIError):
    """Server connection error."""

    def __init__(self, url: str, details: str | None = None):
        hint = """Troubleshooting:
  1. Check if server is running: docker-compose ps
  2. Verify URL: aegis config show
  3. Check firewall/network settings"""

        message = f"Cannot connect to Aegis server\n  URL: {url}"
        if details:
            message += f"\n  Error: {details}"

        super().__init__(message, exit_code=2, hint=hint)


class AuthenticationError(CLIError):
    """Authentication failure."""

    def __init__(self, details: str | None = None):
        hint = """Fix:
  1. Check API key: aegis config show
  2. Update key: aegis config init
  3. Or set env: export AEGIS_API_KEY=<key>"""

        message = "Authentication failed"
        if details:
            message += f"\n  Error: {details}"

        super().__init__(message, exit_code=3, hint=hint)


class NotFoundError(CLIError):
    """Resource not found."""

    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} not found: {resource_id}"
        super().__init__(message, exit_code=4)


class ValidationError(CLIError):
    """Input validation error."""

    def __init__(self, message: str):
        super().__init__(f"Validation error\n  {message}", exit_code=5)


def handle_api_error(error: Exception, context: str = "") -> NoReturn:
    """
    Handle API errors and convert to user-friendly messages.

    Args:
        error: The caught exception
        context: Additional context about what operation failed
    """
    if isinstance(error, httpx.ConnectError):
        raise ConnectionError(
            url=str(getattr(error, 'request', {}).url if hasattr(error, 'request') else 'unknown'),
            details=str(error)
        )

    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code

        if status == 401:
            raise AuthenticationError("Invalid API key")
        elif status == 403:
            raise AuthenticationError("Access denied")
        elif status == 404:
            raise NotFoundError("Resource", context or "unknown")
        elif status == 422:
            # Validation error from FastAPI
            try:
                detail = error.response.json().get("detail", str(error))
                if isinstance(detail, list):
                    detail = "; ".join(d.get("msg", str(d)) for d in detail)
            except Exception:
                detail = str(error)
            raise ValidationError(detail)
        elif status == 429:
            raise CLIError(
                "Rate limit exceeded",
                hint="Wait a moment and try again, or check your usage limits."
            )
        else:
            try:
                detail = error.response.json().get("detail", str(error))
            except Exception:
                detail = str(error)
            raise CLIError(f"API error ({status}): {detail}")

    if isinstance(error, httpx.TimeoutException):
        raise CLIError(
            "Request timed out",
            hint="The server took too long to respond. Try again or check server health."
        )

    # Unknown error
    raise CLIError(f"Unexpected error: {str(error)}")


def exit_with_error(error: CLIError) -> NoReturn:
    """Print error and exit with appropriate code."""
    console.print(f"\n[red]✗[/red] {error.message}")

    if error.hint:
        console.print(f"\n[dim]{error.hint}[/dim]")

    sys.exit(error.exit_code)


def require_client():
    """Get client or exit with helpful error."""
    from aegis_memory.cli.utils.auth import get_client

    client = get_client()
    if client is None:
        raise AuthenticationError("No API key configured")

    return client


def wrap_errors(func):
    """Decorator to wrap function with error handling."""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CLIError as e:
            exit_with_error(e)
        except httpx.HTTPError as e:
            handle_api_error(e)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted[/dim]")
            sys.exit(130)
        except Exception as e:
            exit_with_error(CLIError(f"Unexpected error: {str(e)}"))

    return wrapper
