# Roteiro: temas 6, 4, 5 e 2 com Genie Code e Genie Code CLI

Este roteiro refaz, com os agentes da Databricks, o que já está implementado como referência no workspace `nuclea-workshop`. Cada etapa traz duas trilhas e um checkpoint:
- **Genie Code:** o agente dentro do workspace (notebook, SQL editor, Lakeflow Pipelines Editor, Catalog Explorer).
- **Genie CLI:** o Genie Code CLI no terminal local.
- **Checkpoint:** a validação, com o número esperado.

Ordem recomendada: **6 → 4 → 5 → 2**. A ingestão alimenta a qualidade, e o score do tema 5 vira ferramenta do agente de crédito do tema 2.

> **Regra de ouro:** faça os exercícios no schema `lab_<iniciais>` (exemplo: `lab_lm`) e nomeie os recursos com o sufixo `-<iniciais>`. Não sobrescreva a referência: `lab_ingestao`, `lab_ml`, `lab_credito`, `nuclea-score-inadimplencia` e `nuclea-monitor`.

---

## 0. Preparação (15 min)

### 0.1 Skills no workspace (Genie Code)
As 6 skills já estão instaladas na minha pasta de usuário: `/Users/leandro.medeiros@databricks.com/.assistant/skills/`.

| Skill | Para que serve |
|---|---|
| `@nuclea-contexto-dados` | Mapa das tabelas, regras e armadilhas. **Sempre carregar** |
| `@nuclea-ingestao-massiva` | Tema 6 |
| `@nuclea-data-quality` | Tema 4 |
| `@nuclea-model-serving` | Tema 5 |
| `@nuclea-monitoramento-credito` | Tema 2 |
| `@nuclea-identidade-visual` | Cores Núclea para apps, dashboards e slides |

**Para outros participantes:** cada um copia para a própria pasta.
```bash
databricks workspace export-dir /Users/leandro.medeiros@databricks.com/.assistant/skills ./skills --profile nuclea-workshop
databricks workspace import-dir ./skills /Users/<email>/.assistant/skills --profile nuclea-workshop
```
Um admin também pode publicar para todo o workspace em `/Workspace/.assistant/skills/`. **Isso torna as skills visíveis para todos;** decida antes.

**Teste:** abra o Genie Code (painel lateral), comece uma **nova conversa** e digite `@nuclea` para ver as skills sugeridas. Pergunte: *"@nuclea-contexto-dados quais tabelas eu uso para medir a inadimplência de uma carteira?"*. Se uma skill não aparecer, faça um hard refresh no navegador; edições só valem em conversas novas.

**Opcional:** crie `/Users/<email>/.assistant_instructions.md` com as regras do `AGENTS.md`: não alterar a origem, usar serverless, não usar Streamlit, sempre validar.

### 0.2 Genie Code CLI (terminal)
```bash
# instalar (Beta; requer Databricks CLI >= 1.0)
curl -fsSL https://github.com/databricks/genie-code-cli/releases/latest/download/install.sh | bash
genie --version
cd ~/ncworkshop        # pasta com AGENTS.md e .agents/skills/
genie                  # na 1ª execução, escolha o profile nuclea-workshop
```
- A CLI lê o `AGENTS.md` da raiz e as skills de `.agents/skills/`, que já foram copiadas para este projeto. Ela **não** lê as skills do workspace.
- Para ter as skills em qualquer pasta: `cp -R .agents/skills/* ~/.genie/skills/`.
- Dentro da sessão: `/mcp` lista as ferramentas, `/resume` retoma uma sessão anterior, e `/import` traz a configuração do Claude Code ou do Cursor.
- Para conferir resultados sem sair do terminal: `databricks genie ask "..." --include-sql --profile nuclea-workshop`, que conversa com as salas Genie.

**Limitações conhecidas (Beta):**
- O modelo é fixo, gerenciado pela Databricks.
- Token expirado gera 401 nas ferramentas; nesse caso, saia e reabra o `genie`.
- Não funciona em sessões por túnel SSH.

---

## Tema 6: Ingestor massivo (45 min)

**Objetivo:** arquivos chegando em lotes num Volume, Auto Loader, bronze, silver e gold, tudo serverless, com ingestão incremental e schema drift.

### Trilha Genie Code
1. **Notebook novo:**
   > @nuclea-ingestao-massiva @nuclea-contexto-dados Crie o schema `lab_<iniciais>` e o volume `landing`. Escreva e rode, em compute serverless, um gerador que exporte `boletos.boletos_registro` (CSV), `boletos.boletos_baixas` (CSV), `cartoes.unidades_recebiveis` (JSON) e `cadastro.empresas_pj` (Parquet) em lotes mensais (`<entidade>/lote_NNN/`), injetando os problemas descritos na skill e gravando o gabarito em `manifesto_injecoes`. Gere só os lotes 1 a 5.
2. **Lakeflow Pipelines Editor** (New → ETL pipeline, serverless, catálogo `workshop_nuclea_genie_catalog`, schema `lab_<iniciais>`):
   > @nuclea-ingestao-massiva Crie um pipeline Python orientado a metadados (`entidades.py`) com bronze via Auto Loader (schemaHints com CNPJ/ISPB como STRING, `addNewColumns`, `_rescued_data`, metadados do arquivo), silver com dedup por chave fixa e gold com a posição diária de boletos e UR por UF, região, setor e porte. Use liquid clustering.
   - Rode o pipeline pelo editor e acompanhe o grafo.
3. **Novo lote:**
   > Gere o lote 6 com a coluna nova `id_registradora` nas URs e rode o pipeline de novo.

### Trilha Genie CLI
```text
> @nuclea-ingestao-massiva Crie em tema6_<iniciais>/ um Declarative Automation Bundle com: volume landing,
  job serverless gerador de lotes, pipeline SDP serverless (bronze/silver/gold) e job de orquestração
  gerar_lotes -> pipeline. Schema lab_<iniciais>. Valide, faça deploy e rode a carga inicial (lotes 1-5).
> Agora rode a orquestração com lotes=6 e me mostre, por update do pipeline, quantas linhas foram escritas no bronze.
```
A CLI edita os arquivos localmente e roda `databricks bundle validate`, `deploy` e `run`. Aprove cada comando.

### Checkpoint 6
- O update do lote 6 escreve no bronze **só** as linhas do lote 6, sem reprocessar. Referência: 316.882 de boletos e baixas mais 90.145 de UR.
- A coluna `id_registradora` existe e só está preenchida no lote 6.
- **Se** a silver de UR falhar com `STATE_STORE_KEY_SCHEMA_NOT_COMPATIBLE`: a dedup está usando `df.columns`. Peça ao agente para fixar `chaves_dedup`. É a lição do tema; não faça full refresh.

---

## Tema 4: Data Quality (30 min)

### Trilha Genie Code
1. **Pipelines Editor** (no mesmo pipeline):
   > @nuclea-data-quality Crie `dq_regras.py` como catálogo único de regras fail/drop/warn por entidade (todas com `coalesce(..., false)`), aplique como expectations na silver e crie `quarentena_<entidade>` com a coluna `_motivos`. Publique o event log no UC como `event_log_ingestao`.
2. **SQL editor:**
   > @nuclea-data-quality Crie as views `vw_dq_taxa_aprovacao`, `vw_dq_quarentena_motivos` e `vw_dq_reconciliacao` (bronze = silver + quarentena + duplicadas comparado com `manifesto_injecoes`).
3. **Catalog Explorer** → schema `lab_<iniciais>` → aba **Quality**: habilite o monitor de anomalias. Pela CLI, use o comando da skill.
4. **Perfil sem pipeline** (SQL editor):
   > @nuclea-data-quality Faça um perfil de qualidade de `cadastro.empresas_pj` e `risco.consultas_cnpj`: unicidade, órfãos, domínio de datas e valores, e coerência entre `faixa_risco` e `score_pj`.

### Trilha Genie CLI
```text
> @nuclea-data-quality Adicione ao bundle do tema 6 as expectations a partir de dq_regras.py, as tabelas de quarentena,
  o event log no UC e uma task que cria as views vw_dq_*. Faça deploy, rode e me mostre vw_dq_reconciliacao.
> Habilite o monitor de anomalias no schema lab_<iniciais> e confirme com get-monitor.
```

### Checkpoint 4
- `vw_dq_reconciliacao`: todas as combinações entidade × lote com `confere = true`. Na referência foram 19 de 19.
- **Regras fail:** 100%. **Regras drop:** 99,95% a 99,99%, batendo com a quarentena.
- **Regra warn `sem_divergencia_beneficiario`:** cerca de 3.965 baixas. É fraude real (boleto adulterado), não injeção; discuta isso com o grupo.
- **O perfil deve achar:**
  - a empresa aberta em 1888
  - a `faixa_risco` incoerente com o score
  - nomes de participante repetidos em ISPBs diferentes

---

## Tema 5: Model serving em tempo real (45 min)

### Trilha Genie Code
1. **Notebook com o Data Science agent:**
   > @nuclea-model-serving Crie `lab_<iniciais>.features_pj` (uma linha por CNPJ) conforme a skill, **sem** usar `status_contrato` nem `saldo_devedor`. Treine um LightGBM para `rotulo_inadimplente` apenas com tomadores, reporte AUC, KS e lift no top 10%, e registre no UC como `lab_<iniciais>.score_inadimplencia_pj` com alias `champion`, signature e input_example.
   - Peça também: *"explique as 10 features mais importantes"* e *"existe algum vazamento?"*.
2. **Serving** (UI ou agente):
   > Crie o endpoint serverless `nuclea-score-<iniciais>` (Small, scale-to-zero) com inference table e usage tracking no AI Gateway.
3. **SQL editor:**
   > @nuclea-model-serving Crie a função `lab_<iniciais>.score_cnpj(cnpj STRING)` que busca as features e chama o endpoint via `ai_query`.

### Trilha Genie CLI
```text
> @nuclea-model-serving Em tema5_<iniciais>/: SQL de features, script de treino como job serverless (environment v4,
  só lightgbm e mlflow-skinny), JSON do endpoint e função score_cnpj. Rode tudo, depois chame o endpoint com 20 CNPJs
  (10 inadimplentes e 10 adimplentes) e me dê p50/p95 de latência e a prob. média de cada grupo.
```

### Checkpoint 5
- AUC de cerca de 0,65 e KS de cerca de 0,23. É um sinal moderado; os dados são sintéticos.
- Prob. média dos inadimplentes **maior** que a dos adimplentes. Referência: 0,49 contra 0,14.
- Latência de cerca de 250 ms no p50 após o warmup. A primeira chamada demora por causa do scale-to-zero.
- `SELECT * FROM lab_<iniciais>.score_cnpj('05.657.016/0001-95')` devolve 1 linha.
- **Discussão:** a probabilidade serve como ranking, não como PD calibrada. Quando faz sentido usar Online Feature Store (Lakebase) em vez de `ai_query`?

---

## Tema 2: Monitoramento de crédito com agentes especialistas (45 min)

**Pergunta-alvo:** *"Como está a minha carteira de crédito de empresas do segmento varejo, pequeno porte, com presença na região Sudeste?"*

### Trilha Genie Code
1. **SQL editor:**
   > @nuclea-monitoramento-credito Crie `lab_<iniciais>.carteira_contratos` enriquecida (score e variação, alertas, boletos vencidos, agenda comprometida, região, porte_grupo) com COMMENT nas colunas, e as UC functions `resumo_carteira`, `quebra_carteira`, `evolucao_carteira`, `maiores_exposicoes` e `sinais_alerta`.
2. **Valide os números** (obrigatório) com o SQL do passo 4 da skill para o ISPB 42691787, filtrando Varejo, Pequeno e Sudeste.
3. **Camada de agente sem código:** crie uma **sala Genie** "Monitoramento de Crédito - <iniciais>" sobre `carteira_contratos`.
   - Adicione as UC functions como SQL functions.
   - Coloque nas instruções: "pequeno porte = porte_grupo Pequeno; carteira = status_contrato <> 'Liquidado'; sempre comparar com o mercado".
   - Cadastre 3 perguntas de exemplo com o SQL esperado.
4. **Multiagente** (Agents → Supervisor Agent / Agent Bricks): combine a sala de crédito, as salas existentes (Risco, Boletos), a UC function `score_cnpj` e as funções de `lab_<iniciais>`. Faça a pergunta do cliente e inspecione o trace.
5. **Genie Code como agente da própria plataforma:** no Genie Code, configure as UC functions de `lab_<iniciais>` como servidor MCP (Settings → MCP → UC Functions) e pergunte direto no painel.

### Trilha Genie CLI
```text
> @nuclea-monitoramento-credito Rode os SQL de referência adaptados para lab_<iniciais> e valide resumo_carteira
  contra o SQL direto para o ISPB 42691787 (Varejo, Pequeno, Sudeste).
> Crie a sala Genie "Monitoramento de Crédito - <iniciais>" via `databricks genie create-space` com a tabela, as instruções
  e 3 perguntas de exemplo; depois pergunte a ela com `databricks genie ask` a pergunta do cliente.
> (avançado) Adicione ao app Flask uma aba Carteira com orquestrador por tool calling usando
  .agents/skills/nuclea-monitoramento-credito/referencias/orquestrador_credito.py como base. Deploy como app nuclea-monitor-<iniciais>.
```

### Checkpoint 2
| Métrica (ISPB 42691787, Varejo, Pequeno, Sudeste) | Minha carteira | Mercado |
|---|---|---|
| Contratos ativos | 622 | 6.258 |
| Saldo devedor | R$ 27,92 mi | R$ 260,33 mi |
| % inadimplência | 4,02% | 4,64% |

- Sinais esperados no topo:
  - Novais Moreira S.A.: score caiu 173 pontos, faixa D, 2 alertas
  - Gonçalves da Mota: inadimplente com boleto adulterado
- **Governança:** o agente nunca pode ver contratos de outra instituição. O ISPB vem do app ou do login, não do LLM. Teste pedir para investigar um CNPJ fora da carteira: o acesso deve ser negado.
- **Referência pronta para demo:** app `nuclea-monitor`, aba **Carteira de crédito**, que mostra o rastro de cada agente.

---

## Fechamento (10 min): o que comparar
| Critério | Genie Code (workspace) | Genie Code CLI (terminal) |
|---|---|---|
| Melhor para | exploração, notebooks, pipelines visuais, DS agent | projetos versionáveis (bundles, apps), automação |
| Onde ficam as skills | `.assistant/skills` no workspace | `.agents/skills` ou `~/.genie/skills` |
| Contexto do projeto | `.assistant_instructions.md`, AGENTS.md subindo a árvore de pastas | `AGENTS.md` na raiz |
| Identidade | o usuário, com permissões do UC | o usuário via profile do CLI, com permissões do UC |

Perguntas para o time Nuclea:
1. Quanto do trabalho do cientista virou skill reaproveitável?
2. O que falta para levar o agente de carteira aos clientes, como canal de autoatendimento?
