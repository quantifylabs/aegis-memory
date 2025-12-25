"""
Aegis CLI Configuration Management

Handles loading/saving config files and credentials.
"""

import os
from pathlib import Path
from typing import Any

import yaml


def get_config_dir() -> Path:
    """Get the Aegis config directory."""
    config_dir = os.environ.get("AEGIS_CONFIG_DIR")
    if config_dir:
        return Path(config_dir)
    return Path.home() / ".aegis"


def get_config_path() -> Path:
    """Get the main config file path."""
    return get_config_dir() / "config.yaml"


def get_credentials_path() -> Path:
    """Get the credentials file path."""
    return get_config_dir() / "credentials"


def ensure_config_dir():
    """Ensure config directory exists with proper permissions."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    # Set directory permissions to owner only
    try:
        os.chmod(config_dir, 0o700)
    except OSError:
        pass  # Windows doesn't support chmod


def load_config() -> dict[str, Any]:
    """Load configuration from file."""
    config_path = get_config_path()

    if not config_path.exists():
        return get_default_config()

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
            return {**get_default_config(), **config}
    except Exception:
        return get_default_config()


def save_config(config: dict[str, Any]):
    """Save configuration to file."""
    ensure_config_dir()
    config_path = get_config_path()

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def load_credentials() -> dict[str, Any]:
    """Load credentials from file."""
    creds_path = get_credentials_path()

    if not creds_path.exists():
        return {"profiles": {}}

    try:
        with open(creds_path) as f:
            return yaml.safe_load(f) or {"profiles": {}}
    except Exception:
        return {"profiles": {}}


def save_credentials(credentials: dict[str, Any]):
    """Save credentials to file with restricted permissions."""
    ensure_config_dir()
    creds_path = get_credentials_path()

    with open(creds_path, "w") as f:
        yaml.dump(credentials, f, default_flow_style=False, sort_keys=False)

    # Set file permissions to owner only (chmod 600)
    try:
        os.chmod(creds_path, 0o600)
    except OSError:
        pass  # Windows doesn't support chmod


def get_default_config() -> dict[str, Any]:
    """Get default configuration."""
    return {
        "default_profile": "local",
        "profiles": {
            "local": {
                "api_url": "http://localhost:8000",
                "api_key_env": "AEGIS_API_KEY",
                "default_namespace": "default",
                "default_agent_id": "cli-user",
            }
        },
        "output": {
            "format": "table",
            "color": "auto",
        }
    }


def get_active_profile(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get the currently active profile configuration."""
    if config is None:
        config = load_config()

    # Check for environment override
    profile_name = os.environ.get("AEGIS_PROFILE", config.get("default_profile", "local"))
    profiles = config.get("profiles", {})

    if profile_name not in profiles:
        return get_default_config()["profiles"]["local"]

    return profiles[profile_name]


def get_profile_value(key: str, default: Any = None, config: dict[str, Any] | None = None) -> Any:
    """Get a value from the active profile with environment override."""
    env_map = {
        "api_url": "AEGIS_API_URL",
        "default_namespace": "AEGIS_NAMESPACE",
        "default_agent_id": "AEGIS_AGENT_ID",
    }

    # Check environment first
    if key in env_map and os.environ.get(env_map[key]):
        return os.environ[env_map[key]]

    profile = get_active_profile(config)
    return profile.get(key, default)


def set_nested_value(d: dict, keys: list, value: Any):
    """Set a nested dictionary value using a list of keys."""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def get_nested_value(d: dict, keys: list, default: Any = None) -> Any:
    """Get a nested dictionary value using a list of keys."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d
