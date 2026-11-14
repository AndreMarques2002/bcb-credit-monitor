import io
import json
import urllib.error

import pytest

from creditmonitor.ingest import IngestError, SgsClient


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(payload):
    def opener(url, timeout=None):
        return FakeResponse(json.dumps(payload).encode("utf-8"))
    return opener


GOOD = [{"data": "01/03/2011", "valor": "3.34"}, {"data": "01/04/2011", "valor": "3.40"}]


def test_fetch_parses_bcb_format():
    rows = SgsClient(opener=opener_returning(GOOD)).fetch(21082)
    assert rows == GOOD


def test_url_follows_sgs_pattern():
    url = SgsClient.url(21082, "01/03/2011", "31/12/2020")
    assert url == ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.21082/dados"
                   "?formato=json&dataInicial=01/03/2011&dataFinal=31/12/2020")


def test_retries_with_backoff_then_succeeds():
    calls, sleeps = {"n": 0}, []

    def flaky(url, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("falha temporária")
        return FakeResponse(json.dumps(GOOD).encode())

    rows = SgsClient(opener=flaky, retries=4, backoff=2, sleep=sleeps.append).fetch(1)
    assert rows == GOOD and calls["n"] == 3 and sleeps == [2, 4]


def test_gives_up_after_retries():
    def always_fails(url, timeout=None):
        raise TimeoutError("lento")

    with pytest.raises(IngestError, match="falhou após 3 tentativas"):
        SgsClient(opener=always_fails, retries=3, sleep=lambda s: None).fetch(1)


@pytest.mark.parametrize("bad", [[], {"erro": "x"}, [{"data": "01/01/2020"}], ["texto"], None])
def test_rejects_unexpected_payloads(bad):
    with pytest.raises(IngestError):
        SgsClient.validate(1, bad)


def test_invalid_json_is_retried_then_fails():
    def garbage(url, timeout=None):
        return FakeResponse(b"<html>manutencao</html>")

    with pytest.raises(IngestError):
        SgsClient(opener=garbage, retries=2, sleep=lambda s: None).fetch(1)
