from datetime import datetime

import pandas as pd
import pytest

from creditmonitor import warehouse
from creditmonitor.config import BY_KEY

NOW = datetime(2026, 9, 15, 12, 0, 0)


def payload(values: dict[str, list[float]], start="2020-01-01") -> dict[int, list[dict]]:
    """Monta o formato da API ({data: dd/mm/aaaa, valor: str}) para as séries pedidas."""
    out = {}
    for key, vals in values.items():
        months = pd.date_range(start, periods=len(vals), freq="MS")
        out[BY_KEY[key].code] = [{"data": d.strftime("%d/%m/%Y"), "valor": str(v)} for d, v in zip(months, vals)]
    return out


def build(raw, ingested_at=NOW, con=None, silver=True):
    con = con or warehouse.connect(":memory:")
    warehouse.load_bronze(con, raw, ingested_at)
    if silver:
        warehouse.run_sql_models(con, prefixes=("01",))
    return con


@pytest.fixture()
def clean_raw():
    n = 40
    return payload({
        "inad_total": [3.0 + 0.01 * i for i in range(n)],
        "inad_pf": [4.0 + 0.01 * i for i in range(n)],
        "inad_pj": [2.0 + 0.01 * i for i in range(n)],
        "selic": [10.0] * n,
        "juros_total": [30.0] * n,
    })
