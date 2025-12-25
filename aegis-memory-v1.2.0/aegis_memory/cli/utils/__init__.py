"""
Aegis CLI Utilities

Helper modules for configuration, authentication, output formatting, and error handling.
"""

from aegis_memory.cli.utils.config import (
    load_config,
    save_config,
    get_config_path,
    get_credentials_path,
    load_credentials,
    save_credentials,
)
from aegis_memory.cli.utils.auth import get_client, get_api_key
from aegis_memory.cli.utils.output import (
    print_table,
    print_success,
    print_error,
    print_warning,
    print_memory,
    print_json,
)
from aegis_memory.cli.utils.errors import handle_api_error, CLIError

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
