from datetime import date

import pandas as pd
import pytest

from creditmonitor import dq, pipeline
from creditmonitor.config import SERIES
from creditmonitor.synthetic import SyntheticClient

TODAY = date(2026, 9, 15)


def run(tmp_path, client=None, **kw):
    return pipeline.run("synthetic", client=client, db_path=tmp_path / "wh.duckdb", data_dir=tmp_path / "data",
                        site_dir=tmp_path / "site", reports_dir=tmp_path / "reports", today=TODAY, **kw)


def test_end_to_end_produces_site_and_reports(tmp_path):
    res = run(tmp_path)
    assert res["dq_errors"] == 0 and res["gold_months"] == 185
    assert (tmp_path / "site" / "index.html").exists() and (tmp_path / "site" / "credit_monitor.csv").exists()
    assert (tmp_path / "site" / "img" / "inadimplencia.png").exists()
    assert (tmp_path / "reports" / "dq_report.md").exists()
    assert len(list((tmp_path / "data" / "bronze").glob("*/sgs_*.json"))) == len(SERIES)
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "Monitor de crédito" in html and "jul/2026" in html


def test_pipeline_is_idempotent_for_silver_and_gold(tmp_path):
    from datetime import datetime
    run(tmp_path, now=datetime(2026, 9, 15, 10))
    run(tmp_path, now=datetime(2026, 9, 16, 10))                 # segunda ingestão idêntica
    import duckdb
    con = duckdb.connect(str(tmp_path / "wh.duckdb"), read_only=True)
    assert con.execute("SELECT count(*) FROM bronze.sgs_raw").fetchone()[0] == 2 * 185 * len(SERIES)   # bronze acumula
    silver = con.execute("SELECT count(*) FROM silver.series_monthly").fetchone()[0]
    assert silver == 185 * len(SERIES)                            # a silver não duplica
    assert con.execute("SELECT count(DISTINCT ingested_at) FROM bronze.sgs_raw").fetchone()[0] == 2


class BrokenClient(SyntheticClient):
    def fetch(self, code, start="01/03/2011", end=None):
        rows = super().fetch(code, start, end)
        if code == 21082:
            del rows[50]                                          # buraco na série de inadimplência total
        return rows


def test_pipeline_stops_before_gold_when_dq_has_errors(tmp_path):
    with pytest.raises(dq.DataQualityError, match="sem meses faltando"):
        run(tmp_path, client=BrokenClient())
    assert not (tmp_path / "site" / "index.html").exists()        # nada publicado com dado ruim
    assert "FALHA" in (tmp_path / "reports" / "dq_report.md").read_text(encoding="utf-8")


def test_can_continue_with_no_fail_flag(tmp_path):
    res = run(tmp_path, client=BrokenClient(), fail_on_error=False)
    assert res["dq_errors"] >= 1 and (tmp_path / "site" / "index.html").exists()


def test_gold_csv_matches_warehouse(tmp_path):
    run(tmp_path)
    df = pd.read_csv(tmp_path / "site" / "credit_monitor.csv")
    assert {"inad_total", "spread_juros_selic", "gap_inad_pf_pj"} <= set(df.columns)
    assert df.inad_total.between(0, 100).all()
