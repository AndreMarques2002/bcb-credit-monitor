"""DuckDB como data warehouse local: camadas bronze, silver e gold em SQL."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from .config import SERIES, SGS_URL, SQL_DIR


def connect(path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS meta; CREATE SCHEMA IF NOT EXISTS bronze;")
    con.execute("""CREATE TABLE IF NOT EXISTS bronze.sgs_raw (
        series_code INTEGER, data VARCHAR, valor VARCHAR, ingested_at TIMESTAMP, source_url VARCHAR)""")
    load_series_dimension(con)
    return con


def load_series_dimension(con) -> None:
    dim = pd.DataFrame([{"series_code": s.code, "series_key": s.key, "name": s.name,
                         "unit": s.unit, "kind": s.kind} for s in SERIES])
    con.execute("CREATE OR REPLACE TABLE meta.series AS SELECT * FROM dim")


def load_bronze(con, raw: dict[int, list[dict]], ingested_at: datetime) -> int:
    """Acrescenta (append-only) os registros brutos com metadados de ingestão."""
    frames = []
    for code, rows in raw.items():
        df = pd.DataFrame(rows, columns=["data", "valor"])
        df.insert(0, "series_code", code)
        df["ingested_at"] = ingested_at
        df["source_url"] = SGS_URL.split("?")[0].format(code=code)
        frames.append(df)
    batch = pd.concat(frames, ignore_index=True)
    con.execute("INSERT INTO bronze.sgs_raw SELECT series_code, data, valor, ingested_at, source_url FROM batch")
    return len(batch)


def run_sql_models(con, sql_dir: Path = SQL_DIR, prefixes: tuple[str, ...] | None = None) -> list[str]:
    """Executa sql/*.sql em ordem alfabética. `prefixes` filtra por início do nome (ex.: ("01",))."""
    files = sorted(Path(sql_dir).glob("*.sql"))
    if prefixes:
        files = [f for f in files if f.name.startswith(prefixes)]
    if not files:
        raise FileNotFoundError(f"Nenhum modelo SQL em {sql_dir} para {prefixes}")
    for f in files:
        con.execute(f.read_text(encoding="utf-8"))
    return [f.name for f in files]
