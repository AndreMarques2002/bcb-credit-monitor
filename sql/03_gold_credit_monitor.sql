-- Gold: painel mensal em formato largo, com spreads úteis para análise.
CREATE OR REPLACE TABLE gold.credit_monitor AS
WITH wide AS (
    SELECT
        ref_month,
        max(value) FILTER (WHERE series_key = 'inad_total')           AS inad_total,
        max(value) FILTER (WHERE series_key = 'inad_pf')              AS inad_pf,
        max(value) FILTER (WHERE series_key = 'inad_pj')              AS inad_pj,
        max(value) FILTER (WHERE series_key = 'inad_cheque_especial') AS inad_cheque_especial,
        max(value) FILTER (WHERE series_key = 'inad_consignado')      AS inad_consignado,
        max(value) FILTER (WHERE series_key = 'juros_total')          AS juros_total,
        max(value) FILTER (WHERE series_key = 'juros_pj')             AS juros_pj,
        max(value) FILTER (WHERE series_key = 'selic')                AS selic
    FROM silver.series_monthly
    GROUP BY ref_month
)
SELECT
    *,
    juros_total - selic          AS spread_juros_selic,   -- p.p.
    inad_pf - inad_pj            AS gap_inad_pf_pj,       -- p.p.
    inad_cheque_especial - inad_consignado AS gap_cheque_consignado
FROM wide
ORDER BY ref_month;
