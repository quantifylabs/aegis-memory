"""Interactive memory exploration command."""

import typer
from rich.console import Console
from rich.table import Table

from aegis_memory.cli.utils.auth import get_default_agent_id, get_default_namespace
from aegis_memory.cli.utils.errors import require_client, wrap_errors

console = Console()


@wrap_errors
def explore(
    query: str = typer.Option("", "--query", "-q", help="Initial query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
):
    """Browse memories interactively from the terminal."""
    client = require_client()
    agent = get_default_agent_id()
    namespace = get_default_namespace()

    console.print("[bold]Aegis Memory Explorer[/bold]")
    console.print("Type a query and press Enter (`exit` to quit).\n")

    current = query
    while True:
        if not current:
            current = typer.prompt("Explore")
        if current.strip().lower() in {"exit", "quit", "q"}:
            console.print("[dim]Bye![/dim]")
            break

        memories = client.query(
            query=current,
            agent_id=agent,
            namespace=namespace,
            top_k=top_k,
        )

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim", width=14)
        table.add_column("Score", width=7)
        table.add_column("Content")

        for m in memories:
            table.add_row(m.id[:12], f"{(m.score or 0):.2f}", (m.content or "")[:120])

        if memories:
            console.print(table)
        else:
            console.print("[dim]No results found.[/dim]")

        current = ""
