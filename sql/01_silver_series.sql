-- Silver: série mensal tipada e deduplicada.
-- Se a mesma série/mês aparece em mais de uma ingestão (revisão do BCB), vale a mais recente.
CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.series_monthly AS
SELECT
    m.series_key,
    m.kind,
    m.unit,
    CAST(date_trunc('month', try_strptime(b.data, '%d/%m/%Y')) AS DATE) AS ref_month,
    TRY_CAST(b.valor AS DOUBLE)                                         AS value,
    b.ingested_at
FROM bronze.sgs_raw AS b
JOIN meta.series    AS m ON m.series_code = b.series_code
WHERE try_strptime(b.data, '%d/%m/%Y') IS NOT NULL
  AND TRY_CAST(b.valor AS DOUBLE) IS NOT NULL
QUALIFY row_number() OVER (
            PARTITION BY b.series_code, date_trunc('month', try_strptime(b.data, '%d/%m/%Y'))
            ORDER BY b.ingested_at DESC, b.valor DESC) = 1;
