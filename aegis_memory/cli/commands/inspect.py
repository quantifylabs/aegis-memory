"""Aegis Inspect CLI — ``aegis inspect`` and ``aegis replay``.

Standalone, server-free, offline. Unlike the other CLI commands these never need a running
Aegis server or an API key: they run static analysis and a local deterministic scan.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()


def inspect(
    path: str = typer.Argument(".", help="Project directory to inspect"),
    framework: str | None = typer.Option(
        None, "--framework", help="Force a sink adapter (e.g. langgraph). Auto-detect by default."
    ),
    ci: bool = typer.Option(False, "--ci", help="CI mode: machine output + non-zero exit on breach"),
    max_risk: int = typer.Option(60, "--max-risk", help="CI risk-score threshold for a non-zero exit"),
):
    """Inspect an agent project for unsafe memory flows. Writes aegis-out/."""
    from aegis_memory.inspect import run_inspection

    root = Path(path).resolve()
    if not root.is_dir():
        console.print(f"[red]Not a directory:[/red] {root}")
        raise typer.Exit(code=2)

    result = run_inspection(root, framework=framework)
    score = result.score["score"]
    counts = result.score["counts"]
    n = len(result.findings)

    if ci:
        # Terse, parseable output.
        console.print(
            f"aegis-inspect findings={n} score={score} "
            f"critical={counts['critical']} high={counts['high']} "
            f"medium={counts['medium']} low={counts['low']} max_risk={max_risk}"
        )
        if score > max_risk:
            console.print(f"[red]RISK BREACH[/red]: score {score} > max-risk {max_risk}")
            raise typer.Exit(code=1)
        console.print("[green]OK[/green]: within risk threshold")
        return

    console.print(f"\n[bold]Aegis Inspect[/bold] — {root.name}")
    console.print(f"[dim]Wrote {result.out_root}[/dim]\n")
    crit = [f for f in result.findings if f.severity in ("critical", "high")]
    if crit:
        console.print("[bold]Top findings:[/bold]")
        for f in crit[:10]:
            color = "red" if f.severity == "critical" else "yellow"
            console.print(
                f"  [{color}]{f.id} [{f.severity}/{f.confidence}][/{color}] {f.title}"
            )
            console.print(f"    [dim]{f.sink.file}:{f.sink.line} · {f.sink.call}[/dim]")
    else:
        console.print("[green]No critical/high findings.[/green]")
    console.print(
        f"\nMemory Risk Score: [bold]{score}/100[/bold] [dim](heuristic)[/dim]  "
        f"Critical {counts['critical']} · High {counts['high']} · "
        f"Medium {counts['medium']} · Low {counts['low']}"
    )
    console.print(
        f"\nReport: [cyan]{result.out_root / 'INSPECTION_REPORT.md'}[/cyan]\n"
        f"Map:    [cyan]{result.out_root / 'agent_memory_map.html'}[/cyan]"
    )


def replay(
    path: str = typer.Argument(".", help="Project directory (for output location)"),
    attack: str = typer.Option(
        "memory-poisoning", "--attack", help="Built-in attack to replay"
    ),
):
    """Replay a built-in attack against the project using the real scanner."""
    from aegis_memory.inspect import replay as replay_mod

    if attack != "memory-poisoning":
        console.print(f"[red]Unknown attack:[/red] {attack} (only 'memory-poisoning' in v1)")
        raise typer.Exit(code=2)

    result = replay_mod.run_memory_poisoning()
    wa = result["with_aegis"]
    console.print("\n[bold]Replay: memory-poisoning[/bold]\n")
    console.print(f"[dim]Payload:[/dim] {result['payload']}\n")
    console.print("[red]Without Aegis:[/red] stored in long-term memory. Poison persists.")
    blocked = not wa["allowed"]
    verb = "[green]REJECTED[/green]" if blocked else f"[yellow]{wa['action']}[/yellow]"
    console.print(f"[green]With Aegis:[/green]    {verb} by the injection scanner.")
    console.print(f"               reason: {wa['reason']}")

    out_dir = Path(path).resolve() / "aegis-out" / "replay_attacks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "memory_poisoning_demo.md"
    out_file.write_text(replay_mod.render_markdown(result), encoding="utf-8")
    console.print(f"\n[dim]Wrote {out_file}[/dim]")
