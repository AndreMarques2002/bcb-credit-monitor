"""Orquestração: ingestão (bronze) -> silver -> qualidade -> gold -> painel.

Uso:
    python -m creditmonitor.pipeline --source live        # API real do Banco Central
    python -m creditmonitor.pipeline --source synthetic   # demonstração offline (dados SINTÉTICOS)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from . import dq, report, warehouse
from .config import DATA_DIR, REPORTS_DIR, SITE_DIR, WAREHOUSE_PATH
from .ingest import IngestError, SgsClient, fetch_all, save_raw_snapshot, utcnow
from .synthetic import SyntheticClient

log = logging.getLogger("creditmonitor")


def run(source: str = "live", *, client=None, db_path: Path | str = WAREHOUSE_PATH, data_dir: Path = DATA_DIR,
        site_dir: Path = SITE_DIR, reports_dir: Path = REPORTS_DIR, today: date | None = None,
        fail_on_error: bool = True, now: datetime | None = None) -> dict:
    t0 = time.perf_counter()
    client = client or (SyntheticClient() if source == "synthetic" else SgsClient())

    log.info("1/5 Ingestão (%s)", source)
    raw = fetch_all(client)
    ingested_at = now or utcnow()
    snapshot_dir = save_raw_snapshot(raw, data_dir, ingested_at)
    con = warehouse.connect(db_path)
    n_bronze = warehouse.load_bronze(con, raw, ingested_at)

    log.info("2/5 Silver")
    warehouse.run_sql_models(con, prefixes=("01",))

    log.info("3/5 Qualidade de dados")
    checks = dq.run_checks(con, today)
    reports_dir.mkdir(parents=True, exist_ok=True)
    checks.to_csv(reports_dir / "dq_results.csv", index=False)
    (reports_dir / "dq_report.md").write_text(dq.to_markdown(checks), encoding="utf-8")
    if dq.has_errors(checks) and fail_on_error:
        failed = checks[(checks.severidade == "error") & (~checks.ok)]
        raise dq.DataQualityError("Checagens com erro:\n" + failed[["check", "detalhe"]].to_string(index=False))

    log.info("4/5 Gold")
    warehouse.run_sql_models(con, prefixes=("02", "03", "04"))

    log.info("5/5 Painel")
    index = report.build_site(con, checks, site_dir)
    n_rows = con.execute("SELECT count(*) FROM gold.credit_monitor").fetchone()[0]
    con.close()
    return {"bronze_rows": n_bronze, "gold_months": n_rows, "site": str(index), "snapshot": str(snapshot_dir),
            "dq_errors": int(((checks.severidade == "error") & ~checks.ok).sum()),
            "dq_warnings": int(((checks.severidade == "warn") & ~checks.ok).sum()),
            "seconds": round(time.perf_counter() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["live", "synthetic"], default="live")
    ap.add_argument("--no-fail", action="store_true", help="não interrompe se houver erro de qualidade")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    try:
        res = run(a.source, fail_on_error=not a.no_fail)
    except (IngestError, dq.DataQualityError) as exc:
        log.error("%s", exc)
        return 1
    log.info("Concluído: %s", res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
