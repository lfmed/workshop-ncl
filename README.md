# Workshop Núclea × Databricks: do arquivo ao agente, com Genie Code

Material do workshop em que o time Núclea constrói, com o **Genie Code**, um produto de dados sobre as bases sintéticas do workshop. O produto, em proposta, é o **Monitor de Carteira PJ com agentes**: a instituição pergunta em linguagem natural sobre a própria carteira de crédito com garantia em recebíveis e recebe um parecer com KPIs comparados com o mercado, safras, concentração, alertas precoces e score.

> Todos os dados são **sintéticos**. O nome do produto é de trabalho, não é um produto oficial da Núclea.

## A história em 4 atos
| Ato | Tema | Estado no workspace da demo |
|---|---|---|
| 1 | Ingestão massiva: Auto Loader + Lakeflow Spark Declarative Pipelines, serverless | pronto |
| 2 | Data Quality: expectations, quarentena, event log, monitor de anomalias | pronto |
| 3 | Score de inadimplência PJ em tempo real: MLflow, Unity Catalog, Model Serving, `score_cnpj` | pronto |
| **4** | **Agentes especialistas de crédito**: UC functions, sala Genie, Supervisor Agent, Genie Code + MCP | especialistas e sala de crédito prontos; Supervisor e MCP **ao vivo** |

## Workspace
- **URL:** https://fe-sandbox-workshop-nuclea-genie.cloud.databricks.com
- **Catálogo:** `workshop_nuclea_genie_catalog`, com os schemas de origem `boletos`, `cadastro`, `cartoes`, `credito`, `duplicatas`, `pix`, `risco` e os laboratórios `lab_ingestao`, `lab_ml`, `lab_credito`.
- **Volume:** 18 tabelas de origem, 5.186.912 linhas.

## Estrutura
```
apresentacao/   slides: PDF e PPTX (exportados do Google Slides) + versão HTML navegável (setas, N = notas, F = tela cheia)
roteiros/       roteiro_ao_vivo_ato4.html (apresentador) · roteiro_demo_genie_code.html (participantes, todos os atos)
skills/         6 skills do Genie Code (SKILL.md + referências)
AGENTS.md       instruções de projeto para agentes (Genie Code CLI e outros)
codigo/         implementação de referência
  ingestao_dq/            bundle (DAB): gerador de lotes, pipeline SDP, views de DQ, job (Atos 1 e 2)
  model_serving/          features, treino LightGBM, endpoint, score_cnpj, validação (Ato 3)
  monitoramento_credito/  carteira_contratos + 5 UC functions + sala Genie de crédito via API (genie/sala_credito.json) (Ato 4)
  app_nuclea_monitor/     app Flask + Lakebase com orquestrador por tool calling (referência do Ato 4)
migracao/       como os dados e as salas Genie foram levados de um workspace para outro
docs/           pesquisa sobre Genie Code e Genie Code CLI · roteiro em markdown
scripts/        run_sql.py (executa .sql no warehouse) · contraste_wcag.py
```

## Como usar as skills
**No Genie Code (UI do workspace):** copie a pasta `skills/` para `/Users/<seu-email>/.assistant/skills/`.
```bash
databricks workspace import-dir skills /Users/<seu-email>/.assistant/skills --profile <profile>
```
Depois abra o Genie Code, comece uma **nova conversa** e digite `@nuclea`.

| Skill | Para que serve |
|---|---|
| `nuclea-contexto-dados` | Mapa das tabelas, chaves (CNPJ e ISPB), regras e armadilhas. Carregue sempre |
| `nuclea-ingestao-massiva` | Ato 1 |
| `nuclea-data-quality` | Ato 2 |
| `nuclea-model-serving` | Ato 3 |
| `nuclea-monitoramento-credito` | Ato 4 |
| `nuclea-identidade-visual` | Cores Núclea (HEX, contraste) para apps, dashboards e slides |

**Na Genie Code CLI (terminal):** rode `genie` na raiz deste repositório. Ela lê o `AGENTS.md` e as skills em `.agents/skills/`, que é um link para `skills/`.

## Para replicar (participantes)
1. Abra `roteiros/roteiro_demo_genie_code.html` no navegador.
2. Preencha suas iniciais no topo da página: os prompts passam a usar o schema `lab_<iniciais>` e o endpoint `nuclea-score-<iniciais>`.
3. Siga os atos, copiando os prompts para o Genie Code e conferindo cada checkpoint.

Não escreva nos schemas de origem nem em `lab_ingestao`, `lab_ml` e `lab_credito`, que são da demo.

## Números de referência (para conferir)
| Ato | Resultado |
|---|---|
| 1 e 2 | bronze 2.262.765 = silver 2.259.624 + quarentena 2.031 + duplicadas 1.110; 19/19 reconciliações; 3.965 baixas com divergência de beneficiário (boletos adulterados) |
| 3 | AUC 0,652 · KS 0,234 · ~250–300 ms p50 |
| 4 (ISPB 42691787 · Varejo · Pequeno · Sudeste) | 622 contratos · R$ 27,92 mi · 4,02% contra 6.258 · R$ 260,33 mi · 4,64% no mercado |

## Observações
- **SQL functions na sala Genie:** se a UI não permitir anexá-las, crie a sala pela API (`databricks genie create-space --json @codigo/monitoramento_credito/genie/sala_credito.json`). O formato está explicado na skill `nuclea-monitoramento-credito`.
- O app `codigo/app_nuclea_monitor` foi implantado no workspace original do workshop, onde o catálogo se chama `stable_nuclea_workshop_catalog`. Para usá-lo em outro workspace, ajuste `app.yaml` e `genie_spaces.json`.
- **Migração de dados:** `read_files` acrescenta a coluna `_rescued_data`; use `SELECT * EXCEPT (_rescued_data)`, como em `migracao/02_criar_tabelas.sql`. Sem isso, o Auto Loader do Ato 1 falha.
- As cores seguem a skill `nuclea-identidade-visual`, cujos valores foram extraídos de material institucional público da Núclea. Não há brandbook público.
