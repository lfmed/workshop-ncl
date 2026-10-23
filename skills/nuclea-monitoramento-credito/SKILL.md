---
name: nuclea-monitoramento-credito
description: Constrói e opera o monitoramento de carteira de crédito da Nuclea com agentes especialistas - tabela de carteira enriquecida, UC functions como ferramentas (resumo, quebra, safras, exposições, sinais de alerta), sala Genie ou agente orquestrador, e validação dos números. Use quando pedirem para analisar "como está a minha carteira", criar agentes de monitoramento/concessão/recuperação de crédito, ou ferramentas de crédito para um agente.
---

# Monitoramento de crédito com agentes especialistas

Carregue também a skill `@nuclea-contexto-dados`. Ela tem o mapa das tabelas e as regras do workshop.

## Resultado esperado
Uma instituição (identificada por **ISPB**) pergunta em linguagem natural, por exemplo *"Como está a minha carteira de crédito de empresas do Varejo, pequeno porte, no Sudeste?"*. A resposta traz:
- KPIs comparados com o mercado
- Safras
- Concentração
- Tomadores com sinais de alerta
- Recomendações

## Passo 1: tabela da carteira (`lab_credito.carteira_contratos`)
Uma linha por contrato de `cartoes.contratos_gravames`, enriquecida com:
- `cadastro.empresas_pj`: porte, `porte_grupo` (Pequeno = MEI, ME, EPP), setor, UF, região derivada da UF, idade da empresa
- `cadastro.participantes`: nome do financiador
- `risco.consultas_cnpj`:
  - `score_atual` e `faixa_atual`, ambos via `max_by(..., data_hora_consulta)`
  - `variacao_score`: média dos últimos 30 dias menos a média de 30 a 120 dias atrás
  - consultas nos últimos 30 dias
- `risco.alertas_fraude`: quantidade em aberto ou em análise, quantidade confirmada e lista de tipos
- `boletos.boletos_registro`: boletos vencidos em aberto do CNPJ como beneficiário
- `cartoes.unidades_recebiveis` com `status_ur = 'A liquidar'`: `pct_agenda_comprometida` = comprometido / (constituído − cancelado)

Use `CLUSTER BY (ispb_financiador, setor, regiao)` e escreva COMMENT nas colunas: o Genie e o agente leem os comentários.
SQL de referência: [referencias/01_carteira.sql](referencias/01_carteira.sql).

## Passo 2: ferramentas como UC functions (`lab_credito`)
Os filtros seguem uma convenção única: NULL ou `''` = sem filtro, listas separadas por vírgula, sem diferenciar maiúsculas. `p_porte` aceita porte ou grupo, e `p_regiao` aceita região ou UF. Crie primeiro um helper `filtra(lista, valor)`.

| Função | Agente | Retorno |
|---|---|---|
| `resumo_carteira(p_ispb, p_setor, p_porte, p_regiao)` | Carteira | 2 linhas, "Minha carteira" e "Mercado": contratos, tomadores, saldo, % inadimplência, taxa, prazo, score, % faixa D/E, % com alerta, % com score em queda |
| `quebra_carteira(p_ispb, p_dimensao, ...)` | Carteira | Por setor, porte, UF, região, tipo de efeito ou faixa de risco, com a inadimplência do mercado no mesmo grupo |
| `evolucao_carteira(...)` | Carteira | Safra mensal: originação, taxa, % da safra inadimplente comparada com o mercado |
| `maiores_exposicoes(..., p_limite)` | Exposição | Maiores tomadores e % da carteira de cada um |
| `sinais_alerta(..., p_limite)` | Alerta precoce | Tomadores com sinais (já inadimplente, score caiu ≥ 50, faixa D/E, fraude confirmada ou em aberto, ≥ 30% de boletos vencidos, ≥ 90% da agenda comprometida), com pontos e motivos |

SQL de referência: [referencias/02a_ferramentas_prontas.sql](referencias/02a_ferramentas_prontas.sql) (filtra, resumo_carteira, instituicoes) e [referencias/02b_gabarito_ao_vivo.sql](referencias/02b_gabarito_ao_vivo.sql) (as outras 4).

**Armadilhas já resolvidas na referência:**
- `LIMIT` não aceita parâmetro em SQL UDF. Use `row_number()` e `WHERE rn <= p_limite`.
- Para "minha carteira contra o mercado" numa única consulta, duplique as linhas com `LATERAL VIEW explode(array(0,1))` e agrupe pela cópia. Agrupar por `ispb = p_ispb` conta a carteira em dobro.
- Escreva COMMENT nas funções e nos parâmetros: é desse texto que sai a descrição da ferramenta para o LLM.

## Passo 3: escolha a camada de agente
1. **Mais rápida, sem código: sala Genie** sobre `lab_credito.carteira_contratos`.
   - Instruções: "pequeno porte = porte_grupo Pequeno", "carteira = status_contrato <> 'Liquidado'", "sempre compare com o mercado".
   - Adicione as UC functions como SQL functions/trusted assets e cadastre exemplos de perguntas com o SQL esperado.
   - **Se a UI não permitir anexar SQL functions à sala**, crie ou atualize a sala pela API (`databricks genie create-space --json @arquivo.json`, ou `update-space`).
     - No `serialized_space` (version 2), as funções ficam em `instructions.sql_functions`: `[{"id": "<32 hex>", "identifier": "catalogo.schema.funcao"}]`, ordenadas por `(id, identifier)`.
     - Os ids precisam ser únicos entre `text_instructions`, `example_question_sqls`, `sql_functions` e `join_specs`.
     - Referência pronta, usada na sala "Nuclea - Monitoramento de Credito": [referencias/sala_genie_credito.json](referencias/sala_genie_credito.json).
2. **Agente orquestrador com tool calling.** Referência: [referencias/orquestrador_credito.py](referencias/orquestrador_credito.py), usada no app `nuclea-monitor`, aba "Carteira de crédito".
   - As ferramentas são geradas a partir de `w.functions.get()`.
   - **O ISPB é injetado pelo app e nunca vem do LLM.**
   - A investigação via Genie só aceita CNPJs da própria carteira.
   - O loop tem no máximo 8 passos e chama as ferramentas em paralelo.
3. **Agent Bricks Supervisor Agent**, que combina a sala Genie de crédito, as UC functions e o endpoint de score do tema 5.

## Passo 4: valide os números (obrigatório)
Compare a ferramenta com SQL direto. Exemplo para o ISPB 42691787, filtrando Varejo, Pequeno e Sudeste:
```sql
SELECT * FROM workshop_nuclea_genie_catalog.lab_credito.resumo_carteira('42691787','Varejo','Pequeno','Sudeste');
-- precisa bater com:
SELECT count(*), sum(saldo_devedor), 100*sum(saldo_inadimplente)/sum(saldo_devedor)
FROM workshop_nuclea_genie_catalog.lab_credito.carteira_contratos
WHERE ispb_financiador='42691787' AND setor='Varejo' AND porte IN ('MEI','ME','EPP')
  AND uf IN ('SP','RJ','MG','ES') AND status_contrato<>'Liquidado';
-- esperado: 622 contratos, R$ 27,92 mi, 4,02% (mercado 4,64%)
```

## Passo 5: permissões
O agente roda com a identidade do app ou do usuário. Conceda o acesso no schema:
```sql
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workshop_nuclea_genie_catalog.lab_credito TO `<principal>`;
```
