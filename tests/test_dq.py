from datetime import date

import pytest

from creditmonitor import dq
from creditmonitor.config import BY_KEY
from creditmonitor.synthetic import make_payloads

from .conftest import build, payload

TODAY = date(2023, 6, 1)


def failed(df, name):
    row = df[df.check.str.startswith(name)].iloc[0]
    return not row.ok


def test_clean_data_has_no_errors(clean_raw):
    df = dq.run_checks(build(clean_raw), TODAY)
    # 'série presente' falha aqui porque o fixture só traz 5 das 8 séries: é o único erro esperado
    assert set(df[(df.severidade == "error") & ~df.ok].check) == {"série presente"}


def test_synthetic_full_catalog_passes():
    df = dq.run_checks(build(make_payloads(end="2026-07")), date(2026, 9, 15))
    assert not dq.has_errors(df) and df.ok.all()


def test_detects_missing_month(clean_raw):
    code = BY_KEY["inad_total"].code
    del clean_raw[code][10]
    assert failed(dq.run_checks(build(clean_raw), TODAY), "sem meses faltando")


def test_detects_out_of_range(clean_raw):
    clean_raw[BY_KEY["inad_pf"].code][5]["valor"] = "120.0"
    assert failed(dq.run_checks(build(clean_raw), TODAY), "valores plausíveis")


def test_detects_total_outside_pf_pj(clean_raw):
    clean_raw[BY_KEY["inad_total"].code][7]["valor"] = "9.0"       # PF = ~4,07 e PJ = ~2,07
    df = dq.run_checks(build(clean_raw), TODAY)
    assert failed(df, "inadimplência total entre PF e PJ") and dq.has_errors(df)


def test_detects_stale_series_as_warning(clean_raw):
    df = dq.run_checks(build(clean_raw), date(2030, 1, 1))
    row = df[df.check.str.startswith("atualizada")].iloc[0]
    assert (not row.ok) and row.severidade == "warn"


def test_detects_monthly_jump_as_warning(clean_raw):
    clean_raw[BY_KEY["selic"].code][20]["valor"] = "16.0"           # de 10 para 16
    row = dq.run_checks(build(clean_raw), TODAY).query("check.str.startswith('sem saltos')", engine="python").iloc[0]
    assert (not row.ok) and row.severidade == "warn"


def test_detects_unparseable_bronze_rows(clean_raw):
    clean_raw[BY_KEY["selic"].code][3]["valor"] = "abc"
    assert failed(dq.run_checks(build(clean_raw), TODAY), "data e valor válidos")


def test_detects_duplicates_within_a_batch(clean_raw):
    clean_raw[BY_KEY["selic"].code].append(dict(clean_raw[BY_KEY["selic"].code][0]))
    assert failed(dq.run_checks(build(clean_raw), TODAY), "sem duplicatas")


def test_markdown_report_lists_failures(clean_raw):
    clean_raw[BY_KEY["inad_pf"].code][5]["valor"] = "120.0"
    md = dq.to_markdown(dq.run_checks(build(clean_raw), TODAY))
    assert "FALHA" in md and "valores plausíveis" in md and "Erros:" in md
