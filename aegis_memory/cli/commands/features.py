"""
Aegis CLI Features Commands

Feature tracking - replacement for dashboard Features view.
"""


import typer
from rich import box
from rich.console import Console
from rich.table import Table

from aegis_memory.cli.utils.auth import get_default_namespace
from aegis_memory.cli.utils.errors import handle_api_error, require_client, wrap_errors
from aegis_memory.cli.utils.output import (
    format_time_ago,
    print_json,
    print_success,
)

app = typer.Typer(help="Feature tracking")
console = Console()


@app.command("list")
@wrap_errors
def list_features(
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Namespace"),
    session: str | None = typer.Option(None, "--session", help="Filter by session"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    List all features with status summary.

    Use at session start to see what's complete and what needs work.
    """
    client = require_client()
    ns = namespace or get_default_namespace()

    try:
        result = client.list_features(
            namespace=ns,
            session_id=session,
            status=status,
        )
        features = result.features
    except Exception as e:
        handle_api_error(e, "list features")

    # Filter by category
    if category:
        features = [f for f in features if f.category == category]

    if json_output:
        print_json({
            "features": [
                {
                    "id": f.id,
                    "feature_id": f.feature_id,
                    "description": f.description,
                    "category": f.category,
                    "status": f.status,
                    "passes": f.passes,
                    "implemented_by": f.implemented_by,
                    "verified_by": f.verified_by,
                }
                for f in features
            ],
            "total": result.total,
            "passing": result.passing,
            "failing": result.failing,
            "in_progress": result.in_progress,
        })
        return

    if not features:
        console.print("\n[dim]No features found[/dim]")
        return

    # Pretty output
    console.print(f"\n[bold]Features[/bold] ({result.total} total)")
    console.print("─" * 70)

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Status", width=10)
    table.add_column("Feature", width=25)
    table.add_column("Category", width=12)
    table.add_column("Implemented By", width=15)

    for feature in features:
        if feature.passes:
            status_str = "[green]✓ passing[/green]"
        elif feature.status == "in_progress":
            status_str = "[yellow]● progress[/yellow]"
        elif feature.status == "failed":
            status_str = "[red]✗ failed[/red]"
        elif feature.status == "blocked":
            status_str = "[yellow]⚠ blocked[/yellow]"
        else:
            status_str = "[dim]○ pending[/dim]"

        table.add_row(
            status_str,
            feature.feature_id[:25],
            feature.category or "-",
            feature.implemented_by or "-",
        )

    console.print(table)

    # Summary
    console.print()
    console.print(f"[bold]Summary:[/bold] {result.passing} passing, {result.in_progress} in progress, {result.failing} failed")


@app.command("show")
@wrap_errors
def show_feature(
    feature_id: str = typer.Argument(..., help="Feature ID"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Show feature details.
    """
    client = require_client()
    ns = namespace or get_default_namespace()

    try:
        feature = client.get_feature(feature_id, namespace=ns)
    except Exception as e:
        handle_api_error(e, feature_id)

    if json_output:
        print_json({
            "id": feature.id,
            "feature_id": feature.feature_id,
            "description": feature.description,
            "category": feature.category,
            "status": feature.status,
            "passes": feature.passes,
            "test_steps": feature.test_steps,
            "implemented_by": feature.implemented_by,
            "verified_by": feature.verified_by,
            "updated_at": str(feature.updated_at),
        })
        return

    # Pretty output
    console.print(f"\n[bold]Feature:[/bold] {feature.feature_id}")
    console.print("─" * 40)

    console.print(f"[bold]Description:[/bold]  {feature.description}")

    if feature.category:
        console.print(f"[bold]Category:[/bold]     {feature.category}")

    # Status
    if feature.passes:
        console.print("[bold]Status:[/bold]       [green]✓ passing[/green]")
    elif feature.status == "in_progress":
        console.print("[bold]Status:[/bold]       [yellow]● in progress[/yellow]")
    elif feature.status == "failed":
        console.print("[bold]Status:[/bold]       [red]✗ failed[/red]")
    else:
        console.print(f"[bold]Status:[/bold]       {feature.status}")

    # Test steps
    if feature.test_steps:
        console.print("\n[bold]Test Steps:[/bold]")
        for i, step in enumerate(feature.test_steps, 1):
            if feature.passes:
                console.print(f"  {i}. [green]✓[/green] {step}")
            else:
                console.print(f"  {i}. [dim]○[/dim] {step}")

    # Implementation info
    if feature.implemented_by:
        console.print(f"\n[bold]Implemented by:[/bold] {feature.implemented_by}")
    if feature.verified_by:
        console.print(f"[bold]Verified by:[/bold]    {feature.verified_by}")

    console.print(f"[bold]Updated:[/bold]        {format_time_ago(feature.updated_at)}")


@app.command("create")
@wrap_errors
def create_feature(
    feature_id: str = typer.Argument(..., help="Feature ID"),
    description: str = typer.Option(..., "--description", "-d", help="Feature description"),
    category: str | None = typer.Option(None, "--category", "-c", help="Category"),
    session: str | None = typer.Option(None, "--session", help="Link to session"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Namespace"),
    test_step: list[str] | None = typer.Option(None, "--test-step", "-t", help="Test step (repeatable)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Create a feature to track.

    Examples:
        aegis features create user-auth -d "User authentication" -c auth
        aegis features create oauth -d "Google OAuth" -t "Can initiate flow" -t "Handles callback"
    """
    client = require_client()
    ns = namespace or get_default_namespace()

    try:
        feature = client.create_feature(
            feature_id=feature_id,
            description=description,
            namespace=ns,
            session_id=session,
            category=category,
            test_steps=test_step,
        )
    except Exception as e:
        handle_api_error(e, feature_id)

    if json_output:
        print_json({"feature_id": feature.feature_id, "id": feature.id})
        return

    print_success(f"Feature created: {feature.feature_id}")


@app.command("update")
@wrap_errors
def update_feature(
    feature_id: str = typer.Argument(..., help="Feature ID"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Namespace"),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
    implemented_by: str | None = typer.Option(None, "--implemented-by", help="Agent that implemented"),
    notes: str | None = typer.Option(None, "--notes", help="Implementation notes"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Update feature status.

    Examples:
        aegis features update user-auth -s in_progress --implemented-by executor
    """
    client = require_client()
    ns = namespace or get_default_namespace()

    try:
        feature = client.update_feature(
            feature_id=feature_id,
            namespace=ns,
            status=status,
            implemented_by=implemented_by,
            implementation_notes=notes,
        )
    except Exception as e:
        handle_api_error(e, feature_id)

    if json_output:
        print_json({"feature_id": feature.feature_id, "status": feature.status})
        return

    print_success(f"Feature updated: {feature.feature_id}")


@app.command("verify")
@wrap_errors
def verify_feature(
    feature_id: str = typer.Argument(..., help="Feature ID"),
    by: str = typer.Option(..., "--by", help="Agent that verified"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Namespace"),
    notes: str | None = typer.Option(None, "--notes", help="Verification notes"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Mark feature as passing (verified).

    Examples:
        aegis features verify user-auth --by qa-agent
    """
    client = require_client()
    ns = namespace or get_default_namespace()

    try:
        feature = client.mark_feature_complete(
            feature_id=feature_id,
            verified_by=by,
            namespace=ns,
            notes=notes,
        )
    except Exception as e:
        handle_api_error(e, feature_id)

    if json_output:
        print_json({"feature_id": feature.feature_id, "passes": True, "verified_by": by})
        return

    print_success(f"Feature verified: {feature.feature_id}")
    console.print("  [green]Status: passing[/green]")
    console.print(f"  Verified by: {by}")


@app.command("fail")
@wrap_errors
def fail_feature(
    feature_id: str = typer.Argument(..., help="Feature ID"),
    reason: str = typer.Option(..., "--reason", "-r", help="Failure reason"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Mark feature as failed.

    Examples:
        aegis features fail 2fa-totp -r "TOTP validation fails on time skew"
    """
    client = require_client()
    ns = namespace or get_default_namespace()

    try:
        feature = client.mark_feature_failed(
            feature_id=feature_id,
            reason=reason,
            namespace=ns,
        )
    except Exception as e:
        handle_api_error(e, feature_id)

    if json_output:
        print_json({"feature_id": feature.feature_id, "passes": False, "failure_reason": reason})
        return

    print_success(f"Feature marked failed: {feature.feature_id}")
    console.print(f"  [red]Reason: {reason}[/red]")
