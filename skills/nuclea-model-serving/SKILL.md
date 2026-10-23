---
name: nuclea-model-serving
description: Treina, registra no Unity Catalog e serve em tempo real um modelo de risco PJ da Nuclea (score de inadimplência por CNPJ) - tabela de features sem vazamento, treino LightGBM com MLflow, alias champion, endpoint serverless com inference table, função SQL score_cnpj via ai_query, e validação de latência e qualidade. Use quando pedirem modelo de score/risco/fraude, model serving, inferência em tempo real, ou ferramenta de score para agentes.
---

# Model serving com inferência em tempo real: score de inadimplência PJ

Carregue também `@nuclea-contexto-dados`. Escreva só no schema `lab_ml`, ou num schema seu.

## Passo 1: features (`lab_ml.features_pj`, uma linha por CNPJ, PK `cnpj`)
- **Fontes:**
  - `cadastro`: porte, setor, UF, idade, log do faturamento, aceita cartão
  - `cartoes.unidades_recebiveis`: valor constituído e comprometido, % comprometido, nº de credenciadoras
  - `contratos_gravames`, **só atributos de originação**: quantidade, valor contratado, taxa média, prazo médio, nº de financiadores
  - `boletos`: % vencido em aberto como beneficiário e como pagador, divergência de beneficiário
  - `duplicatas`: % sem NF-e validada, % negociada
  - `risco`: último score, consultas nos últimos 30 dias e no total, alertas e valor exposto
- **Alvo:** `rotulo_inadimplente` = CNPJ tem algum contrato `Inadimplente`.
  - Treine só com tomadores (CNPJs com algum gravame): cerca de 21,9 mil, com cerca de 6,9% de positivos.
- **Anti-vazamento (obrigatório):** **não** use `status_contrato` nem `saldo_devedor`. O saldo zera quando o contrato é liquidado e revela o status.
- `data_abertura` < 1900 é um problema de DQ conhecido: trunque o cálculo da idade.
- Ligue o CDF (`delta.enableChangeDataFeed`) para uma futura Online Feature Store.

Referência: [referencias/01_features.sql](referencias/01_features.sql).

## Passo 2: treino (job serverless, MLflow 3)
- LightGBM com `scale_pos_weight = sqrt(neg/pos)`, holdout estratificado de 20%. Reporte AUC, KS e lift no top 10%.
- Empacote como pyfunc que devolve `prob_inadimplencia`, `score = (1-prob)*1000` e `faixa_risco` (A a E, com cortes de prob. em 3%, 7%, 15% e 30%). Inclua `signature` e `input_example`.
- Registre no UC como `workshop_nuclea_genie_catalog.lab_ml.score_inadimplencia_pj` e defina o alias `champion`.
- **Dica de ambiente serverless:** use environment versão 4 e instale só `lightgbm` e `mlflow-skinny`. Fixar muitas versões fez a instalação falhar.

Referências: [referencias/02_train.py](referencias/02_train.py) e [referencias/03_submit_train.json](referencias/03_submit_train.json).

## Passo 3: endpoint `nuclea-score-inadimplencia`
- Serverless, tamanho Small, `scale_to_zero_enabled: true`.
- AI Gateway com inference table (`lab_ml.score_inadimplencia_payload`) e usage tracking.

Referência: [referencias/04_endpoint.json](referencias/04_endpoint.json). Para criar:
```bash
databricks serving-endpoints create --json @04_endpoint.json --profile nuclea-genie
```
Para trocar a versão do modelo: mova o alias **e** rode `serving-endpoints update-config` com a nova `entity_version`.

## Passo 4: inferência por CNPJ (`lab_ml.score_cnpj(cnpj STRING)`)
Uma função SQL busca a linha em `features_pj` e chama o endpoint com `ai_query(..., returnType => 'STRUCT<...>')`. Aceita CNPJ com ou sem máscara.

Ela serve igualmente para SQL, Genie, agentes (como UC function tool) e apps. Referência: [referencias/05_score_cnpj.sql](referencias/05_score_cnpj.sql).
```sql
SELECT * FROM workshop_nuclea_genie_catalog.lab_ml.score_cnpj('05.657.016/0001-95');
```
**Evolução:** para SLA abaixo de 100 ms fora do warehouse, publique `features_pj` numa Online Feature Store (Lakebase) e logue o modelo com `FeatureLookup`. Assim o endpoint aceita `{"cnpj": ...}` direto.

## Passo 5: validação (obrigatória)
- **Latência:** chame o endpoint com 20 CNPJs após o warmup e meça p50 e p95. Referência: cerca de 250 ms e 295 ms, medidos de um cliente local.
- **Sanidade:** a prob. média dos inadimplentes deve ser maior que a dos adimplentes (referência: 0,49 contra 0,14).
- **Monotonicidade das faixas:** a taxa observada deve subir de A para E.
- Leia a probabilidade como **ranking**, não como PD calibrada. Para PD, calibre com isotônica ou Platt.

Referência: [referencias/06_validate.py](referencias/06_validate.py).

## Permissões de quem consome
- `EXECUTE` em `lab_ml.score_cnpj`
- `SELECT` em `lab_ml.features_pj` e em `cadastro.empresas_pj`
- `CAN_QUERY` no endpoint. Num Databricks App, declare o endpoint como resource `serving_endpoint`.
