"""Gerador SINTÉTICO de payloads no formato da API do SGS. Serve para testes, CI e demonstração offline.

NÃO são dados reais do Banco Central e não devem ser usados para análise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SERIES


def make_payloads(end: str = "2026-07", seed: int = 42) -> dict[int, list[dict]]:
    rng = np.random.default_rng(seed)
    months = pd.date_range("2011-03-01", f"{end}-01", freq="MS")
    n = len(months)

    def cycle(scale: float, phi: float = 0.97) -> np.ndarray:
        x = np.zeros(n)
        for t in range(1, n):
            x[t] = phi * x[t - 1] + rng.normal(0, scale)
        return x

    pf = 4.0 + cycle(0.12)
    pj = 2.6 + cycle(0.08)
    w = 0.55 + 0.05 * np.sin(np.linspace(0, 6, n))          # peso da carteira PF no total
    total = w * pf + (1 - w) * pj + rng.normal(0, 0.01, n)   # média ponderada: sempre entre PF e PJ
    selic = np.empty(n)
    selic[0] = 11.0
    for t in range(1, n):
        step = rng.choice([0, 0, 0, -0.5, 0.5, 1.0, -1.0], p=[.55, .1, .1, .05, .1, .05, .05])
        selic[t] = np.clip(selic[t - 1] + step, 2.0, 15.0)

    values = {
        "inad_total": total, "inad_pf": pf, "inad_pj": pj,
        "inad_cheque_especial": 11.0 + cycle(0.15), "inad_consignado": 2.3 + cycle(0.04),
        "juros_total": 22.0 + 0.8 * selic + cycle(0.3), "juros_pj": 16.0 + 0.6 * selic + cycle(0.25),
        "selic": selic,
    }
    dates = [d.strftime("%d/%m/%Y") for d in months]
    return {s.code: [{"data": d, "valor": f"{v:.2f}"} for d, v in zip(dates, np.round(values[s.key], 2))]
            for s in SERIES}


class SyntheticClient:
    """Substitui o SgsClient nos testes: mesma interface `.fetch(code, start)`."""

    def __init__(self, end: str = "2026-07", seed: int = 42):
        self._payloads = make_payloads(end, seed)

    def fetch(self, code: int, start: str = "01/03/2011", end: str | None = None) -> list[dict]:
        return list(self._payloads[code])
