"""Build the point-in-time dataset: extract tables from a run, then compute features and labels.

Output, in `data/processed/<run_name>/`:
- `dataset.duckdb`: tables `players`, `buckets`, `matches`, `examples`, `sequences` and
  `candidates`, ready for SQL exploration.
- `examples.parquet`: one row per (player, cutoff), the input to modelling.
- `sequences.parquet`: one row per (player, cutoff, recent game), the neural nets' input.
- `candidates.parquet`: candidate features per (player, cutoff), judged by the forward test
  before they join the model (ADR 0013).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa

from lolret.collect.config import CollectConfig
from lolret.collect.store import Store
from lolret.dataset.extract import Tables, extract

FEATURES_SQL = (Path(__file__).parent / "features.sql").read_text(encoding="utf-8")
SEQUENCES_SQL = (Path(__file__).parent / "sequences.sql").read_text(encoding="utf-8")
CANDIDATES_SQL = (Path(__file__).parent / "candidates.sql").read_text(encoding="utf-8")


@dataclass(frozen=True)
class BuildSummary:
    players: int
    examples: int
    eligible: int
    churn_rate_eligible: float | None
    path: Path


def build_examples(con: duckdb.DuckDBPyConnection, tables: Tables, cutoffs: list[datetime]) -> None:
    """Create tables `examples`, `sequences` and `candidates` in `con` from the tables."""
    cutoff_table = pa.table(
        {"cutoff": pa.array([c.replace(tzinfo=None) for c in cutoffs], pa.timestamp("ms"))}
    )
    for name, table in (
        ("players", tables.players),
        ("buckets", tables.buckets),
        ("matches", tables.matches),
        ("cutoffs", cutoff_table),
    ):
        con.from_arrow(table).create(name)
    # Both queries are constants shipped with the package, not user input.
    con.execute("CREATE TABLE examples AS " + FEATURES_SQL)
    con.execute("CREATE TABLE sequences AS " + SEQUENCES_SQL)
    con.execute("CREATE TABLE candidates AS " + CANDIDATES_SQL)


def build_dataset(cfg: CollectConfig, store: Store, out_dir: Path) -> BuildSummary:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "dataset.duckdb"
    db_path.unlink(missing_ok=True)  # always rebuilt from the raw store
    tables = extract(store, cfg)
    with duckdb.connect(str(db_path)) as con:
        build_examples(con, tables, cfg.cutoffs)
        con.table("examples").write_parquet(str(out_dir / "examples.parquet"))
        con.table("sequences").write_parquet(str(out_dir / "sequences.parquet"))
        con.table("candidates").write_parquet(str(out_dir / "candidates.parquet"))
        row = con.execute(
            """SELECT count(*), count(*) FILTER (WHERE eligible),
                      avg(churned::INT) FILTER (WHERE eligible)
               FROM examples"""
        ).fetchone() or (0, 0, None)
    return BuildSummary(
        players=tables.players.num_rows,
        examples=int(row[0]),
        eligible=int(row[1]),
        churn_rate_eligible=None if row[2] is None else float(row[2]),
        path=db_path,
    )
