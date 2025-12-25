"""
Aegis CLI Utilities

Helper modules for configuration, authentication, output formatting, and error handling.
"""

from aegis_memory.cli.utils.auth import get_api_key, get_client
from aegis_memory.cli.utils.config import (
    get_config_path,
    get_credentials_path,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)
from aegis_memory.cli.utils.errors import CLIError, handle_api_error
from aegis_memory.cli.utils.output import (
    print_error,
    print_json,
    print_memory,
    print_success,
    print_table,
    print_warning,
)

__all__ = [
    "load_config",
    "save_config",
    "get_config_path",
    "get_credentials_path",
    "load_credentials",
    "save_credentials",
    "get_client",
    "get_api_key",
    "print_table",
    "print_success",
    "print_error",
    "print_warning",
    "print_memory",
    "print_json",
    "handle_api_error",
    "CLIError",
]
