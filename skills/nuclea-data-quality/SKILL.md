---
name: nuclea-data-quality
description: Implementa Data Quality em camadas para as bases da Nuclea - expectations fail/drop/warn em Lakeflow SDP a partir de um catálogo único de regras, tabela de quarentena com motivo, métricas de aprovação a partir do event log, reconciliação contra o gabarito, monitor de anomalias (data quality monitoring) no schema e checagens de perfil em tabelas existentes. Use quando pedirem regras de qualidade, expectations, quarentena, monitoramento de qualidade/anomalias, profiling ou investigação de dados inconsistentes.
---

# Data Quality em camadas

Carregue também `@nuclea-contexto-dados`, e `@nuclea-ingestao-massiva` se a DQ for dentro do pipeline.

## Camada 1: catálogo único de regras (`dq_regras.py`)
Um dicionário `REGRAS[entidade][fail|drop|warn] = {nome_da_regra: expressao_sql}` alimenta as expectations **e** a quarentena. Assim a regra nunca diverge entre as duas.

| Ação | Quando usar | Exemplos |
|---|---|---|
| `fail` (`@dp.expect_all_or_fail`) | invariante do processo | lote identificado, arquivo rastreável |
| `drop` (`@dp.expect_all_or_drop`) → quarentena | registro inválido | chave nula, valor ≤ 0, vencimento < registro, CNPJ ≠ 14 dígitos, `_rescued_data` não nulo, data de abertura fora de [1900, hoje] |
| `warn` (`@dp.expect_all`) | alerta de negócio | espécie desconhecida, valor > R$ 1 mi, comprometido > constituído, divergência de beneficiário |

Embrulhe toda regra em `coalesce(expr, false)`: **NULL conta como violação**.

Referência: [referencias/dq_regras.py](referencias/dq_regras.py).

## Camada 2: quarentena com motivo
`quarentena_<entidade>` lê o bronze e grava os registros que violam alguma regra `drop`, com a coluna `_motivos` (array com os nomes das regras violadas). Nada se perde em silêncio.

Referência: [referencias/quarentena.py](referencias/quarentena.py).

## Camada 3: métricas pelo event log
Publique o event log do pipeline no UC (`event_log: {name: event_log_ingestao}`) e crie as views:
- `vw_dq_expectativas`: `flow_progress.data_quality.expectations` explodido por regra
- `vw_dq_taxa_aprovacao`: % aprovado por tabela, regra e ação
- `vw_dq_ingestao_por_update`: linhas escritas por update e por tabela (prova o incremental)
- `vw_dq_quarentena_motivos`: registros por entidade, lote e motivo
- `vw_dq_reconciliacao`: bronze = silver + quarentena + duplicadas, comparado com `manifesto_injecoes`

Referências: [referencias/criar_views_dq.py](referencias/criar_views_dq.py) e [referencias/validacao.sql](referencias/validacao.sql).

## Camada 4: monitor de anomalias no schema
```bash
SID=$(databricks schemas get workshop_nuclea_genie_catalog.lab_ingestao -p nuclea-genie -o json | jq -r .schema_id)
databricks data-quality create-monitor -p nuclea-genie \
  --json "{\"object_type\":\"schema\",\"object_id\":\"$SID\",\"anomaly_detection_config\":{}}"
databricks data-quality get-monitor schema $SID -p nuclea-genie
```
O monitor aprende o padrão de freshness e de volume de cada tabela e sinaliza desvios. Os resultados ficam em Catalog Explorer → schema → Quality, e ele precisa de histórico para ter sinal. Neste workspace, `list-monitor` não funciona; use `get-monitor`.

## Camada 5: perfil de tabelas já existentes (sem pipeline)
Quando a pergunta for "esses dados estão bons?", rode checagens SQL diretas e reporte em tabela:
- **Unicidade de chave:** `count(*) - count(DISTINCT pk)`
- **Integridade referencial:** LEFT JOIN contra `cadastro.empresas_pj` ou `cadastro.participantes`, contando órfãos
- **Domínio e intervalo:** datas antes de 1900 ou no futuro, valores ≤ 0, CNPJ fora de `^[0-9]{14}$`
- **Coerência entre colunas:** por exemplo, `faixa_risco` comparada com as faixas de `score_pj`

Problemas conhecidos que essas checagens devem encontrar:
- 1 empresa aberta em 1888
- `faixa_risco` incoerente com `score_pj`: a faixa D vai de 106 a 799
- Nomes de participante repetidos em ISPBs diferentes
- Gravames e consultas **sem** órfãos contra `empresas_pj`

## Validação esperada (referência do workshop)
- `vw_dq_reconciliacao`: **19 de 19** combinações entidade × lote com `confere = true`.
- Totais: bronze 2.262.765, quarentena 2.031, duplicadas 1.110, silver 2.259.624.
- **Regras fail:** 100% de aprovação.
- **Regras drop:** entre 99,95% e 99,99%, batendo com a quarentena por motivo.
- **Regras warn:** `sem_divergencia_beneficiario` reprova 3.965 baixas. É sinal **real** de boleto adulterado, não injeção, e merece um alerta de negócio.
