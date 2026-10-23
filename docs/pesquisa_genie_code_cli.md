# Pesquisa: Genie Code (workspace) e Genie Code CLI — out/2026

Fontes (docs oficiais, consultadas em 21/10/2026):
- Skills: https://docs.databricks.com/aws/en/genie-code/skills
- Instruções: https://docs.databricks.com/aws/en/genie-code/instructions
- MCP: https://docs.databricks.com/aws/en/genie-code/mcp
- Visão geral: https://docs.databricks.com/aws/en/genie-code/
- Uso: https://docs.databricks.com/aws/en/genie-code/use-genie-code
- CLI: https://docs.databricks.com/aws/en/genie-code/genie-code-cli (atualizada em 20/10/2026)
- Grupo `databricks genie`: https://docs.databricks.com/aws/en/dev-tools/cli/reference/genie-commands

## 1. Genie Code no workspace

### Skills (confiança ALTA — doc oficial)
- Skills do workspace todo: `/Workspace/.assistant/skills/<nome>/SKILL.md` (precisa de admin para escrever na raiz)
- Skills do usuário: `/Users/<email>/.assistant/skills/<nome>/SKILL.md`
- Uma subpasta por skill, cada uma com `SKILL.md`; arquivos auxiliares (scripts, .md, templates) referenciados por **caminho relativo**.
- Também dá para registrar pastas extras em Settings (a pasta registrada tem que ser a pasta-mãe das subpastas de skill, não a que tem o SKILL.md).
- Frontmatter obrigatório (formato aberto "Agent Skills"):
  ```markdown
  ---
  name: nome-da-skill
  description: O que faz e quando usar (o Genie Code usa isto para decidir carregar).
  ---
  # Instruções passo a passo, exemplos, casos de borda
  ```
- Invocação: automática (pela `description`) ou manual com menção `@nome-da-skill`.
- Edições só valem em **nova conversa**; se parecer desatualizada, hard refresh no navegador.

### Instruções customizadas (confiança ALTA)
- Usuário: `/Users/<email>/.assistant_instructions.md`
- Workspace (admin): `/Workspace/.assistant_workspace_instructions.md`
- Limite de 20.000 caracteres; o workspace tem prioridade sobre o usuário.
- O Genie Code também lê automaticamente `AGENTS.md` e `CLAUDE.md`, subindo a árvore de pastas a partir do notebook/arquivo aberto.

### MCP no Genie Code (confiança ALTA)
Configurado nas settings do Genie Code. Tipos: UC MCP Service (servidor externo registrado no UC), UC Functions, AI Search (índice vetorial), **Genie Agent (sala Genie como ferramenta)**, Custom MCP Server (Databricks App no mesmo workspace, endpoint `/mcp`, stateless).

### O que o Genie Code faz hoje (confiança MÉDIA-ALTA)
Agente autônomo por padrão (planeja, executa, corrige erros). Superfícies: Notebooks (inclui o Data Science agent para EDA e treino de modelo), SQL editor, Lakeflow Pipelines Editor (constrói pipelines/ETL), AI/BI dashboards, MLflow e a página inteira de "command center". Tem slash commands e memória entre sessões.

## 2. "Genie CLI" = Genie Code CLI (confiança ALTA)
É o agente de código do Genie Code **no terminal local**. Lê e edita arquivos, roda comandos, consulta o UC via Genie e cria/deploya ativos Databricks.
- Status: **Beta**. Modelo gerenciado pela Databricks via Unity Gateway (GPT 5.6 no Beta), sem escolha de modelo.
- Pré-requisitos: região com suporte a Unity Gateway, UC habilitado, Databricks CLI >= 1.0.0.
- Instalação macOS/Linux:
  `curl -fsSL https://github.com/databricks/genie-code-cli/releases/latest/download/install.sh | bash`
- Autenticação: no primeiro `genie`, escolhe um profile do Databricks CLI (ou faz login). Roda com a identidade do usuário (permissões do UC valem).
- Comandos: `genie`, `genie --version`, `genie update`, `genie resume [--last]`, `genie mcp add ...`; dentro da sessão: `/resume`, `/mcp`, `/import` (importa configuração do Claude Code/Cursor).
- Skills: **só locais** — `~/.genie/skills/<nome>/SKILL.md` (pessoais), `.agents/skills/<nome>/SKILL.md` (no repositório/projeto), sistema em `~/.genie/skills/.system/`. **Não lê** `.assistant/skills` do workspace: é preciso copiar (ex.: `databricks workspace export-dir`).
- Instruções de projeto: `AGENTS.md` na raiz do projeto.
- Limitações: OAuth M2M; não suporta sessões por túnel SSH; token expirado gera 401 nas chamadas MCP.

### Não confundir: `databricks genie` (CLI do Databricks, confiança ALTA — verificado localmente com a v1.18.0)
Fala com **salas Genie (AI/BI)**, não é o agente de código. Ex.:
`databricks genie ask "pergunta" -s sessao --include-sql -o json --profile <p>` e mais `start-conversation`, `create-message`, `list-spaces`, `create-space`, `update-space` e `genie-create-eval-run` (benchmarks, Beta).

## 3. Estado do workspace nuclea-workshop (verificado, só leitura)
- Não existem: `/Workspace/.assistant`, `/Users/leandro.medeiros@databricks.com/.assistant`, `.assistant_instructions.md` do usuário nem `.assistant_workspace_instructions.md`. Nenhuma skill instalada.
- Genie (AI/BI) está ativo (6 salas Nuclea existem). Não há como checar pela CLI o toggle do Genie Code; validar abrindo o painel do Genie Code na UI.
- O Genie Code CLI (`genie`) **não está instalado** nesta máquina.
