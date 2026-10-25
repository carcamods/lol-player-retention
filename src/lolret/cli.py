"""Command-line entry point: `lolret <command>`.

Pipeline commands (export, predict) are added phase by phase.
"""

import asyncio
from collections.abc import Awaitable, Callable
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
from lolret.forward.collect import collect_features, collect_labels
from lolret.forward.config import Forward, ForwardError, load_forward
from lolret.forward.predict import freeze_predictions, frozen_players
from lolret.forward.score import PRIMARY, REPORT_FILE, score_forward
from lolret.log import configure_logging, get_logger
from lolret.model.config import load_train_config
from lolret.model.train import InsufficientDataError, examples_path, train_and_evaluate
from lolret.notify import notify_discord
from lolret.riot.client import RiotAuthError, RiotClient
from lolret.riot.ratelimit import parse_limits

app = typer.Typer(help="LoL player-retention pipeline.", no_args_is_help=True)
forward_app = typer.Typer(
    help="Forward test: predict at a new cutoff now, score it once the outcomes exist.",
    no_args_is_help=True,
)
app.add_typer(forward_app, name="forward")
log = get_logger(__name__)

ConfigOption = Annotated[
    Path, typer.Option("--config", "-c", help="Collection config (YAML).", exists=True)
]
DEFAULT_COLLECT_CONFIG = Path("configs/collect.yaml")
TrainConfigOption = Annotated[
    Path, typer.Option("--config", "-c", help="Training config (YAML).", exists=True)
]
DEFAULT_TRAIN_CONFIG = Path("configs/train.yaml")
ForwardOption = Annotated[
    Path, typer.Option("--config", "-c", help="Forward-test config (YAML).", exists=True)
]
DEFAULT_FORWARD_CONFIG = Path("configs/forward.yaml")

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


def _require_key(settings: Settings) -> str:
    if settings.riot_api_key is None:
        log.error("RIOT_API_KEY is not set. Copy .env.example to .env and add your key.")
        raise typer.Exit(1)
    return settings.riot_api_key.get_secret_value()


def _run_requests(
    label: str,
    settings: Settings,
    api_key: str,
    work: Callable[[RiotClient], Awaitable[RunResult]],
) -> RunResult:
    """Run a collection with a rate-limited client; handle a rejected key and Ctrl+C."""

    async def run() -> RunResult:
        limits = parse_limits(settings.riot_rate_limits)
        async with RiotClient(api_key, limits=limits) as client:
            return await work(client)

    try:
        return asyncio.run(run())
    except RiotAuthError as exc:
        log.error("%s Progress is saved; re-run after fixing the key.", exc)
        notify_discord(settings.discord_webhook_url, f"{label} stopped: Riot key rejected.")
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        log.warning("Interrupted. Progress is saved; re-run the same command to resume.")
        raise typer.Exit(EXIT_INTERRUPTED) from None


def _report(label: str, settings: Settings, result: RunResult) -> None:
    complete = sum(p.complete for p in result.platforms)
    players = sum(p.players for p in result.platforms)
    summary = (
        f"{label} finished in {format_duration(result.seconds)}: "
        f"{complete}/{players} players complete, {result.failed} failed, "
        f"{result.requests} API requests, {result.cache_hits} cache hits."
    )
    log.info(summary)
    notify_discord(settings.discord_webhook_url, summary)
    if result.failed:
        log.warning("Re-run the same command to retry the failed work.")
        raise typer.Exit(EXIT_FAILED_REQUESTS)


@app.command()
def collect(config: ConfigOption = DEFAULT_COLLECT_CONFIG) -> None:
    """Sample players and download their match history from the Riot API.

    Safe to stop (Ctrl+C) and re-run: finished requests are never sent again.
    """
    settings = get_settings()
    api_key = _require_key(settings)
    cfg = load_config(config)
    store = Store(run_db_path(settings, cfg))
    log.info("Run '%s': %d cutoffs, data in %s", cfg.run_name, cfg.n_cutoffs, store.path)
    label = f"lolret collect '{cfg.run_name}'"
    try:
        result = _run_requests(
            label,
            settings,
            api_key,
            lambda client: run_collection(cfg, store, client, now=datetime.now(UTC)),
        )
    finally:
        store.close()
    _report(label, settings, result)


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


@app.command()
def train(config: TrainConfigOption = DEFAULT_TRAIN_CONFIG) -> None:
    """Train the classical models on a built dataset and evaluate them on held-out players.

    Writes models, metrics.json and model_card.md to data/models/<dataset>/.
    """
    settings = get_settings()
    cfg = load_train_config(config)
    source = examples_path(settings.data_dir, cfg.dataset)
    if not source.exists():
        log.error("No dataset '%s' at %s. Run `lolret build` first.", cfg.dataset, source)
        raise typer.Exit(1)
    try:
        summary = train_and_evaluate(cfg, settings.data_dir)
    except InsufficientDataError as exc:
        log.error("Not enough data to train: %s.", exc)
        raise typer.Exit(1) from None
    for name, r in summary.test.items():
        log.info(
            "%-9s PR-AUC %s  ROC-AUC %s  Brier %.3f",
            name,
            "n/a" if r["pr_auc"] is None else f"{r['pr_auc']:.3f}",
            "n/a" if r["roc_auc"] is None else f"{r['roc_auc']:.3f}",
            r["brier"],
        )
    log.info("Models, metrics.json and model_card.md in %s", summary.out_dir)


def _load_forward(config: Path) -> Forward:
    try:
        return load_forward(config)
    except (ValueError, OSError) as exc:
        log.error("Invalid forward-test config %s: %s", config, exc)
        raise typer.Exit(1) from None


@forward_app.command("collect")
def forward_collect(
    config: ForwardOption = DEFAULT_FORWARD_CONFIG,
    labels: Annotated[
        bool, typer.Option("--labels", help="Collect the outcomes, once the label window ended.")
    ] = False,
) -> None:
    """Fetch what the forward test needs: features now, outcomes 28 days later (--labels).

    Reuses the base run's cached responses, which are never written. Safe to stop and re-run.
    """
    settings = get_settings()
    api_key = _require_key(settings)
    fwd = _load_forward(config)
    label = f"lolret forward collect '{fwd.name}' ({'labels' if labels else 'features'})"
    now = datetime.now(UTC)

    def work(client: RiotClient) -> Awaitable[RunResult]:
        if labels:
            players = frozen_players(fwd, settings.data_dir)
            return collect_labels(fwd, settings.data_dir, client, players, now=now)
        return collect_features(fwd, settings.data_dir, client, now=now)

    try:
        result = _run_requests(label, settings, api_key, work)
    except ForwardError as exc:
        log.error("%s", exc)
        raise typer.Exit(1) from None
    _report(label, settings, result)


@forward_app.command("predict")
def forward_predict(config: ForwardOption = DEFAULT_FORWARD_CONFIG) -> None:
    """Train on every labelled example and freeze predictions at the forward cutoff.

    Runs once: it refuses to overwrite frozen predictions, or to run once labels exist.
    """
    settings = get_settings()
    fwd = _load_forward(config)
    try:
        summary = freeze_predictions(fwd, settings.data_dir, now=datetime.now(UTC))
    except ForwardError as exc:
        log.error("%s", exc)
        raise typer.Exit(1) from None
    log.info(
        "Froze predictions for %d players (mean LightGBM churn probability %.1f%%) in %s.",
        summary.players,
        100 * summary.churn_expected,
        summary.entry,
    )
    typer.echo(f"Commit this in {config} before collecting labels:")
    typer.echo("entries:")
    typer.echo(f"  ladder: {summary.sha256}")


@forward_app.command("score")
def forward_score(config: ForwardOption = DEFAULT_FORWARD_CONFIG) -> None:
    """Score the frozen predictions against the collected outcomes."""
    settings = get_settings()
    fwd = _load_forward(config)
    try:
        summary = score_forward(fwd, settings.data_dir, now=datetime.now(UTC))
    except ForwardError as exc:
        log.error("%s", exc)
        raise typer.Exit(1) from None
    log.info("%d eligible players, %d churned.", summary.players, summary.churned)
    for name, r in summary.results.items():
        log.info("%-9s PR-AUC %.3f  ROC-AUC %.3f", name, r["pr_auc"], r["roc_auc"])
    if PRIMARY in summary.vs_baseline:
        c = summary.vs_baseline[PRIMARY]
        lo, hi = c["pr_auc_diff_ci"] or (float("nan"), float("nan"))
        log.info(
            "%s - recency: %+.3f PR-AUC (95%% CI %+.3f to %+.3f)",
            PRIMARY,
            c["pr_auc_diff"],
            lo,
            hi,
        )
    log.info("Report in %s", summary.out_dir / REPORT_FILE)
