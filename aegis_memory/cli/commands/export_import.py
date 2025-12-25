"""
Aegis CLI Export/Import Commands

Data export and import for backup and migration.
"""

import json
import sys
import typer
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from aegis_memory.cli.utils.auth import get_client, get_default_namespace
from aegis_memory.cli.utils.output import print_json, print_success, print_error
from aegis_memory.cli.utils.errors import wrap_errors, require_client, handle_api_error

console = Console()


@wrap_errors
def export(
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Filter by namespace (default: all)"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Filter by agent ID"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Format: jsonl or json"),
    include_embeddings: bool = typer.Option(False, "--include-embeddings", help="Include embedding vectors"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max memories to export"),
):
    """
    Export memories for backup or migration.
    
    Examples:
        aegis export > backup.jsonl
        aegis export -o backup.jsonl
        aegis export -n production -f json -o prod-backup.json
        aegis export --include-embeddings -o full-backup.jsonl
    """
    if format not in ("jsonl", "json"):
        print_error("Format must be 'jsonl' or 'json'")
        raise typer.Exit(1)
    
    client = require_client()
    
    # Build request
    params = {"format": format}
    if namespace:
        params["namespace"] = namespace
    if agent:
        params["agent_id"] = agent
    if include_embeddings:
        params["include_embeddings"] = True
    if limit:
        params["limit"] = limit
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description="Exporting memories...", total=None)
        
        try:
            response = client.client.post("/memories/export", json=params)
            response.raise_for_status()
        except Exception as e:
            handle_api_error(e, "export")
    
    # Handle output
    if format == "jsonl":
        # Streaming response
        content = response.text
        lines = content.strip().split("\n") if content.strip() else []
        count = len(lines)
        
        if output:
            output.write_text(content)
            print_success(f"Exported {count} memories to {output}")
        else:
            # Output to stdout
            console.print(content, end="")
            if sys.stdout.isatty():
                console.print(f"\n[dim]Exported {count} memories[/dim]", err=True)
    else:
        # JSON response
        data = response.json()
        memories = data.get("memories", [])
        count = len(memories)
        
        if output:
            with open(output, "w") as f:
                json.dump(data, f, indent=2, default=str)
            print_success(f"Exported {count} memories to {output}")
        else:
            console.print(json.dumps(data, indent=2, default=str))
            if sys.stdout.isatty():
                console.print(f"\n[dim]Exported {count} memories[/dim]", err=True)


@wrap_errors
def import_memories(
    file: Path = typer.Argument(..., help="File to import from"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Override namespace"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Override agent ID"),
    skip_duplicates: bool = typer.Option(True, "--skip-duplicates/--no-skip-duplicates", help="Skip content duplicates"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without importing"),
):
    """
    Import memories from export file.
    
    Examples:
        aegis import backup.jsonl
        aegis import backup.json -n staging
        aegis import backup.jsonl --dry-run
    """
    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)
    
    client = require_client()
    
    # Detect format
    content = file.read_text()
    
    if file.suffix == ".json" or content.strip().startswith("{"):
        # JSON format
        try:
            data = json.loads(content)
            memories = data.get("memories", [])
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON: {e}")
            raise typer.Exit(1)
    else:
        # JSONL format
        memories = []
        for line in content.strip().split("\n"):
            if line.strip():
                try:
                    memories.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print_error(f"Invalid JSONL line: {e}")
                    raise typer.Exit(1)
    
    if not memories:
        print_error("No memories found in file")
        raise typer.Exit(1)
    
    if dry_run:
        console.print(f"\n[bold]Dry run[/bold] - would import {len(memories)} memories")
        
        # Show sample
        if memories:
            sample = memories[0]
            console.print(f"\nSample memory:")
            console.print(f"  Content: {sample.get('content', '')[:60]}...")
            console.print(f"  Agent: {namespace or sample.get('agent_id', '-')}")
            console.print(f"  Namespace: {agent or sample.get('namespace', 'default')}")
        
        return
    
    # Import memories
    imported = 0
    skipped = 0
    errors = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(description="Importing...", total=len(memories))
        
        for mem in memories:
            try:
                # Override namespace/agent if specified
                mem_namespace = namespace or mem.get("namespace", "default")
                mem_agent = agent or mem.get("agent_id")
                
                result = client.add(
                    content=mem.get("content", ""),
                    agent_id=mem_agent,
                    user_id=mem.get("user_id"),
                    namespace=mem_namespace,
                    scope=mem.get("scope"),
                    metadata=mem.get("metadata"),
                )
                
                if result.deduped_from and skip_duplicates:
                    skipped += 1
                else:
                    imported += 1
                    
            except Exception as e:
                errors += 1
            
            progress.update(task, advance=1)
    
    # Summary
    print_success(f"Imported {imported} memories")
    if skipped:
        console.print(f"  [dim]Skipped (duplicate): {skipped}[/dim]")
    if errors:
        console.print(f"  [yellow]Errors: {errors}[/yellow]")
