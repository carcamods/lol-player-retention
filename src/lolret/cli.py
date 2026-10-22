"""Command-line entry point: `lolret <command>`.

Pipeline commands (collect, build, train, export, predict) are added phase by phase.
"""

import typer

from lolret import __version__
from lolret.config import get_settings
from lolret.log import configure_logging

app = typer.Typer(help="LoL player-retention pipeline.", no_args_is_help=True)


@app.callback()
def main() -> None:
    configure_logging(get_settings().log_level)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def config() -> None:
    """Show the effective configuration. Secrets are reported as set/missing, never printed."""
    settings = get_settings()
    typer.echo(f"data_dir:            {settings.data_dir}")
    typer.echo(f"log_level:           {settings.log_level}")
    typer.echo(f"riot_api_key:        {'set' if settings.riot_api_key else 'missing'}")
    typer.echo(f"discord_webhook_url: {'set' if settings.discord_webhook_url else 'missing'}")
