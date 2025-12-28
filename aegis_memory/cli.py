"""
Aegis Memory - Command Line Interface

Usage:
    aegis demo          Run the interactive 60-second demo
    aegis demo --log    Save demo output to demo.log
    aegis health        Check server health
    aegis version       Show version info
"""

import click
import sys

from aegis_memory import __version__


@click.group()
@click.version_option(version=__version__, prog_name="aegis")
def main():
    """Aegis Memory - The Memory Layer for AI Agents"""
    pass


@main.command()
@click.option('--log', is_flag=True, help='Save demo output to demo.log for sharing')
@click.option('--server', default='http://localhost:8000', help='Aegis server URL')
@click.option('--quiet', is_flag=True, help='Minimal output (no explanations)')
@click.option('--skip-server-check', is_flag=True, help='Skip server health check')
def demo(log, server, quiet, skip_server_check):
    """
    Run the interactive 60-second demo.
    
    Shows Aegis Memory's core value in 5 acts:
    
    \b
    1. THE PROBLEM     - Agents forget everything between sessions
    2. AEGIS MEMORY    - Persistent memory that survives context resets
    3. SMART EXTRACT   - Automatic extraction of valuable information
    4. MULTI-AGENT     - Agents share knowledge with scope control
    5. SELF-IMPROVE    - Agents learn what works over time
    
    Examples:
    
    \b
        aegis demo              # Run the demo
        aegis demo --log        # Save output to demo.log
        aegis demo --quiet      # Minimal output
    """
    from aegis_memory.demo import run_demo
    
    success = run_demo(
        log=log,
        server_url=server,
        quiet=quiet,
        skip_server_check=skip_server_check
    )
    
    sys.exit(0 if success else 1)


@main.command()
@click.option('--server', default='http://localhost:8000', help='Aegis server URL')
def health(server):
    """Check Aegis server health."""
    import httpx
    
    try:
        response = httpx.get(f"{server}/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            click.echo(f"✓ Server healthy: {server}")
            click.echo(f"  Status: {data.get('status', 'unknown')}")
        else:
            click.echo(f"✗ Server returned {response.status_code}")
            sys.exit(1)
    except httpx.ConnectError:
        click.echo(f"✗ Cannot connect to {server}")
        click.echo("  Start the server: docker compose up -d")
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Error: {e}")
        sys.exit(1)


@main.command()
def version():
    """Show version information."""
    click.echo(f"Aegis Memory v{__version__}")
    click.echo("https://github.com/quantifylabs/aegis-memory")


if __name__ == '__main__':
    main()
