"""Command-line entry point: `lolret <command>`.

Pipeline commands (train, export, predict) are added phase by phase.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from lolret import __version__
from lolret.collect.config import CollectConfig, load_config
from lolret.collect.runner import RunResult, format_duration, run_collection
from lolret.collect.store import Store
from lolret.config import Settings, get_settings
from lolret.dataset.build import build_dataset
from lolret.log import configure_logging, get_logger
from lolret.notify import notify_discord
from lolret.riot.client import RiotAuthError, RiotClient
from lolret.riot.ratelimit import parse_limits

app = typer.Typer(help="LoL player-retention pipeline.", no_args_is_help=True)
log = get_logger(__name__)

ConfigOption = Annotated[
    Path, typer.Option("--config", "-c", help="Collection config (YAML).", exists=True)
]
DEFAULT_COLLECT_CONFIG = Path("configs/collect.yaml")

EXIT_FAILED_REQUESTS = 2
EXIT_INTERRUPTED = 130


def run_db_path(settings: Settings, cfg: CollectConfig) -> Path:
    return settings.data_dir / "raw" / f"{cfg.run_name}.sqlite"


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
    typer.echo(f"riot_rate_limits:    {settings.riot_rate_limits}")
    typer.echo(f"riot_api_key:        {'set' if settings.riot_api_key else 'missing'}")
    typer.echo(f"discord_webhook_url: {'set' if settings.discord_webhook_url else 'missing'}")


async def _collect(cfg: CollectConfig, store: Store, settings: Settings, api_key: str) -> RunResult:
    limits = parse_limits(settings.riot_rate_limits)
    async with RiotClient(api_key, limits=limits) as client:
        return await run_collection(cfg, store, client, now=datetime.now(UTC))


@app.command()
def collect(config: ConfigOption = DEFAULT_COLLECT_CONFIG) -> None:
    """Sample players and download their match history from the Riot API.

    Safe to stop (Ctrl+C) and re-run: finished requests are never sent again.
    """
    settings = get_settings()
    if settings.riot_api_key is None:
        log.error("RIOT_API_KEY is not set. Copy .env.example to .env and add your key.")
        raise typer.Exit(1)
    cfg = load_config(config)
    store = Store(run_db_path(settings, cfg))
    log.info("Run '%s': %d cutoffs, data in %s", cfg.run_name, cfg.n_cutoffs, store.path)
    try:
        result = asyncio.run(
            _collect(cfg, store, settings, settings.riot_api_key.get_secret_value())
        )
    except RiotAuthError as exc:
        log.error("%s Progress is saved; re-run after fixing the key.", exc)
        notify_discord(
            settings.discord_webhook_url,
            f"lolret collect '{cfg.run_name}' stopped: Riot key rejected.",
        )
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        log.warning("Interrupted. Progress is saved; re-run the same command to resume.")
        raise typer.Exit(EXIT_INTERRUPTED) from None
    finally:
        store.close()

    complete = sum(p.complete for p in result.platforms)
    players = sum(p.players for p in result.platforms)
    summary = (
        f"lolret collect '{cfg.run_name}' finished in {format_duration(result.seconds)}: "
        f"{complete}/{players} players complete, {result.failed} failed, "
        f"{result.requests} API requests, {result.cache_hits} cache hits."
    )
    log.info(summary)
    notify_discord(settings.discord_webhook_url, summary)
    if result.failed:
        log.warning("Re-run the same command to retry the failed work.")
        raise typer.Exit(EXIT_FAILED_REQUESTS)


@app.command()
def status(config: ConfigOption = DEFAULT_COLLECT_CONFIG) -> None:
    """Show a collection run's progress. Safe to run while `collect` is running."""
    settings = get_settings()
    cfg = load_config(config)
    path = run_db_path(settings, cfg)
    if not path.exists():
        typer.echo(f"Run '{cfg.run_name}' has no data yet ({path}).")
        return
    store = Store(path, read_only=True)
    try:
        summary = store.summary()
    finally:
        store.close()
    target = len(cfg.tiers) * len(cfg.divisions) * cfg.players_per_division
    typer.echo(f"Run '{cfg.run_name}' ({path})")
    for platform in cfg.platforms:
        sampled = summary["players"].get(platform, 0)
        complete = summary["complete"].get(platform, 0)
        typer.echo(
            f"  {platform:<5} {complete:>6} / {sampled:<6} players complete (target {target})"
        )
    for endpoint, count in sorted(summary["responses"].items()):
        typer.echo(f"  {endpoint:<15} {count:>8} responses cached")
    typer.echo(f"  open failures   {summary['failures']['open']:>8}")


@app.command()
def build(config: ConfigOption = DEFAULT_COLLECT_CONFIG) -> None:
    """Build the point-in-time dataset (features and labels) from a collection run.

    Reads only stored responses, never the API, and only players whose collection finished,
    so it can run while `collect` is still going.
    """
    settings = get_settings()
    cfg = load_config(config)
    raw = run_db_path(settings, cfg)
    if not raw.exists():
        log.error(
            "No collected data for run '%s' at %s. Run `lolret collect` first.", cfg.run_name, raw
        )
        raise typer.Exit(1)
    store = Store(raw, read_only=True)
    try:
        summary = build_dataset(cfg, store, settings.data_dir / "processed" / cfg.run_name)
    finally:
        store.close()
    churn = "n/a" if summary.churn_rate_eligible is None else f"{summary.churn_rate_eligible:.1%}"
    log.info(
        "Built %d examples from %d players: %d eligible, churn among eligible %s. Data in %s",
        summary.examples,
        summary.players,
        summary.eligible,
        churn,
        summary.path.parent,
    )
