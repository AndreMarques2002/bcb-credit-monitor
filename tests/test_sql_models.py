from datetime import datetime

import numpy as np
import pandas as pd

from creditmonitor import warehouse

from .conftest import build, payload


def test_silver_keeps_latest_ingestion_for_the_same_month():
    old = payload({"inad_total": [3.0, 3.1]})
    new = payload({"inad_total": [3.0, 3.5]})            # BCB revisou o 2º mês
    con = build(old, datetime(2026, 1, 1), silver=False)
    warehouse.load_bronze(con, new, datetime(2026, 2, 1))
    warehouse.run_sql_models(con, prefixes=("01",))
    rows = con.execute("SELECT ref_month, value FROM silver.series_monthly ORDER BY ref_month").fetchall()
    assert [r[1] for r in rows] == [3.0, 3.5] and len(rows) == 2


def test_silver_drops_unparseable_rows():
    raw = payload({"inad_total": [3.0, 3.1, 3.2]})
    code = next(iter(raw))
    raw[code][1]["valor"] = "n/d"
    raw[code][2]["data"] = "31/02/2020"                   # data inexistente
    con = build(raw)
    assert con.execute("SELECT count(*) FROM silver.series_monthly").fetchone()[0] == 1


def test_series_metrics_mom_yoy_ma12():
    vals = [float(i) for i in range(1, 15)]               # 1..14
    con = build(payload({"inad_total": vals}))
    warehouse.run_sql_models(con, prefixes=("02",))
    m = con.execute("SELECT * FROM gold.series_metrics ORDER BY ref_month").df()
    assert np.isnan(m.mom.iloc[0]) and m.mom.iloc[1:].eq(1.0).all()
    assert m.yoy.iloc[:12].isna().all() and m.yoy.iloc[12] == 12.0 and m.yoy.iloc[13] == 12.0
    assert m.ma12.iloc[:11].isna().all()
    assert m.ma12.iloc[11] == np.mean(vals[:12]) and m.ma12.iloc[13] == np.mean(vals[2:14])
    assert m.pctl_hist.iloc[-1] == 1.0 and m.pctl_hist.iloc[0] == 0.0


def test_mom_is_null_when_previous_month_is_missing():
    raw = payload({"inad_total": [3.0, 3.1, 3.2, 3.3]})
    code = next(iter(raw))
    del raw[code][1]                                      # falta fev/2020: mar não pode comparar com "o anterior" errado
    con = build(raw)
    warehouse.run_sql_models(con, prefixes=("02",))
    m = con.execute("SELECT ref_month, mom FROM gold.series_metrics ORDER BY ref_month").df()
    assert pd.isna(m.mom.iloc[1])                         # mar/2020 sem fev/2020
    assert abs(m.mom.iloc[2] - 0.1) < 1e-9                # abr/2020 compara com mar/2020


def test_credit_monitor_spreads():
    n = 5
    con = build(payload({"inad_total": [3.0] * n, "inad_pf": [4.0] * n, "inad_pj": [2.0] * n,
                         "juros_total": [30.0] * n, "selic": [12.0] * n}))
    warehouse.run_sql_models(con, prefixes=("02", "03"))
    d = con.execute("SELECT * FROM gold.credit_monitor ORDER BY ref_month").df()
    assert (d.spread_juros_selic == 18.0).all() and (d.gap_inad_pf_pj == 2.0).all() and len(d) == n


def test_alert_flags_the_outlier_and_not_the_calm_months():
    rng = np.random.default_rng(0)
    vals = list(3.0 + np.cumsum(rng.normal(0, 0.02, 60)))
    vals[50] += 1.5                                       # salto isolado
    con = build(payload({"inad_total": [round(v, 4) for v in vals]}))
    warehouse.run_sql_models(con, prefixes=("02", "04"))
    a = con.execute("SELECT * FROM gold.alerts ORDER BY ref_month").df()
    flagged = a[a.is_alert]
    assert bool(a.loc[50, "is_alert"])                    # o salto é detectado
    assert not a.loc[a.n_base < 24, "is_alert"].any()     # sem base suficiente, nunca alerta
    assert len(flagged) <= 6                              # e o resto, calmo, quase não gera alerta
