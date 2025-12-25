"""
Aegis CLI Status Command

Check server health and connection status.
"""

import sys
import typer
from typing import Optional
from rich.console import Console
from rich.panel import Panel

from aegis_memory.cli.utils.auth import get_client, get_api_url
from aegis_memory.cli.utils.config import load_config, get_active_profile
from aegis_memory.cli.utils.output import print_json, print_error
from aegis_memory.cli.utils.errors import wrap_errors, ConnectionError

console = Console()


@wrap_errors
def status(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Exit code only, no output"),
):
    """
    Check server health and connection.
    
    Exit codes:
      0 - Server healthy
      1 - Server unhealthy or error
      2 - Connection failed
    """
    config = load_config()
    profile = get_active_profile(config)
    api_url = get_api_url(config)
    profile_name = config.get("default_profile", "local")
    
    try:
        client = get_client(config=config)
        if client is None:
            if quiet:
                sys.exit(1)
            print_error("No API key configured")
            raise typer.Exit(1)
        
        response = client.client.get("/health")
        response.raise_for_status()
        health = response.json()
        
    except Exception as e:
        if quiet:
            sys.exit(2)
        raise ConnectionError(api_url, str(e))
    
    # Determine overall status
    is_healthy = health.get("status") in ("healthy", "degraded")
    
    if quiet:
        sys.exit(0 if is_healthy else 1)
    
    if json_output:
        print_json({
            "status": health.get("status"),
            "version": health.get("version"),
            "database": health.get("database"),
            "embedding_model": health.get("embedding_model"),
            "api_url": api_url,
            "profile": profile_name,
        })
        return
    
    # Pretty output
    console.print("\n[bold]Aegis Memory Server[/bold]")
    console.print("─" * 35)
    
    status_str = health.get("status", "unknown")
    if status_str == "healthy":
        console.print(f"[bold]Status:[/bold]     [green]{status_str}[/green]")
    elif status_str == "degraded":
        console.print(f"[bold]Status:[/bold]     [yellow]{status_str}[/yellow]")
    else:
        console.print(f"[bold]Status:[/bold]     [red]{status_str}[/red]")
    
    console.print(f"[bold]Version:[/bold]    {health.get('version', 'unknown')}")
    
    # Database status
    db_status = health.get("database", "unknown")
    if db_status == "connected":
        console.print(f"[bold]Database:[/bold]   [green]{db_status}[/green]")
    else:
        console.print(f"[bold]Database:[/bold]   [red]{db_status}[/red]")
    
    # Embedding model
    embed_model = health.get("embedding_model", "unknown")
    console.print(f"[bold]Embeddings:[/bold] {embed_model}")
    
    # Features
    features = health.get("features", [])
    if features:
        console.print(f"[bold]Features:[/bold]   {', '.join(features)}")
    
    # Profile info
    console.print()
    console.print(f"[bold]Profile:[/bold]    {profile_name}")
    console.print(f"[bold]API URL:[/bold]    {api_url}")
    console.print(f"[bold]Namespace:[/bold]  {profile.get('default_namespace', 'default')}")
    
    if not is_healthy:
        raise typer.Exit(1)
