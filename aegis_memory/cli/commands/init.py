"""Top-level init wizard with framework detection."""

import typer
from rich.console import Console
from rich.prompt import Prompt

from aegis_memory.cli.commands.config import init as config_init
from aegis_memory.cli.utils.frameworks import detect_framework, recommended_namespace

console = Console()


def init(
    non_interactive: bool = typer.Option(False, "--non-interactive", "-y", help="Use defaults without prompting"),
):
    """Interactive setup wizard with framework detection."""
    framework = detect_framework()

    if framework:
        console.print(f"[green]Detected framework:[/green] {framework}")
    else:
        console.print("[yellow]No framework detected automatically.[/yellow]")

    if non_interactive:
        config_init(non_interactive=True)
        return

    use_recommended = False
    if framework:
        use_recommended = Prompt.ask(
            "Use recommended defaults for detected framework?",
            choices=["y", "n"],
            default="y",
        ) == "y"

    if use_recommended:
        # Run config init non-interactively, then patch recommended namespace/agent.
        config_init(non_interactive=True)
        from aegis_memory.cli.utils.config import load_config, save_config

        cfg = load_config()
        cfg.setdefault("profiles", {}).setdefault("local", {})
        cfg["profiles"]["local"]["default_namespace"] = recommended_namespace(framework)
        cfg["profiles"]["local"]["default_agent_id"] = f"{framework}-agent"
        save_config(cfg)
        console.print("[green]Updated config with framework-specific defaults.[/green]")
        return

    config_init(non_interactive=False)
