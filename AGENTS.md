# Workshop Nuclea: instruções para agentes (Genie Code CLI e outros)

- Workspace: profile do Databricks CLI apontando para https://fe-sandbox-workshop-nuclea-genie.cloud.databricks.com.
- Catálogo: `workshop_nuclea_genie_catalog`. Dados **sintéticos**, período de 01/04/2026 a 30/09/2026 (data de referência 2026-09-30).
- **Nunca altere** os schemas de origem: `boletos`, `cadastro`, `cartoes`, `credito`, `duplicatas`, `pix`, `risco`.
- **Implementação de referência (não sobrescrever):** `lab_credito`, `lab_ml`, `lab_ingestao`, o endpoint `nuclea-score-inadimplencia` e o app `nuclea-monitor`.
- **Exercícios do roteiro:** use o schema `lab_<suas_iniciais>` e nomes de recurso com o sufixo `-<suas_iniciais>`.
- Prefira serverless: SQL warehouse `416525bdb6d93a9b` (Serverless Starter Warehouse), jobs e pipelines serverless.
- Faça o deploy de pipelines e jobs com Declarative Automation Bundles (`databricks bundle ...`).
- Web apps em Flask + Jinja2 + Gunicorn como Databricks App, com estado no Lakebase. **Não use Streamlit.**
- Todo código e artefato fica dentro desta pasta. Scripts auxiliares vão em `scripts/`.
- Valide sempre com SQL contra os números de referência das skills antes de dar uma tarefa por concluída.

Skills do projeto, em `skills/` (com link em `.agents/skills/` para a Genie Code CLI):
- `nuclea-contexto-dados`: mapa das tabelas, regras de negócio e armadilhas conhecidas
- `nuclea-ingestao-massiva`: tema 6, Auto Loader + SDP
- `nuclea-data-quality`: tema 4, expectations, quarentena, event log e monitor de anomalias
- `nuclea-model-serving`: tema 5, score de inadimplência em tempo real
- `nuclea-monitoramento-credito`: tema 2, agentes especialistas de carteira de crédito
- `nuclea-identidade-visual`: código de cores Núclea (HEX oficiais, contraste, tokens CSS). Use em todo app, dashboard ou slide
