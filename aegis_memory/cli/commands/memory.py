"""
Aegis CLI Memory Commands

Core memory operations: add, query, get, delete.
"""

import sys
import json
import typer
from typing import Optional, List
from pathlib import Path
from rich.console import Console

from aegis_memory.cli.utils.auth import get_client, get_default_namespace, get_default_agent_id
from aegis_memory.cli.utils.output import (
    print_json,
    print_success,
    print_error,
    print_memory,
    print_memories_table,
    confirm,
)
from aegis_memory.cli.utils.errors import wrap_errors, require_client, handle_api_error

console = Console()


@wrap_errors
def add(
    content: Optional[str] = typer.Argument(None, help="Memory content (or use --file)"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent ID"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="User ID"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Namespace"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope: agent-private, agent-shared, global"),
    memory_type: str = typer.Option("standard", "--type", "-t", help="Type: standard, strategy, reflection"),
    share_with: Optional[List[str]] = typer.Option(None, "--share-with", help="Agent IDs to share with"),
    metadata: Optional[str] = typer.Option(None, "--metadata", "-m", help="JSON metadata"),
    ttl: Optional[int] = typer.Option(None, "--ttl", help="TTL in seconds"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read content from file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Add a memory.
    
    Examples:
        aegis add "User prefers dark mode"
        aegis add "API pattern" -t strategy -s global
        aegis add -f ./insight.txt -t reflection
        echo "Piped content" | aegis add
    """
    client = require_client()
    
    # Get content from argument, file, or stdin
    if content:
        mem_content = content
    elif file:
        if not file.exists():
            print_error(f"File not found: {file}")
            raise typer.Exit(1)
        mem_content = file.read_text()
    elif not sys.stdin.isatty():
        mem_content = sys.stdin.read().strip()
    else:
        print_error("No content provided. Use argument, --file, or pipe content.")
        raise typer.Exit(1)
    
    if not mem_content.strip():
        print_error("Content cannot be empty")
        raise typer.Exit(1)
    
    # Parse metadata
    meta_dict = None
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON metadata: {e}")
            raise typer.Exit(1)
    
    # Build request
    resolved_namespace = namespace or get_default_namespace()
    resolved_agent = agent or get_default_agent_id()
    
    try:
        result = client.add(
            content=mem_content,
            agent_id=resolved_agent,
            user_id=user,
            namespace=resolved_namespace,
            scope=scope,
            metadata=meta_dict,
            ttl_seconds=ttl,
            shared_with_agents=share_with,
        )
        
        # Handle memory type by adding to metadata if not standard
        # Note: The add() method doesn't directly support memory_type,
        # but the server infers it. For explicit type, use delta endpoint.
        
    except Exception as e:
        handle_api_error(e, "add memory")
    
    if json_output:
        print_json({
            "id": result.id,
            "deduped_from": result.deduped_from,
            "inferred_scope": result.inferred_scope,
        })
        return
    
    if result.deduped_from:
        print_success(f"Memory deduplicated: {result.id}")
        console.print(f"  [dim]Already exists as: {result.deduped_from}[/dim]")
    else:
        print_success(f"Memory created: {result.id}")
        if result.inferred_scope:
            console.print(f"  [dim]Scope: {result.inferred_scope} (inferred)[/dim]")


@wrap_errors
def query(
    query_text: str = typer.Argument(..., help="Search query"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Requesting agent ID"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Namespace"),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Number of results"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum similarity score"),
    memory_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    cross_agent: Optional[List[str]] = typer.Option(None, "--cross-agent", "-x", help="Query across these agents"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    full: bool = typer.Option(False, "--full", help="Show full content"),
    ids_only: bool = typer.Option(False, "--ids-only", help="Print only memory IDs"),
):
    """
    Search memories semantically.
    
    Examples:
        aegis query "user preferences"
        aegis query "API patterns" -t strategy -k 5
        aegis query "current task" -x planner,coordinator
    """
    client = require_client()
    
    resolved_namespace = namespace or get_default_namespace()
    resolved_agent = agent or get_default_agent_id()
    
    import time
    start_time = time.time()
    
    try:
        if cross_agent:
            # Cross-agent query
            memories = client.query_cross_agent(
                query=query_text,
                requesting_agent_id=resolved_agent,
                target_agent_ids=cross_agent,
                namespace=resolved_namespace,
                top_k=top_k,
                min_score=min_score,
            )
        else:
            # Standard query
            memories = client.query(
                query=query_text,
                agent_id=resolved_agent,
                namespace=resolved_namespace,
                top_k=top_k,
                min_score=min_score,
            )
        
        query_time = (time.time() - start_time) * 1000
        
    except Exception as e:
        handle_api_error(e, "query memories")
    
    # Filter by type if specified
    if memory_type:
        memories = [m for m in memories if m.memory_type == memory_type]
    
    # IDs only output
    if ids_only:
        for mem in memories:
            console.print(mem.id)
        return
    
    # JSON output
    if json_output:
        print_json({
            "memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "agent_id": m.agent_id,
                    "memory_type": m.memory_type,
                    "scope": m.scope,
                    "score": m.score,
                    "metadata": m.metadata,
                    "bullet_helpful": m.bullet_helpful,
                    "bullet_harmful": m.bullet_harmful,
                    "created_at": str(m.created_at),
                }
                for m in memories
            ],
            "query_time_ms": query_time,
            "total": len(memories),
        })
        return
    
    # Pretty output
    if not memories:
        console.print(f"\n[dim]No memories found ({query_time:.0f}ms)[/dim]")
        return
    
    console.print(f"\n[bold]Found {len(memories)} memories[/bold] ({query_time:.0f}ms)")
    console.print("─" * 70)
    
    if full:
        for mem in memories:
            print_memory({
                "id": mem.id,
                "content": mem.content,
                "agent_id": mem.agent_id,
                "memory_type": mem.memory_type,
                "scope": mem.scope,
                "namespace": mem.namespace,
                "score": mem.score,
                "bullet_helpful": mem.bullet_helpful,
                "bullet_harmful": mem.bullet_harmful,
                "metadata": mem.metadata,
                "created_at": mem.created_at,
            }, full=True)
    else:
        print_memories_table(
            [
                {
                    "id": m.id,
                    "content": m.content,
                    "agent_id": m.agent_id,
                    "memory_type": m.memory_type,
                    "score": m.score,
                }
                for m in memories
            ],
            show_score=True,
        )


@wrap_errors
def get(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    content_only: bool = typer.Option(False, "--content-only", help="Print only content"),
):
    """
    Get a single memory by ID.
    
    Examples:
        aegis get 7f3a8b2c1d4e
        aegis get 7f3a8b2c1d4e --content-only | pbcopy
    """
    client = require_client()
    
    try:
        memory = client.get(memory_id)
    except Exception as e:
        handle_api_error(e, memory_id)
    
    # Content only
    if content_only:
        console.print(memory.content)
        return
    
    # JSON output
    if json_output:
        print_json({
            "id": memory.id,
            "content": memory.content,
            "agent_id": memory.agent_id,
            "user_id": memory.user_id,
            "namespace": memory.namespace,
            "memory_type": memory.memory_type,
            "scope": memory.scope,
            "shared_with_agents": memory.shared_with_agents,
            "derived_from_agents": memory.derived_from_agents,
            "metadata": memory.metadata,
            "bullet_helpful": memory.bullet_helpful,
            "bullet_harmful": memory.bullet_harmful,
            "created_at": str(memory.created_at),
        })
        return
    
    # Pretty output
    print_memory({
        "id": memory.id,
        "content": memory.content,
        "agent_id": memory.agent_id,
        "user_id": memory.user_id,
        "namespace": memory.namespace,
        "memory_type": memory.memory_type,
        "scope": memory.scope,
        "metadata": memory.metadata,
        "bullet_helpful": memory.bullet_helpful,
        "bullet_harmful": memory.bullet_harmful,
        "created_at": memory.created_at,
    }, full=True)


@wrap_errors  
def delete(
    memory_id: str = typer.Argument(..., help="Memory ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Delete a memory.
    
    Examples:
        aegis delete 7f3a8b2c1d4e
        aegis delete 7f3a8b2c1d4e -f
    """
    client = require_client()
    
    # Get memory first for confirmation
    if not force:
        try:
            memory = client.get(memory_id)
            
            content_preview = memory.content[:60] + "..." if len(memory.content) > 60 else memory.content
            
            console.print(f"\nDelete memory [bold]{memory_id}[/bold]?")
            console.print(f"  Content: \"{content_preview}\"")
            console.print(f"  Agent: {memory.agent_id or '-'}")
            
            if memory.bullet_helpful or memory.bullet_harmful:
                console.print(f"  Votes: +{memory.bullet_helpful}/-{memory.bullet_harmful}")
            
            if not confirm("\nConfirm deletion", default=False):
                console.print("[dim]Cancelled[/dim]")
                raise typer.Exit(0)
                
        except Exception as e:
            handle_api_error(e, memory_id)
    
    # Delete
    try:
        client.delete(memory_id)
    except Exception as e:
        handle_api_error(e, memory_id)
    
    if json_output:
        print_json({"deleted": memory_id})
        return
    
    print_success("Memory deleted")
