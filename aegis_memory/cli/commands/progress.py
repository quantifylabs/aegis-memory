"""
Aegis CLI Progress Commands

Session progress tracking - replacement for dashboard Session Inspector.
"""

import typer
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich import box

from aegis_memory.cli.utils.auth import get_client, get_default_namespace, get_default_agent_id
from aegis_memory.cli.utils.output import (
    print_json,
    print_success,
    print_error,
    print_table,
    print_progress_bar,
    format_time_ago,
)
from aegis_memory.cli.utils.errors import wrap_errors, require_client, handle_api_error

app = typer.Typer(help="Session progress tracking")
console = Console()


@app.command("list")
@wrap_errors
def list_sessions(
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Namespace"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    List all sessions.
    
    Shows progress overview for all tracked sessions.
    """
    client = require_client()
    ns = namespace or get_default_namespace()
    
    try:
        params = {"namespace": ns, "limit": 100}
        response = client.client.get("/memories/ace/dashboard/sessions", params=params)
        response.raise_for_status()
        data = response.json()
        sessions = data.get("sessions", [])
    except Exception as e:
        # Fallback: No dashboard endpoint, inform user
        console.print("[dim]Session list requires dashboard API endpoint[/dim]")
        console.print("[dim]Use 'aegis progress show <session-id>' to view specific sessions[/dim]")
        return
    
    # Filter by status
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    
    if json_output:
        print_json({"sessions": sessions})
        return
    
    if not sessions:
        console.print("\n[dim]No sessions found[/dim]")
        return
    
    # Pretty output
    console.print("\n[bold]Active Sessions[/bold]")
    console.print("─" * 70)
    
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Session")
    table.add_column("Agent")
    table.add_column("Progress")
    table.add_column("Status")
    table.add_column("Updated")
    
    for session in sessions:
        completed = session.get("completed_count", 0)
        total = session.get("total_items", 0) or completed
        pct = (completed / total * 100) if total > 0 else 0
        
        progress_str = f"{pct:.0f}% ({completed}/{total})"
        
        status_val = session.get("status", "unknown")
        if status_val == "completed":
            status_str = "[green]completed[/green]"
        elif status_val == "active":
            status_str = "[blue]active[/blue]"
        elif status_val == "failed":
            status_str = "[red]failed[/red]"
        else:
            status_str = f"[dim]{status_val}[/dim]"
        
        updated = session.get("updated_at", "")
        if updated:
            updated = format_time_ago(updated)
        
        table.add_row(
            session.get("session_id", "")[:20],
            session.get("agent_id", "-") or "-",
            progress_str,
            status_str,
            updated,
        )
    
    console.print(table)


@app.command("show")
@wrap_errors
def show_session(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Show session progress details.
    
    Displays completed items, current work, next up, and blockers.
    """
    client = require_client()
    
    try:
        session = client.get_session(session_id)
    except Exception as e:
        handle_api_error(e, session_id)
    
    if json_output:
        print_json({
            "id": session.id,
            "session_id": session.session_id,
            "status": session.status,
            "completed_count": session.completed_count,
            "total_items": session.total_items,
            "progress_percent": session.progress_percent,
            "completed_items": session.completed_items,
            "in_progress_item": session.in_progress_item,
            "next_items": session.next_items,
            "blocked_items": session.blocked_items,
            "summary": session.summary,
            "last_action": session.last_action,
            "updated_at": str(session.updated_at),
        })
        return
    
    # Pretty output
    console.print(f"\n[bold]Session:[/bold] {session.session_id}")
    console.print("─" * 40)
    
    # Status
    status_val = session.status
    if status_val == "completed":
        console.print(f"[bold]Status:[/bold]     [green]{status_val}[/green]")
    elif status_val == "active":
        console.print(f"[bold]Status:[/bold]     [blue]{status_val}[/blue]")
    elif status_val == "failed":
        console.print(f"[bold]Status:[/bold]     [red]{status_val}[/red]")
    else:
        console.print(f"[bold]Status:[/bold]     {status_val}")
    
    # Progress bar
    progress_bar = print_progress_bar(session.completed_count, session.total_items)
    console.print(f"[bold]Progress:[/bold]   {progress_bar}")
    
    # Summary
    if session.summary:
        console.print(f"\n[bold]Summary:[/bold]    {session.summary}")
    
    # Current
    if session.in_progress_item:
        console.print(f"[bold]Current:[/bold]    {session.in_progress_item}")
    
    # Last action
    if session.last_action:
        console.print(f"[bold]Last Action:[/bold] {session.last_action}")
    
    # Completed items
    if session.completed_items:
        console.print(f"\n[bold]Completed:[/bold]")
        for item in session.completed_items:
            console.print(f"  [green]✓[/green] {item}")
    
    # Next items
    if session.next_items:
        console.print(f"\n[bold]Next Up:[/bold]")
        for item in session.next_items:
            console.print(f"  [dim]○[/dim] {item}")
    
    # Blocked items
    if session.blocked_items:
        console.print(f"\n[bold]Blocked:[/bold]")
        for item in session.blocked_items:
            if isinstance(item, dict):
                console.print(f"  [yellow]⚠[/yellow] {item.get('item', 'unknown')} - {item.get('reason', 'no reason')}")
            else:
                console.print(f"  [yellow]⚠[/yellow] {item}")


@app.command("create")
@wrap_errors
def create_session(
    session_id: str = typer.Argument(..., help="Session ID"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent ID"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Namespace"),
    total: Optional[int] = typer.Option(None, "--total", "-t", help="Total items count"),
    summary: Optional[str] = typer.Option(None, "--summary", "-s", help="Initial summary"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Create a new session for progress tracking.
    
    Examples:
        aegis progress create build-dashboard -a coder
        aegis progress create api-refactor -s "Refactoring API endpoints"
    """
    client = require_client()
    
    resolved_agent = agent or get_default_agent_id()
    resolved_namespace = namespace or get_default_namespace()
    
    try:
        session = client.create_session(
            session_id=session_id,
            agent_id=resolved_agent,
            namespace=resolved_namespace,
        )
        
        # Update with summary if provided
        if summary or total:
            session = client.update_session(
                session_id=session_id,
                summary=summary,
                total_items=total,
            )
    except Exception as e:
        handle_api_error(e, session_id)
    
    if json_output:
        print_json({"session_id": session.session_id, "id": session.id})
        return
    
    print_success(f"Session created: {session.session_id}")


@app.command("update")
@wrap_errors
def update_session(
    session_id: str = typer.Argument(..., help="Session ID"),
    completed: Optional[List[str]] = typer.Option(None, "--completed", "-c", help="Mark item(s) complete"),
    in_progress: Optional[str] = typer.Option(None, "--in-progress", "-i", help="Set current item"),
    next_items: Optional[str] = typer.Option(None, "--next", help="Set next items (comma-separated)"),
    blocked: Optional[str] = typer.Option(None, "--blocked", "-b", help="Add blocked item (format: item:reason)"),
    summary: Optional[str] = typer.Option(None, "--summary", "-s", help="Update summary"),
    status: Optional[str] = typer.Option(None, "--status", help="Set status"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Update session progress.
    
    Examples:
        aegis progress update build-dashboard -c auth -i routing
        aegis progress update build-dashboard -b "payments:Waiting for API keys"
        aegis progress update build-dashboard --status completed
    """
    client = require_client()
    
    # Parse blocked item
    blocked_items = None
    if blocked:
        parts = blocked.split(":", 1)
        if len(parts) == 2:
            blocked_items = [{"item": parts[0], "reason": parts[1]}]
        else:
            blocked_items = [{"item": blocked, "reason": "No reason specified"}]
    
    # Parse next items
    next_list = None
    if next_items:
        next_list = [item.strip() for item in next_items.split(",")]
    
    try:
        session = client.update_session(
            session_id=session_id,
            completed_items=completed,
            in_progress_item=in_progress,
            next_items=next_list,
            blocked_items=blocked_items,
            summary=summary,
            status=status,
        )
    except Exception as e:
        handle_api_error(e, session_id)
    
    if json_output:
        print_json({
            "session_id": session.session_id,
            "progress_percent": session.progress_percent,
            "completed_count": session.completed_count,
            "total_items": session.total_items,
        })
        return
    
    print_success(f"Session updated: {session.session_id}")
    console.print(f"  Progress: {session.progress_percent:.0f}% ({session.completed_count}/{session.total_items})")
