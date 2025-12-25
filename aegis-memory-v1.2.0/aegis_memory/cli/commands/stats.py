"""
Aegis CLI Stats Command

Show namespace statistics - replacement for dashboard Overview.
"""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich import box

from aegis_memory.cli.utils.auth import get_client, get_default_namespace
from aegis_memory.cli.utils.output import print_json, print_error
from aegis_memory.cli.utils.errors import wrap_errors, require_client

console = Console()


@wrap_errors
def stats(
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Namespace to query"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Filter by agent ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Show namespace statistics.
    
    Displays memory counts, vote summaries, session info, and feature status.
    """
    client = require_client()
    ns = namespace or get_default_namespace()
    
    # Fetch stats from dashboard endpoint
    params = {"namespace": ns}
    if agent:
        params["agent_id"] = agent
    
    try:
        response = client.client.get("/memories/ace/dashboard/stats", params=params)
        response.raise_for_status()
        stats_data = response.json()
    except Exception:
        # Fallback: construct stats from individual calls
        stats_data = _build_stats_fallback(client, ns, agent)
    
    if json_output:
        print_json(stats_data)
        return
    
    # Pretty output
    console.print(f"\n[bold]Namespace:[/bold] {ns}")
    if agent:
        console.print(f"[bold]Agent:[/bold] {agent}")
    console.print("─" * 35)
    
    # Memory counts
    total = stats_data.get("total_memories", 0)
    console.print(f"\n[bold]Total Memories:[/bold]     {total:,}")
    
    by_type = stats_data.get("by_type", {})
    if by_type:
        console.print(f"  Standard:         {by_type.get('standard', 0):,}")
        console.print(f"  Reflections:      {by_type.get('reflection', 0):,}")
        console.print(f"  Strategies:       {by_type.get('strategy', 0):,}")
    
    # Session info
    sessions = stats_data.get("active_sessions", 0)
    console.print(f"\n[bold]Active Sessions:[/bold]    {sessions}")
    
    # Feature summary
    features = stats_data.get("features", {})
    if features:
        total_f = features.get("total", 0)
        passing = features.get("passing", 0)
        failing = features.get("failing", 0)
        in_progress = features.get("in_progress", 0)
        
        console.print(f"[bold]Features:[/bold]           {total_f} total")
        console.print(f"  [green]✓[/green] Passing:        {passing}")
        console.print(f"  [yellow]●[/yellow] In Progress:    {in_progress}")
        console.print(f"  [red]✗[/red] Failing:        {failing}")
    
    # Vote summary
    votes = stats_data.get("votes", {})
    if votes:
        helpful = votes.get("helpful", 0)
        harmful = votes.get("harmful", 0)
        net = helpful - harmful
        
        console.print(f"\n[bold]Vote Summary:[/bold]")
        console.print(f"  Helpful:          {helpful:,}")
        console.print(f"  Harmful:          {harmful:,}")
        console.print(f"  Net Score:        {'+' if net >= 0 else ''}{net:,}")
    
    # Top agents
    top_agents = stats_data.get("top_agents", [])
    if top_agents:
        console.print(f"\n[bold]Top Agents:[/bold]")
        for agent_info in top_agents[:5]:
            name = agent_info.get("agent_id", "unknown")
            count = agent_info.get("memory_count", 0)
            console.print(f"  {name:20} {count:,} memories")
    
    # Eval metrics (basic)
    eval_metrics = stats_data.get("eval", {})
    if eval_metrics:
        success_rate = eval_metrics.get("success_rate", 0)
        precision = eval_metrics.get("retrieval_precision", 0)
        
        console.print(f"\n[bold]Performance:[/bold]")
        console.print(f"  Success Rate:     {success_rate*100:.1f}%")
        console.print(f"  Precision:        {precision*100:.1f}%")


def _build_stats_fallback(client, namespace: str, agent: Optional[str]) -> dict:
    """Build stats from individual API calls if dashboard endpoint unavailable."""
    stats = {
        "total_memories": 0,
        "by_type": {},
        "active_sessions": 0,
        "features": {},
        "votes": {"helpful": 0, "harmful": 0},
        "top_agents": [],
    }
    
    try:
        # Try to get eval metrics
        params = {"namespace": namespace, "window": "global"}
        if agent:
            params["agent_id"] = agent
            
        response = client.client.get("/memories/ace/eval/metrics", params=params)
        if response.status_code == 200:
            metrics = response.json()
            stats["total_memories"] = metrics.get("total_memories", 0)
            stats["votes"]["helpful"] = metrics.get("helpful_votes", 0)
            stats["votes"]["harmful"] = metrics.get("harmful_votes", 0)
            stats["eval"] = {
                "success_rate": metrics.get("success_rate", 0),
                "retrieval_precision": metrics.get("retrieval_precision", 0),
            }
            stats["features"] = {
                "total": metrics.get("total_tasks", 0),
                "passing": metrics.get("passing_tasks", 0),
            }
    except Exception:
        pass
    
    try:
        # Get feature list
        response = client.client.get("/memories/ace/features", params={"namespace": namespace})
        if response.status_code == 200:
            features = response.json()
            stats["features"] = {
                "total": features.get("total", 0),
                "passing": features.get("passing", 0),
                "failing": features.get("failing", 0),
                "in_progress": features.get("in_progress", 0),
            }
    except Exception:
        pass
    
    return stats
