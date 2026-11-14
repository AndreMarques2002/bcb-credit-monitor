"""Catálogo de séries do SGS/Banco Central, caminhos e limiares de qualidade de dados."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(os.getenv("CM_DATA_DIR", "data"))
SITE_DIR = Path(os.getenv("CM_SITE_DIR", "site"))
REPORTS_DIR = Path(os.getenv("CM_REPORTS_DIR", "reports"))
SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
WAREHOUSE_PATH = DATA_DIR / "warehouse.duckdb"

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json&dataInicial={start}&dataFinal={end}"
START_DATE = "01/03/2011"          # início das séries de crédito do SGS (dd/mm/aaaa)


@dataclass(frozen=True)
class Series:
    code: int          # código no SGS
    key: str           # nome curto usado nas tabelas
    name: str          # nome oficial/descritivo
    unit: str
    kind: str          # "inad" | "juros" | "selic": define limites e alertas


SERIES: list[Series] = [
    Series(21082, "inad_total", "Inadimplência da carteira de crédito - Total", "%", "inad"),
    Series(21084, "inad_pf", "Inadimplência da carteira de crédito - Pessoas físicas - Total", "%", "inad"),
    Series(21083, "inad_pj", "Inadimplência da carteira de crédito - Pessoas jurídicas - Total", "%", "inad"),
    Series(21113, "inad_cheque_especial",
           "Inadimplência da carteira de crédito com recursos livres - Pessoas físicas - Cheque especial", "%", "inad"),
    Series(21119, "inad_consignado",
           "Inadimplência da carteira de crédito com recursos livres - Pessoas físicas - Crédito pessoal consignado total",
           "%", "inad"),
    Series(20714, "juros_total", "Taxa média de juros das operações de crédito - Total", "% a.a.", "juros"),
    Series(20715, "juros_pj", "Taxa média de juros das operações de crédito - Pessoas jurídicas - Total", "% a.a.", "juros"),
    Series(4189, "selic", "Taxa de juros - Selic acumulada no mês anualizada base 252", "% a.a.", "selic"),
]
BY_KEY = {s.key: s for s in SERIES}

# Limites de plausibilidade por tipo de série (erro se violados)
BOUNDS = {"inad": (0.0, 100.0), "juros": (0.0, 300.0), "selic": (0.0, 60.0)}
# Salto mensal (em p.p.) acima do qual o dado merece atenção (aviso)
JUMP_LIMIT = {"inad": 1.0, "juros": 3.0, "selic": 3.0}
# O BCB publica estes dados com cerca de 2 meses de defasagem
FRESHNESS_DAYS = 120
# Tolerância (p.p.) na checagem "total entre PF e PJ"
CONSISTENCY_TOL = 0.05
# Alerta estatístico: |z| >= Z_ALERT sobre a variação mensal, com pelo menos MIN_HISTORY meses de base
Z_ALERT = 2.0
MIN_HISTORY = 24
