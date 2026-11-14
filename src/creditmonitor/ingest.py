"""Cliente da API SGS do Banco Central e camada bronze (dado bruto + metadados de ingestão)."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from .config import SERIES, SGS_URL, START_DATE

log = logging.getLogger(__name__)


class IngestError(RuntimeError):
    pass


class SgsClient:
    """Baixa uma série do SGS com timeout, repetição e espera progressiva."""

    def __init__(self, opener=urllib.request.urlopen, retries: int = 4, backoff: float = 1.5,
                 timeout: float = 30, sleep=time.sleep):
        self.opener, self.retries, self.backoff, self.timeout, self.sleep = opener, retries, backoff, timeout, sleep

    @staticmethod
    def url(code: int, start: str = START_DATE, end: str | None = None) -> str:
        end = end or date.today().strftime("%d/%m/%Y")
        return SGS_URL.format(code=code, start=start, end=end)

    def fetch(self, code: int, start: str = START_DATE, end: str | None = None) -> list[dict]:
        url = self.url(code, start, end)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with self.opener(url, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return self.validate(code, payload)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as exc:
                last_error = exc
                log.warning("Série %s: tentativa %d/%d falhou (%s)", code, attempt, self.retries, exc)
                if attempt < self.retries:
                    self.sleep(self.backoff ** attempt)
        raise IngestError(f"Série {code}: falhou após {self.retries} tentativas ({last_error})")

    @staticmethod
    def validate(code: int, payload) -> list[dict]:
        """Garante o formato [{"data": "dd/mm/aaaa", "valor": "1.23"}, ...] e não-vazio."""
        if not isinstance(payload, list) or not payload:
            raise IngestError(f"Série {code}: resposta vazia ou em formato inesperado")
        if not all(isinstance(r, dict) and "data" in r and "valor" in r for r in payload):
            raise IngestError(f"Série {code}: registros sem os campos 'data' e 'valor'")
        return [{"data": str(r["data"]), "valor": str(r["valor"])} for r in payload]


def fetch_all(client, series=SERIES, start: str = START_DATE) -> dict[int, list[dict]]:
    """Baixa todas as séries do catálogo. `client` precisa ter `.fetch(code, start)`."""
    return {s.code: client.fetch(s.code, start) for s in series}


def save_raw_snapshot(raw: dict[int, list[dict]], data_dir: Path, ingested_at: datetime) -> Path:
    """Guarda o JSON bruto de cada série (auditoria e reprocessamento), um diretório por ingestão."""
    out = data_dir / "bronze" / ingested_at.strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    for code, rows in raw.items():
        (out / f"sgs_{code}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return out


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
