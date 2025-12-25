"""
Aegis CLI Playbook Command

Query playbook for strategies and reflections - replacement for Leaderboard.
"""

import typer
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich import box

from aegis_memory.cli.utils.auth import get_client, get_default_namespace, get_default_agent_id
from aegis_memory.cli.utils.output import print_json, print_error
from aegis_memory.cli.utils.errors import wrap_errors, require_client, handle_api_error

console = Console()


@wrap_errors
def playbook(
    query_text: str = typer.Argument(..., help="Search query"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent ID"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Namespace"),
    top_k: int = typer.Option(20, "--top-k", "-k", help="Number of results"),
    min_effectiveness: float = typer.Option(0.0, "--min-effectiveness", "-e", help="Minimum effectiveness score"),
    memory_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter: strategy, reflection, or both"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Query playbook for proven strategies and reflections.
    
    Returns entries ranked by semantic similarity and effectiveness score.
    Use before starting tasks to leverage accumulated knowledge.
    
    Examples:
        aegis playbook "API pagination"
        aegis playbook "error handling" -t strategy -e 0.5
        aegis playbook "database queries" -k 10 --json
    """
    client = require_client()
    
    resolved_agent = agent or get_default_agent_id()
    resolved_namespace = namespace or get_default_namespace()
    
    # Determine types to include
    include_types = ["strategy", "reflection"]
    if memory_type:
        if memory_type in ("strategy", "reflection"):
            include_types = [memory_type]
        elif memory_type != "both":
            print_error("Type must be 'strategy', 'reflection', or 'both'")
            raise typer.Exit(1)
    
    try:
        result = client.query_playbook(
            query=query_text,
            agent_id=resolved_agent,
            namespace=resolved_namespace,
            include_types=include_types,
            top_k=top_k,
            min_effectiveness=min_effectiveness,
        )
        entries = result.entries
        query_time = result.query_time_ms
    except Exception as e:
        handle_api_error(e, "query playbook")
    
    if json_output:
        print_json({
            "entries": [
                {
                    "id": e.id,
                    "content": e.content,
                    "memory_type": e.memory_type,
                    "effectiveness_score": e.effectiveness_score,
                    "bullet_helpful": e.bullet_helpful,
                    "bullet_harmful": e.bullet_harmful,
                    "error_pattern": e.error_pattern,
                    "created_at": str(e.created_at),
                }
                for e in entries
            ],
            "query_time_ms": query_time,
            "total": len(entries),
        })
        return
    
    if not entries:
        console.print(f"\n[dim]No playbook entries found ({query_time:.0f}ms)[/dim]")
        if min_effectiveness > 0:
            console.print(f"[dim]Try lowering --min-effectiveness (currently {min_effectiveness})[/dim]")
        return
    
    # Pretty output
    console.print(f"\n[bold]Playbook Results[/bold] ({len(entries)} entries, {query_time:.0f}ms)")
    console.print("─" * 75)
    
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Eff.", width=6, justify="right")
    table.add_column("Type", width=10)
    table.add_column("Content", width=55)
    
    for entry in entries:
        # Format effectiveness
        eff = entry.effectiveness_score
        if eff > 0.3:
            eff_str = f"[green]{eff:+.2f}[/green]"
        elif eff < -0.1:
            eff_str = f"[red]{eff:+.2f}[/red]"
        else:
            eff_str = f"{eff:+.2f}"
        
        # Format type
        if entry.memory_type == "reflection":
            type_str = "[yellow]reflection[/yellow]"
        else:
            type_str = "[blue]strategy[/blue]"
        
        # Truncate content
        content = entry.content
        if len(content) > 55:
            content = content[:52] + "..."
        
        table.add_row(eff_str, type_str, content)
    
    console.print(table)
    
    # Show top entry in full if exists
    if entries and len(entries[0].content) > 55:
        console.print(f"\n[bold]Top result (full):[/bold]")
        console.print(f"[dim]{entries[0].content}[/dim]")
