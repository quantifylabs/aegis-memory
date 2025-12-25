"""
Aegis CLI Vote Command

Vote on memory usefulness (helpful/harmful).
"""

import typer
from typing import Optional
from rich.console import Console

from aegis_memory.cli.utils.auth import get_client, get_default_agent_id
from aegis_memory.cli.utils.output import print_json, print_success, print_error
from aegis_memory.cli.utils.errors import wrap_errors, require_client, handle_api_error

console = Console()


@wrap_errors
def vote(
    memory_id: str = typer.Argument(..., help="Memory ID to vote on"),
    vote_type: str = typer.Argument(..., help="Vote type: helpful or harmful"),
    voter: Optional[str] = typer.Option(None, "--voter", "-v", help="Voting agent ID"),
    context: Optional[str] = typer.Option(None, "--context", "-c", help="Why this vote"),
    task: Optional[str] = typer.Option(None, "--task", "-t", help="Related task/feature ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Vote on memory usefulness.
    
    Track which memories help or harm task completion for self-improvement.
    
    Examples:
        aegis vote 7f3a8b2c1d4e helpful
        aegis vote 7f3a8b2c1d4e harmful -c "Caused infinite loop"
        aegis vote abc123 helpful -t feature-auth
    """
    # Validate vote type
    vote_type = vote_type.lower()
    if vote_type not in ("helpful", "harmful"):
        print_error("Vote must be 'helpful' or 'harmful'")
        raise typer.Exit(1)
    
    client = require_client()
    resolved_voter = voter or get_default_agent_id()
    
    try:
        result = client.vote(
            memory_id=memory_id,
            vote=vote_type,
            voter_agent_id=resolved_voter,
            context=context,
            task_id=task,
        )
    except Exception as e:
        handle_api_error(e, memory_id)
    
    if json_output:
        print_json({
            "memory_id": result.memory_id,
            "vote": vote_type,
            "bullet_helpful": result.bullet_helpful,
            "bullet_harmful": result.bullet_harmful,
            "effectiveness_score": result.effectiveness_score,
        })
        return
    
    # Pretty output
    print_success("Vote recorded")
    console.print(f"  [bold]Memory:[/bold]      {result.memory_id}")
    console.print(f"  [bold]Vote:[/bold]        {vote_type}")
    
    score_color = "green" if result.effectiveness_score >= 0 else "red"
    console.print(
        f"  [bold]New score:[/bold]   [{score_color}]{result.effectiveness_score:+.2f}[/{score_color}] "
        f"({result.bullet_helpful} helpful, {result.bullet_harmful} harmful)"
    )
