"""Gera o painel estático (site/index.html) a partir das tabelas gold."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import BY_KEY  # noqa: E402

plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": .25})
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _n(x, d=2, sign=False) -> str:
    if x is None or pd.isna(x):
        return "n/d"
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace(".", ",")


def _mes(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{MESES[ts.month - 1]}/{ts.year}"


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def make_charts(df: pd.DataFrame, img_dir: Path) -> None:
    x = pd.to_datetime(df["ref_month"])

    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.plot(x, df["inad_total"], lw=2.2, label="Total", color="#0d6b86")
    ax.plot(x, df["inad_pf"], lw=1.5, label="Pessoas físicas", color="#b5402a")
    ax.plot(x, df["inad_pj"], lw=1.5, label="Pessoas jurídicas", color="#6b46c1")
    ax.set(title="Inadimplência da carteira de crédito (atraso > 90 dias)", ylabel="% da carteira")
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    _save(fig, img_dir / "inadimplencia.png")

    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.plot(x, df["inad_cheque_especial"], lw=1.8, label="Cheque especial (PF)", color="#b5402a")
    ax.plot(x, df["inad_consignado"], lw=1.8, label="Consignado (PF)", color="#0d6b86")
    ax.set(title="Inadimplência por produto, recursos livres, pessoas físicas", ylabel="% da carteira")
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    _save(fig, img_dir / "produtos.png")

    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.plot(x, df["juros_total"], lw=1.8, label="Juros médios, total", color="#0d6b86")
    ax.plot(x, df["juros_pj"], lw=1.5, label="Juros médios, PJ", color="#6b46c1")
    ax.plot(x, df["selic"], lw=1.8, label="Selic (anualizada)", color="#2f2f2f")
    ax.set(title="Juros do crédito e Selic", ylabel="% ao ano")
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    _save(fig, img_dir / "juros_selic.png")

    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ax.plot(x, df["spread_juros_selic"], lw=1.8, color="#c05621")
    ax.set(title="Diferença entre juros médios do crédito e Selic", ylabel="pontos percentuais")
    _save(fig, img_dir / "spread.png")


def _kpi(label: str, key: str, df: pd.DataFrame, metrics: pd.DataFrame, unit: str) -> str:
    m = metrics[metrics.series_key == key].sort_values("ref_month").iloc[-1]
    return (f'<div class="kpi"><div class="v">{_n(m.value)}<small> {unit}</small></div>'
            f'<div class="l">{html.escape(label)}</div>'
            f'<div class="d">{_n(m.mom, 2, True)} p.p. no mês · {_n(m.yoy, 2, True)} p.p. em 12 meses</div></div>')


def build_site(con, dq: pd.DataFrame, site_dir: Path, generated_at: datetime | None = None) -> Path:
    generated_at = generated_at or datetime.now()
    df = con.execute("SELECT * FROM gold.credit_monitor ORDER BY ref_month").df()
    metrics = con.execute("SELECT * FROM gold.series_metrics").df()
    alerts = con.execute("""SELECT * FROM gold.alerts WHERE is_alert ORDER BY ref_month DESC, abs(zscore) DESC
                            LIMIT 12""").df()
    site_dir.mkdir(parents=True, exist_ok=True)
    make_charts(df, site_dir / "img")
    df.to_csv(site_dir / "credit_monitor.csv", index=False)

    last = df.iloc[-1]
    inad = df.dropna(subset=["inad_total"])
    mx = inad.loc[inad["inad_total"].idxmax()]
    mn = inad.loc[inad["inad_total"].idxmin()]
    pctl = metrics[(metrics.series_key == "inad_total")].sort_values("ref_month").iloc[-1].pctl_hist
    texto = (f"Em {_mes(last.ref_month)}, a inadimplência total foi de {_n(last.inad_total)}% da carteira: "
             f"{_n(last.inad_pf)}% em pessoas físicas e {_n(last.inad_pj)}% em pessoas jurídicas. "
             f"Na série (desde {_mes(df.ref_month.iloc[0])}), o máximo foi {_n(mx.inad_total)}% em {_mes(mx.ref_month)} "
             f"e o mínimo {_n(mn.inad_total)}% em {_mes(mn.ref_month)}; o valor atual está acima de "
             f"{_n(100 * pctl, 0)}% dos meses da série.")
    juros = (f"Os juros médios do crédito estavam em {_n(last.juros_total)}% a.a., {_n(last.spread_juros_selic)} p.p. "
             f"acima da Selic ({_n(last.selic)}% a.a.).")

    kpis = "".join([
        _kpi("Inadimplência total", "inad_total", df, metrics, "%"),
        _kpi("Pessoas físicas", "inad_pf", df, metrics, "%"),
        _kpi("Pessoas jurídicas", "inad_pj", df, metrics, "%"),
        _kpi("Juros médios do crédito", "juros_total", df, metrics, "% a.a."),
        _kpi("Selic (anualizada)", "selic", df, metrics, "% a.a."),
    ])
    if alerts.empty:
        alert_html = "<p>Nenhum alerta estatístico no histórico recente.</p>"
    else:
        rows = "".join(f"<tr><td>{_mes(r.ref_month)}</td><td>{html.escape(BY_KEY[r.series_key].name)}</td>"
                       f"<td>{_n(r.mom, 2, True)}</td><td>{_n(r.zscore, 1, True)}</td></tr>"
                       for r in alerts.itertuples())
        alert_html = ("<table><tr><th>Mês</th><th>Série</th><th>Variação (p.p.)</th><th>z-score</th></tr>"
                      f"{rows}</table>")
    n_err = int(((dq.severidade == "error") & ~dq.ok).sum())
    n_warn = int(((dq.severidade == "warn") & ~dq.ok).sum())

    page = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de crédito e inadimplência no Brasil</title>
<style>
:root{{--bg:#f4f6f8;--ink:#0f1c28;--muted:#53626f;--rule:#d3dbe2;color-scheme:light dark}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0c141b;--ink:#e6edf2;--muted:#9aa9b6;--rule:#26343f}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.6 system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:2rem 1.25rem 4rem}}
h1{{font-size:2rem;letter-spacing:-.02em;margin:.2rem 0}} h2{{margin:2.4rem 0 .6rem;font-size:1.3rem}}
.sub{{color:var(--muted)}} .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin:1.6rem 0}}
.kpi{{border-top:2px solid var(--ink);padding-top:.6rem}} .kpi .v{{font-size:1.7rem;font-weight:700}}
.kpi small{{font-size:.9rem;font-weight:400;color:var(--muted)}} .kpi .l{{font-weight:600}} .kpi .d{{font-size:.85rem;color:var(--muted)}}
img{{max-width:100%;height:auto;background:#fff;border-radius:4px}} table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;padding:.4rem .5rem;border-bottom:1px solid var(--rule)}} .note{{color:var(--muted);font-size:.9rem}}
</style></head><body><main>
<h1>Monitor de crédito e inadimplência no Brasil</h1>
<p class="sub">Dados abertos do Banco Central (SGS), referência até {_mes(last.ref_month)} · gerado em {generated_at:%d/%m/%Y %H:%M}</p>
<div class="kpis">{kpis}</div>
<p>{html.escape(texto)}</p>
<img src="img/inadimplencia.png" alt="Inadimplência total, PF e PJ ao longo do tempo">
<h2>Produtos de crédito</h2><img src="img/produtos.png" alt="Inadimplência do cheque especial e do consignado">
<h2>Juros e Selic</h2><p>{html.escape(juros)}</p>
<img src="img/juros_selic.png" alt="Juros médios do crédito e Selic"><img src="img/spread.png" alt="Diferença entre juros e Selic">
<h2>Alertas estatísticos</h2>
<p class="note">Variação mensal que se afasta mais de 2 desvios-padrão das 36 variações anteriores da própria série (mínimo de 24 meses de base). É um sinal para investigar, não uma conclusão.</p>{alert_html}
<h2>Qualidade dos dados</h2><p>{len(dq)} checagens: {n_err} erro(s) e {n_warn} aviso(s) nesta execução. Dados em <a href="credit_monitor.csv">credit_monitor.csv</a>.</p>
<p class="note">Fonte: Banco Central do Brasil, Sistema Gerenciador de Séries Temporais (licença ODbL). Inadimplência = parcelas com atraso superior a 90 dias. Os valores podem ser revisados pelo BC; as séries têm cerca de 2 meses de defasagem.</p>
</main></body></html>"""
    out = site_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out
