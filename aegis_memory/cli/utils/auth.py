"""
Aegis CLI Authentication

Handles API key resolution and client creation.
"""

import os
from typing import Optional

from aegis_memory import AegisClient
from aegis_memory.cli.utils.config import (
    load_config,
    load_credentials,
    get_active_profile,
    get_profile_value,
)


def get_api_key(config: Optional[dict] = None) -> Optional[str]:
    """
    Resolve API key using priority order:
    1. AEGIS_API_KEY environment variable
    2. Profile's api_key_env -> resolve that env var
    3. Profile's api_key in credentials file
    4. Return None (caller should handle)
    """
    # 1. Direct environment variable
    if os.environ.get("AEGIS_API_KEY"):
        return os.environ["AEGIS_API_KEY"]
    
    if config is None:
        config = load_config()
    
    profile = get_active_profile(config)
    profile_name = os.environ.get("AEGIS_PROFILE", config.get("default_profile", "local"))
    
    # 2. Profile's api_key_env -> resolve that env var
    api_key_env = profile.get("api_key_env")
    if api_key_env and os.environ.get(api_key_env):
        return os.environ[api_key_env]
    
    # 3. Credentials file
    credentials = load_credentials()
    profile_creds = credentials.get("profiles", {}).get(profile_name, {})
    if profile_creds.get("api_key"):
        return profile_creds["api_key"]
    
    # 4. Default dev key for local development
    if profile.get("api_url", "").startswith("http://localhost"):
        return "dev-key"
    
    return None


def get_api_url(config: Optional[dict] = None) -> str:
    """Get API URL from config or environment."""
    if os.environ.get("AEGIS_API_URL"):
        return os.environ["AEGIS_API_URL"]
    
    return get_profile_value("api_url", "http://localhost:8000", config)


def get_client(
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    config: Optional[dict] = None,
) -> Optional[AegisClient]:
    """
    Create an AegisClient with resolved configuration.
    
    Args:
        api_key: Override API key
        api_url: Override API URL
        config: Pre-loaded config dict
        
    Returns:
        AegisClient or None if authentication fails
    """
    if config is None:
        config = load_config()
    
    resolved_key = api_key or get_api_key(config)
    resolved_url = api_url or get_api_url(config)
    
    if not resolved_key:
        return None
    
    return AegisClient(
        api_key=resolved_key,
        base_url=resolved_url,
        timeout=30.0,
    )


def get_default_namespace(config: Optional[dict] = None) -> str:
    """Get default namespace from config or environment."""
    if os.environ.get("AEGIS_NAMESPACE"):
        return os.environ["AEGIS_NAMESPACE"]
    
    return get_profile_value("default_namespace", "default", config)


def get_default_agent_id(config: Optional[dict] = None) -> str:
    """Get default agent ID from config or environment."""
    if os.environ.get("AEGIS_AGENT_ID"):
        return os.environ["AEGIS_AGENT_ID"]
    
    return get_profile_value("default_agent_id", "cli-user", config)
