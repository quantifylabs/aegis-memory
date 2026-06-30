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
    baseline: str | None = typer.Option(
        None,
        "--baseline",
        help="Inspect this path too and use its risk score as the 'before' in the before->after map "
        "(e.g. the unscreened version of the same agent).",
    ),
    ci: bool = typer.Option(False, "--ci", help="CI mode: machine output + non-zero exit on breach"),
    max_risk: int = typer.Option(60, "--max-risk", help="CI risk-score threshold for a non-zero exit"),
    emit_cases: bool = typer.Option(
        False, "--emit-cases", help="Also write aegis-out/cases/cases.json for session-model classification"
    ),
    ingest_verdicts: bool = typer.Option(
        False, "--ingest-verdicts", help="Fold aegis-out/cases/verdicts.json back into the report"
    ),
):
    """Inspect an agent project for unsafe memory flows. Writes aegis-out/.

    Suppress an accepted sink with an inline ``# aegis: ignore`` comment on (or directly above) the
    write call. Findings are also written as SARIF (``aegis-out/findings.sarif``) for GitHub code
    scanning / CI annotation.
    """
    from aegis_memory.inspect import (
        emit_cases as _emit_cases,
    )
    from aegis_memory.inspect import (
        ingest_verdicts as _ingest_verdicts,
    )
    from aegis_memory.inspect import (
        run_inspection,
    )
    from aegis_memory.inspect.cases import StaleVerdictsError

    root = Path(path).resolve()
    if not root.is_dir():
        console.print(f"[red]Not a directory:[/red] {root}")
        raise typer.Exit(code=2)

    before_score: int | None = None
    if baseline is not None:
        baseline_root = Path(baseline).resolve()
        if not baseline_root.is_dir():
            console.print(f"[red]Not a directory:[/red] {baseline_root}")
            raise typer.Exit(code=2)
        before_score = run_inspection(baseline_root, framework=framework, write=False).score["score"]

    if emit_cases and ingest_verdicts:
        console.print("[red]Use --emit-cases and --ingest-verdicts in separate runs.[/red]")
        raise typer.Exit(code=2)

    if ingest_verdicts:
        try:
            result = _ingest_verdicts(root, framework=framework)
        except FileNotFoundError:
            console.print("[red]No cases/verdicts found.[/red] Run --emit-cases first, then write verdicts.json.")
            raise typer.Exit(code=2) from None
        except StaleVerdictsError as e:
            console.print(f"[red]Stale verdicts:[/red] {e}")
            raise typer.Exit(code=2) from None
        score = result.score["score"]
        counts = result.score["counts"]
        console.print(
            f"[green]Ingested verdicts[/green] → refreshed "
            f"[cyan]{result.out_root / 'INSPECTION_REPORT.md'}[/cyan]  "
            f"(score {score}/100; critical {counts['critical']}, high {counts['high']})"
        )
        return
    if emit_cases:
        result, doc = _emit_cases(root, framework=framework)
        n_cases = len(doc["cases"])
        console.print(
            f"[bold]Aegis Inspect[/bold] — emitted {n_cases} case(s) → "
            f"[cyan]{result.out_root / 'cases' / 'cases.json'}[/cyan] (run_id {doc['run_id']})"
        )
        console.print(
            "Have the assistant classify each case as untrusted data, write "
            "cases/verdicts.json, then run [bold]aegis inspect . --ingest-verdicts[/bold]."
        )
        return

    result = run_inspection(root, framework=framework, before_score=before_score)
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
        console.print(f"sarif={result.out_root / 'findings.sarif'}")
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
        f"Map:    [cyan]{result.out_root / 'agent_memory_map.html'}[/cyan]\n"
        f"SARIF:  [cyan]{result.out_root / 'findings.sarif'}[/cyan] [dim](upload to GitHub code scanning)[/dim]"
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
