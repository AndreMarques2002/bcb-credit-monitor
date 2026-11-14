-- Gold: alerta estatístico. Compara a variação mensal com as 36 variações anteriores da mesma série
-- (sem incluir o mês atual). |z| >= 2 com pelo menos 24 meses de base vira alerta.
CREATE OR REPLACE TABLE gold.alerts AS
WITH d AS (
    SELECT
        series_key, kind, ref_month, value, mom,
        avg(mom)         OVER w AS mu,
        stddev_samp(mom) OVER w AS sd,
        count(mom)       OVER w AS n_base
    FROM gold.series_metrics
    WINDOW w AS (PARTITION BY series_key ORDER BY ref_month ROWS BETWEEN 36 PRECEDING AND 1 PRECEDING)
)
SELECT
    series_key, kind, ref_month, value, mom,
    (mom - mu) / nullif(sd, 0) AS zscore,
    n_base,
    coalesce(n_base >= 24 AND abs((mom - mu) / nullif(sd, 0)) >= 2, FALSE) AS is_alert
FROM d;
