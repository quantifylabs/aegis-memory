"""
Aegis CLI Config Command

Configuration management: init, show, set, use profiles.
"""


import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from aegis_memory.cli.utils.auth import get_api_key, get_client
from aegis_memory.cli.utils.config import (
    get_active_profile,
    get_config_path,
    get_credentials_path,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
    set_nested_value,
)
from aegis_memory.cli.utils.output import print_error, print_success, print_warning

app = typer.Typer(help="Configuration management")
console = Console()


@app.command()
def init(
    non_interactive: bool = typer.Option(False, "--non-interactive", "-y", help="Use defaults without prompting"),
):
    """
    Interactive first-run setup.

    Creates configuration and credentials files.
    """
    console.print("\n[bold]Welcome to Aegis Memory CLI![/bold]\n")

    config = load_config()
    credentials = load_credentials()

    if non_interactive:
        # Use defaults
        api_url = "http://localhost:8000"
        api_key = "dev-key"
        namespace = "default"
        agent_id = "cli-user"
    else:
        # Interactive prompts
        api_url = Prompt.ask(
            "Server URL",
            default="http://localhost:8000"
        )

        api_key = Prompt.ask(
            "API Key",
            password=True,
            default="dev-key"
        )

        namespace = Prompt.ask(
            "Default namespace",
            default="default"
        )

        agent_id = Prompt.ask(
            "Default agent ID",
            default="cli-user"
        )

    # Update config
    config["profiles"]["local"] = {
        "api_url": api_url,
        "api_key_env": "AEGIS_API_KEY",
        "default_namespace": namespace,
        "default_agent_id": agent_id,
    }
    config["default_profile"] = "local"

    # Update credentials
    if "profiles" not in credentials:
        credentials["profiles"] = {}
    credentials["profiles"]["local"] = {"api_key": api_key}

    # Save
    save_config(config)
    save_credentials(credentials)

    print_success(f"Configuration saved to {get_config_path()}")
    print_success(f"Credentials saved to {get_credentials_path()}")

    # Test connection
    if not non_interactive:
        if Confirm.ask("\nTest connection?", default=True):
            _test_connection()
    else:
        _test_connection()


def _test_connection():
    """Test connection to server."""
    try:
        client = get_client()
        if client is None:
            print_error("No API key configured")
            return

        response = client.client.get("/health")
        response.raise_for_status()
        health = response.json()

        version = health.get("version", "unknown")
        status = health.get("status", "unknown")

        if status == "healthy":
            print_success(f"Connected to Aegis v{version} ({status})")
        else:
            print_warning(f"Connected to Aegis v{version} ({status})")

    except Exception as e:
        print_error(f"Connection failed: {str(e)}")


@app.command()
def show():
    """Show current configuration."""
    config = load_config()
    profile_name = config.get("default_profile", "local")
    profile = get_active_profile(config)

    console.print(f"\n[bold]Profile:[/bold] {profile_name} (active)")
    console.print(f"[bold]API URL:[/bold] {profile.get('api_url', 'not set')}")
    console.print(f"[bold]Namespace:[/bold] {profile.get('default_namespace', 'default')}")
    console.print(f"[bold]Agent ID:[/bold] {profile.get('default_agent_id', 'cli-user')}")

    output_config = config.get("output", {})
    console.print(f"[bold]Output:[/bold] {output_config.get('format', 'table')}")

    # Show API key status (masked)
    api_key = get_api_key(config)
    if api_key:
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
        console.print(f"[bold]API Key:[/bold] {masked}")
    else:
        console.print("[bold]API Key:[/bold] [red]not configured[/red]")

    console.print(f"\n[dim]Config: {get_config_path()}[/dim]")


@app.command("set")
def set_value(
    key: str = typer.Argument(..., help="Config key (e.g., profiles.local.api_url)"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a configuration value."""
    config = load_config()

    keys = key.split(".")
    set_nested_value(config, keys, value)
    save_config(config)

    print_success(f"Set {key} = {value}")


@app.command()
def use(
    profile: str = typer.Argument(..., help="Profile name to switch to"),
):
    """Switch to a different profile."""
    config = load_config()

    if profile not in config.get("profiles", {}):
        print_error(f"Profile '{profile}' not found")
        console.print("\nAvailable profiles:")
        for name in config.get("profiles", {}).keys():
            console.print(f"  - {name}")
        raise typer.Exit(1)

    config["default_profile"] = profile
    save_config(config)

    print_success(f"Switched to profile: {profile}")


@app.command()
def profiles():
    """List all configured profiles."""
    config = load_config()
    current = config.get("default_profile", "local")

    console.print("\n[bold]Configured Profiles[/bold]\n")

    for name, profile in config.get("profiles", {}).items():
        marker = "[green]●[/green]" if name == current else "[dim]○[/dim]"
        console.print(f"  {marker} {name}")
        console.print(f"      URL: {profile.get('api_url', 'not set')}")
        console.print(f"      Namespace: {profile.get('default_namespace', 'default')}")
        console.print()


@app.command()
def path():
    """Show configuration file paths."""
    console.print(f"[bold]Config:[/bold] {get_config_path()}")
    console.print(f"[bold]Credentials:[/bold] {get_credentials_path()}")
