# Catálogo de dados

Fonte: **Banco Central do Brasil, Sistema Gerenciador de Séries Temporais (SGS)**, publicado no portal de dados abertos
(licença ODbL). Acesso pela API:
`https://api.bcb.gov.br/dados/serie/bcdata.sgs.{código}/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa`

Todas as séries são **mensais**. Os códigos e nomes abaixo foram conferidos no catálogo de dados abertos do BCB.

| Chave | Código SGS | Série | Unidade |
|---|---|---|---|
| `inad_total` | 21082 | Inadimplência da carteira de crédito, total | % |
| `inad_pf` | 21084 | Inadimplência da carteira de crédito, pessoas físicas, total | % |
| `inad_pj` | 21083 | Inadimplência da carteira de crédito, pessoas jurídicas, total | % |
| `inad_cheque_especial` | 21113 | Inadimplência, recursos livres, pessoas físicas, cheque especial | % |
| `inad_consignado` | 21119 | Inadimplência, recursos livres, pessoas físicas, crédito pessoal consignado total | % |
| `juros_total` | 20714 | Taxa média de juros das operações de crédito, total | % a.a. |
| `juros_pj` | 20715 | Taxa média de juros das operações de crédito, pessoas jurídicas, total | % a.a. |
| `selic` | 4189 | Taxa de juros, Selic acumulada no mês anualizada base 252 | % a.a. |

**Definição de inadimplência (BCB):** percentual da carteira de crédito do Sistema Financeiro Nacional com pelo menos
uma parcela com atraso superior a 90 dias. **Juros médios:** taxa média das *novas* operações contratadas no período,
ponderada pelo valor das concessões.

## Camadas

| Camada | Tabela | Conteúdo |
|---|---|---|
| bronze | `bronze.sgs_raw` | Registros brutos como vieram da API (`data`, `valor` em texto) + `ingested_at` e `source_url`. Somente acrescenta. Os JSONs também são guardados em `data/bronze/<data-hora>/`. |
| silver | `silver.series_monthly` | Uma linha por série e mês, tipada (`ref_month` DATE, `value` DOUBLE). Se o BCB revisar um valor, vale a ingestão mais recente. |
| gold | `gold.series_metrics` | Por série e mês: variação no mês (`mom`) e em 12 meses (`yoy`), média móvel de 12 meses (`ma12`) e posição histórica (`pctl_hist`). |
| gold | `gold.credit_monitor` | Painel mensal em formato largo, com `spread_juros_selic`, `gap_inad_pf_pj` e `gap_cheque_consignado`. |
| gold | `gold.alerts` | z-score da variação mensal contra as 36 variações anteriores; `is_alert` quando |z| ≥ 2 com ao menos 24 meses de base. |

## Checagens de qualidade (`creditmonitor/dq.py`)

| Checagem | Camada | Severidade |
|---|---|---|
| Todas as séries do catálogo chegaram | silver | erro |
| Data e valor interpretáveis (última ingestão) | bronze | erro |
| Sem duplicatas na ingestão | bronze | aviso |
| Chave única (série, mês) | silver | erro |
| Valores plausíveis (inadimplência 0–100%, juros 0–300%, Selic 0–60%) | silver | erro |
| Sem meses faltando | silver | erro |
| Série atualizada (últimos 120 dias) | silver | aviso |
| Sem saltos mensais anormais (inadimplência > 1 p.p., juros e Selic > 3 p.p.) | silver | aviso |
| Inadimplência total entre PF e PJ (é uma média ponderada das duas) | silver | erro |

**Erros interrompem o pipeline antes da camada gold**: nenhum painel é publicado com dado que falhou.
