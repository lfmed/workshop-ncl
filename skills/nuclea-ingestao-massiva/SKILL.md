---
name: nuclea-ingestao-massiva
description: Constrói um ingestor massivo de bases da Nuclea com Auto Loader e Lakeflow Spark Declarative Pipelines serverless (landing em Volume -> bronze -> silver -> gold), orientado a metadados, com schema evolution, dedup em streaming, liquid clustering, ingestão incremental e deploy via Declarative Automation Bundle. Use quando pedirem pipeline de ingestão, Auto Loader, carga de arquivos CSV/JSON/Parquet, medalhão, CDC/streaming ou boas práticas para ingerir muitas bases/arquivos.
---

# Ingestor massivo: Auto Loader + Lakeflow SDP

Carregue também `@nuclea-contexto-dados`, e `@nuclea-data-quality` para as expectations e a quarentena. Escreva só em `lab_ingestao`, ou num schema seu.

## Arquitetura de referência
```
Volume lab_ingestao.landing/<entidade>/lote_NNN/*.{csv,json,parquet}
  -> bronze_<entidade>   (Auto Loader: tudo que chegou + _rescued_data + metadados do arquivo)
  -> quarentena_<entidade> (registros que violam regra drop, com _motivos)
  -> silver_<entidade>   (dedup + expectations fail/drop/warn)
  -> gold_*              (materialized views: posição diária por UF/região/setor/porte)
Job: gerar_lotes -> pipeline -> views_dq
```

## Passo 1: simular a chegada de arquivos
Exporte as tabelas de origem para o Volume em lotes, um por mês, com um formato por entidade:
- `boletos_registro` e `boletos_baixas` em CSV
- `unidades_recebiveis` em JSON
- `empresas_pj` em Parquet

Rode como job **serverless**, não localmente. Injete problemas controlados e grave o gabarito em `manifesto_injecoes`. No último lote, inclua uma coluna nova para testar o schema drift.

Referência: [referencias/gerar_lotes.py](referencias/gerar_lotes.py).

## Passo 2: ingestor orientado a metadados
Cada base é uma entrada num dicionário `ENTIDADES` com `formato`, `opcoes`, `hints`, `cluster_by` e `chaves_dedup`. As funções-fábrica criam bronze, silver e quarentena para cada entrada. Referência: [referencias/entidades.py](referencias/entidades.py).

Para centenas de bases, mova essa configuração para uma tabela Delta de controle.

## Passo 3: bronze com Auto Loader (`from pyspark import pipelines as dp`)
- `spark.readStream.format("cloudFiles")` com estas opções:
  - `cloudFiles.format`
  - `cloudFiles.schemaHints`, com **CNPJ, ISPB e IDs sempre como STRING**; inferir como número perde os zeros à esquerda
  - `cloudFiles.schemaEvolutionMode = addNewColumns`
  - `rescuedDataColumn = _rescued_data`
- Acrescente os metadados `_metadata.file_path`, `file_size` e `file_modification_time`, mais o lote e `_ingerido_em`.
- Use `cluster_by` com as colunas de filtro mais comuns (data + CNPJ).

Referência: [referencias/bronze.py](referencias/bronze.py).

## Passo 4: silver com dedup e gold
- **Dedup em streaming com chave FIXA** (`chaves_dedup`), **nunca** `dropDuplicates(df.columns)`.
  - Uma coluna nova muda a chave do estado e quebra o flow com `STATE_STORE_KEY_SCHEMA_NOT_COMPATIBLE`. Isso aconteceu de verdade no workshop.
- Na gold, use `@dp.materialized_view`.
  - Para refresh incremental das MVs, habilite `delta.enableRowTracking` nas silvers. Sem isso, a MV é recalculada por inteiro.

Referências: [referencias/silver.py](referencias/silver.py) e [referencias/gold.py](referencias/gold.py).

## Passo 5: deploy com bundle (DAB)
Referências: [referencias/databricks.yml](referencias/databricks.yml), [ingestao.pipeline.yml](referencias/ingestao.pipeline.yml), [orquestracao.job.yml](referencias/orquestracao.job.yml) e [landing.volume.yml](referencias/landing.volume.yml).
```bash
databricks bundle validate --profile nuclea-genie
databricks bundle deploy   --profile nuclea-genie
databricks bundle run orquestracao --profile nuclea-genie                 # carga inicial (lotes 1 a 5)
databricks bundle run orquestracao --params lotes=6 --profile nuclea-genie # novo lote -> incremental
```
Use pipeline `serverless: true`, `catalog` e `schema` explícitos, e publique o event log no UC (`event_log`).

## Passo 6: valide o incremental (obrigatório)
1. Em `vw_dq_ingestao_por_update`, o update do lote novo escreve no bronze **só** as linhas do lote novo.
2. A soma dos updates bate com o total do bronze. Referência: 1.855.738 + 316.882 + 90.145 = 2.262.765.
3. A coluna nova aparece só nas linhas do lote novo, e os lotes antigos ficam com NULL.
4. Reconciliação: arquivos = bronze = silver + quarentena + duplicadas (ver `@nuclea-data-quality`).

## Boas práticas para ingestão massiva
1. **Use Auto Loader**, não `COPY INTO` nem listagem manual: ele mantém checkpoint exactly-once.
   - Directory listing atende milhares de arquivos.
   - Para milhões de arquivos, use **file events** (`cloudFiles.useManagedFileEvents=true`).
2. **Escolha o modo de schema evolution conscientemente:**
   - `addNewColumns` evolui o schema e reinicia o stream (update com causa `SCHEMA_CHANGE`).
   - `rescue` congela o schema.
   - `failOnNewColumns` serve para contratos rígidos.
3. **Arquivos de 100 MB a 1 GB** na landing. Na primeira carga histórica, controle o micro-batch com `maxFilesPerTrigger` ou `maxBytesPerTrigger`.
4. **Liquid clustering** (`CLUSTER BY` ou `CLUSTER BY AUTO`) no lugar de partição + Z-ORDER. Combine com predictive optimization.
5. **Serverless:** sem dimensionar cluster. Aqui, 1,86 milhão de linhas levou cerca de 2 minutos no primeiro update.
6. **Evite full refresh:** ele apaga o estado dos streams. Corrija o código e deixe o checkpoint retomar.
