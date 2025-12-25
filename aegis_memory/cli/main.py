"""
Aegis CLI Main Application

Entry point for all CLI commands.
"""


import typer
from rich.console import Console

from aegis_memory.cli.commands import (
    config_app,
    export_import,
    features,
    memory,
    playbook,
    progress,
    stats,
    status,
    vote,
)

# Create main app
app = typer.Typer(
    name="aegis",
    help="Aegis Memory CLI - The memory engine for multi-agent systems",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Register command groups
app.add_typer(config_app, name="config", help="Configuration management")
app.add_typer(progress.app, name="progress", help="Session progress tracking")
app.add_typer(features.app, name="features", help="Feature tracking")

# Register standalone commands
app.command(name="status", help="Check server health and connection")(status.status)
app.command(name="stats", help="Show namespace statistics")(stats.stats)
app.command(name="add", help="Add a memory")(memory.add)
app.command(name="query", help="Search memories semantically")(memory.query)
app.command(name="get", help="Get a single memory by ID")(memory.get)
app.command(name="delete", help="Delete a memory")(memory.delete)
app.command(name="vote", help="Vote on memory usefulness")(vote.vote)
app.command(name="playbook", help="Query playbook for strategies")(playbook.playbook)
app.command(name="export", help="Export memories to file")(export_import.export)
app.command(name="import", help="Import memories from file")(export_import.import_memories)


@app.command()
def version():
    """Show version information."""
    from aegis_memory import __version__
    from aegis_memory.cli.utils.auth import get_client
    from aegis_memory.cli.utils.config import load_config

    console.print(f"[bold]aegis-cli[/bold] {__version__}")
    console.print(f"[bold]aegis-memory SDK[/bold] {__version__}")

    import sys
    console.print(f"[bold]Python[/bold] {sys.version.split()[0]}")

    # Try to get server version
    try:
        config = load_config()
        profile = config.get("profiles", {}).get(config.get("default_profile", "local"), {})
        console.print(f"\n[bold]Server:[/bold] {profile.get('api_url', 'not configured')}")

        client = get_client()
        if client:
            health = client.client.get("/health").json()
            console.print(f"[bold]Server version:[/bold] {health.get('version', 'unknown')}")
    except Exception:
        console.print("[dim]Server: not connected[/dim]")


def main():
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
