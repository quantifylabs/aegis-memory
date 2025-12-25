"""
Aegis CLI Output Formatting

Rich-based output helpers for consistent terminal output.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich import box

console = Console()


def print_success(message: str):
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str, details: Optional[str] = None):
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")
    if details:
        console.print(f"  [dim]{details}[/dim]")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str):
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_json(data: Any):
    """Print JSON output."""
    if isinstance(data, str):
        console.print(data)
    else:
        formatted = json.dumps(data, indent=2, default=str)
        syntax = Syntax(formatted, "json", theme="monokai")
        console.print(syntax)


def print_table(
    columns: List[str],
    rows: List[List[Any]],
    title: Optional[str] = None,
    show_lines: bool = False,
):
    """Print a formatted table."""
    table = Table(
        title=title,
        box=box.ROUNDED if show_lines else box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
    )
    
    for col in columns:
        table.add_column(col)
    
    for row in rows:
        table.add_row(*[str(cell) if cell is not None else "" for cell in row])
    
    console.print(table)


def print_memory(memory: Dict[str, Any], full: bool = False):
    """Print a single memory with formatting."""
    content = memory.get("content", "")
    if not full and len(content) > 200:
        content = content[:200] + "..."
    
    # Header
    console.print(f"\n[bold]Memory:[/bold] {memory.get('id', 'unknown')}")
    console.print("─" * 40)
    
    # Content
    console.print(f"[bold]Content:[/bold]    {content}")
    console.print()
    
    # Metadata
    console.print(f"[bold]Type:[/bold]       {memory.get('memory_type', 'standard')}")
    console.print(f"[bold]Agent:[/bold]      {memory.get('agent_id', '-')}")
    console.print(f"[bold]Scope:[/bold]      {memory.get('scope', '-')}")
    console.print(f"[bold]Namespace:[/bold]  {memory.get('namespace', 'default')}")
    
    # Votes
    helpful = memory.get("bullet_helpful", 0)
    harmful = memory.get("bullet_harmful", 0)
    if helpful or harmful:
        total = helpful + harmful
        score = (helpful - harmful) / (total + 1) if total > 0 else 0
        console.print(f"\n[bold]Votes:[/bold]      +{helpful} helpful, -{harmful} harmful (score: {score:+.2f})")
    
    # Timestamps
    created = memory.get("created_at")
    if created:
        if isinstance(created, str):
            console.print(f"[bold]Created:[/bold]    {created}")
        else:
            console.print(f"[bold]Created:[/bold]    {created}")
    
    # Metadata
    metadata = memory.get("metadata", {})
    if metadata:
        console.print(f"\n[bold]Metadata:[/bold]")
        for key, value in metadata.items():
            console.print(f"  {key}: {value}")


def print_memories_table(
    memories: List[Dict[str, Any]],
    show_score: bool = True,
    truncate: int = 60,
):
    """Print memories as a table."""
    columns = []
    if show_score:
        columns.append("Score")
    columns.extend(["ID", "Agent", "Type", "Content"])
    
    rows = []
    for mem in memories:
        content = mem.get("content", "")
        if len(content) > truncate:
            content = content[:truncate] + "..."
        
        row = []
        if show_score:
            score = mem.get("score", 0)
            row.append(f"{score:.2f}" if score else "-")
        
        row.extend([
            mem.get("id", "")[:16],
            mem.get("agent_id", "-") or "-",
            mem.get("memory_type", "standard"),
            content,
        ])
        rows.append(row)
    
    print_table(columns, rows)


def print_progress_bar(
    completed: int,
    total: int,
    width: int = 30,
    label: str = "",
) -> str:
    """Create a text-based progress bar."""
    if total == 0:
        pct = 0
    else:
        pct = completed / total
    
    filled = int(width * pct)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    
    return f"{bar} {pct*100:.0f}% ({completed}/{total}) {label}"


def format_time_ago(dt: datetime) -> str:
    """Format datetime as 'X ago' string."""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt
    
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    else:
        days = int(seconds / 86400)
        return f"{days}d ago"


def confirm(message: str, default: bool = False) -> bool:
    """Ask for confirmation."""
    suffix = "[Y/n]" if default else "[y/N]"
    response = console.input(f"{message} {suffix} ").strip().lower()
    
    if not response:
        return default
    
    return response in ("y", "yes")
