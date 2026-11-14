-- Gold: métricas por série (variação mensal e em 12 meses, média móvel e posição histórica).
-- A variação usa junção por mês calendário (e não LAG), para não errar caso haja meses faltando.
CREATE SCHEMA IF NOT EXISTS gold;

CREATE OR REPLACE TABLE gold.series_metrics AS
SELECT
    s.series_key,
    s.kind,
    s.ref_month,
    s.value,
    s.value - p1.value  AS mom,          -- variação no mês (p.p.)
    s.value - p12.value AS yoy,          -- variação em 12 meses (p.p.)
    CASE WHEN count(*) OVER w12 = 12 THEN avg(s.value) OVER w12 END AS ma12,
    percent_rank() OVER (PARTITION BY s.series_key ORDER BY s.value) AS pctl_hist
FROM silver.series_monthly AS s
LEFT JOIN silver.series_monthly AS p1
       ON p1.series_key = s.series_key
      AND p1.ref_month  = CAST(s.ref_month - INTERVAL 1 MONTH AS DATE)
LEFT JOIN silver.series_monthly AS p12
       ON p12.series_key = s.series_key
      AND p12.ref_month  = CAST(s.ref_month - INTERVAL 12 MONTH AS DATE)
WINDOW w12 AS (PARTITION BY s.series_key ORDER BY s.ref_month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);
