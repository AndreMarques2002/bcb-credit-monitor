"""Checagens de qualidade de dados (bronze e silver). Erros interrompem o pipeline; avisos só aparecem no relatório."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .config import BOUNDS, CONSISTENCY_TOL, FRESHNESS_DAYS, JUMP_LIMIT


@dataclass
class Check:
    name: str
    scope: str
    severity: str        # "error" | "warn"
    n_failed: int
    detail: str

    @property
    def passed(self) -> bool:
        return self.n_failed == 0


class DataQualityError(RuntimeError):
    pass


def _latest_batch(con) -> str:
    return "ingested_at = (SELECT max(ingested_at) FROM bronze.sgs_raw)"


def run_checks(con, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    checks: list[Check] = []

    def add(name, scope, severity, rows, detail_fn=lambda r: str(r)):
        n = len(rows)
        checks.append(Check(name, scope, severity, n, "" if n == 0 else "; ".join(detail_fn(r) for r in rows[:6])))

    # 1. Completude: toda série do catálogo chegou?
    rows = con.execute("""SELECT m.series_key FROM meta.series m
        LEFT JOIN (SELECT DISTINCT series_key FROM silver.series_monthly) x USING (series_key)
        WHERE x.series_key IS NULL""").fetchall()
    add("série presente", "silver", "error", rows, lambda r: r[0])

    # 2. Registros brutos que não viram data/valor válidos (última ingestão)
    n = con.execute(f"""SELECT count(*) FROM bronze.sgs_raw WHERE {_latest_batch(con)}
        AND (try_strptime(data, '%d/%m/%Y') IS NULL OR TRY_CAST(valor AS DOUBLE) IS NULL)""").fetchone()[0]
    checks.append(Check("data e valor válidos", "bronze", "error", n, f"{n} registros não interpretáveis" if n else ""))

    # 3. Duplicidade dentro da própria ingestão
    rows = con.execute(f"""SELECT series_code, data FROM bronze.sgs_raw WHERE {_latest_batch(con)}
        GROUP BY 1, 2 HAVING count(*) > 1""").fetchall()
    add("sem duplicatas na ingestão", "bronze", "warn", rows, lambda r: f"{r[0]}@{r[1]}")

    # 4. Unicidade na silver (série, mês)
    rows = con.execute("""SELECT series_key, ref_month FROM silver.series_monthly
        GROUP BY 1, 2 HAVING count(*) > 1""").fetchall()
    add("chave única (série, mês)", "silver", "error", rows, lambda r: f"{r[0]}@{r[1]}")

    # 5. Faixa de plausibilidade por tipo de série
    rows = []
    for kind, (lo, hi) in BOUNDS.items():
        rows += con.execute("""SELECT series_key, ref_month, value FROM silver.series_monthly
            WHERE kind = ? AND (value < ? OR value > ?)""", [kind, lo, hi]).fetchall()
    add("valores plausíveis", "silver", "error", rows, lambda r: f"{r[0]}@{r[1]}={r[2]}")

    # 6. Continuidade mensal (sem meses faltando)
    rows = con.execute("""SELECT series_key, datediff('month', min(ref_month), max(ref_month)) + 1 AS esperado,
        count(*) AS real FROM silver.series_monthly GROUP BY 1
        HAVING datediff('month', min(ref_month), max(ref_month)) + 1 <> count(*)""").fetchall()
    add("sem meses faltando", "silver", "error", rows, lambda r: f"{r[0]} ({r[2]} de {r[1]} meses)")

    # 7. Atualidade (o BCB publica com ~2 meses de defasagem)
    cutoff = today - timedelta(days=FRESHNESS_DAYS)
    rows = con.execute("""SELECT series_key, max(ref_month) FROM silver.series_monthly
        GROUP BY 1 HAVING max(ref_month) < ?""", [cutoff]).fetchall()
    add(f"atualizada (últimos {FRESHNESS_DAYS} dias)", "silver", "warn", rows, lambda r: f"{r[0]} até {r[1]}")

    # 8. Saltos mensais anormais (aviso: pode ser real, mas merece olhar)
    limit = " ".join(f"WHEN '{k}' THEN {v}" for k, v in JUMP_LIMIT.items())
    rows = con.execute(f"""WITH d AS (SELECT series_key, kind, ref_month,
            value - lag(value) OVER (PARTITION BY series_key ORDER BY ref_month) AS delta
        FROM silver.series_monthly)
        SELECT series_key, ref_month, round(delta, 3) FROM d
        WHERE abs(delta) > CASE kind {limit} END""").fetchall()
    add("sem saltos mensais anormais", "silver", "warn", rows, lambda r: f"{r[0]}@{r[1]} ({r[2]:+} p.p.)")

    # 9. Consistência entre séries: o total fica entre PF e PJ (é uma média ponderada das duas)
    rows = con.execute("""WITH w AS (SELECT ref_month,
            max(value) FILTER (WHERE series_key = 'inad_total') AS t,
            max(value) FILTER (WHERE series_key = 'inad_pf')    AS pf,
            max(value) FILTER (WHERE series_key = 'inad_pj')    AS pj
        FROM silver.series_monthly GROUP BY 1)
        SELECT ref_month, t, pf, pj FROM w
        WHERE t IS NOT NULL AND pf IS NOT NULL AND pj IS NOT NULL
          AND (t < least(pf, pj) - ? OR t > greatest(pf, pj) + ?)""", [CONSISTENCY_TOL, CONSISTENCY_TOL]).fetchall()
    add("inadimplência total entre PF e PJ", "silver", "error", rows,
        lambda r: f"{r[0]}: total {r[1]} fora de [{min(r[2], r[3])}, {max(r[2], r[3])}]")

    return pd.DataFrame([{"check": c.name, "camada": c.scope, "severidade": c.severity,
                          "ok": c.passed, "n_falhas": c.n_failed, "detalhe": c.detail} for c in checks])


def has_errors(df: pd.DataFrame) -> bool:
    return bool(((df["severidade"] == "error") & (~df["ok"])).any())


def to_markdown(df: pd.DataFrame, title: str = "Relatório de qualidade de dados") -> str:
    status = df.assign(status=df["ok"].map({True: "OK", False: "FALHA"}))
    n_err = int(((df.severidade == "error") & ~df.ok).sum())
    n_warn = int(((df.severidade == "warn") & ~df.ok).sum())
    lines = [f"# {title}\n", f"Erros: **{n_err}** · Avisos: **{n_warn}** · Checagens: {len(df)}\n",
             "| Checagem | Camada | Severidade | Status | Falhas | Detalhe |", "|---|---|---|---|---|---|"]
    for r in status.itertuples():
        lines.append(f"| {r.check} | {r.camada} | {r.severidade} | {r.status} | {r.n_falhas} | {r.detalhe} |")
    return "\n".join(lines) + "\n"
