---
name: nuclea-contexto-dados
description: Mapa das bases sintéticas do workshop Nuclea (catálogo workshop_nuclea_genie_catalog) - schemas, tabelas, chaves de junção, regras de negócio e armadilhas conhecidas. Use SEMPRE que for consultar, modelar ou construir algo (pipeline, agente, modelo, dashboard) sobre boletos, cartões/recebíveis, crédito, duplicatas, Pix Automático, risco/fraude ou cadastro de empresas e participantes da Nuclea.
---

# Contexto de dados: workshop Nuclea

Todos os dados são **sintéticos**. Catálogo: `workshop_nuclea_genie_catalog`. Período: **01/04/2026 a 30/09/2026**.

## Regras
1. **Não altere os schemas de origem** (`boletos`, `cadastro`, `cartoes`, `credito`, `duplicatas`, `pix`, `risco`). Escreva sempre em um schema `lab_*` (por exemplo `lab_credito`, `lab_ml`, `lab_ingestao`) ou em um schema seu.
2. **Data de referência = 2026-09-30**, não `current_date()`. Calcule com `max(data)` da própria tabela.
3. **Identifique instituições por ISPB, nunca pelo nome.** Há nomes repetidos em ISPBs diferentes (por exemplo, 3 participantes "da Cruz Pagamentos S.A.").
4. **CNPJ é STRING com 14 dígitos**, sem máscara, e é a chave entre todas as bases.
5. Prefira serverless (SQL warehouse "Serverless Starter Warehouse", jobs e pipelines serverless).

## Mapa das tabelas
| Schema.tabela | Linhas | Chaves / colunas-chave |
|---|---|---|
| `cadastro.empresas_pj` | 50 mil | `cnpj` (PK), `porte` (MEI, ME, EPP, Medio, Grande), `setor` (10 valores), `uf` (15 UFs, **sem município nem lat/long**), `data_abertura`, `faturamento_anual_declarado`, `cpf_socio_administrador`, `telefone_contato`, `dominio_email`, `ispb_banco_principal`, `rotulo_fraude_gt` (40 positivos) |
| `cadastro.participantes` | 150 | `ispb` (PK), `nome_participante`, `tipo_instituicao`, `segmento_prudencial`, `uf_sede` |
| `cadastro.calendario` | | `data`, `dia_util`, `feriado`, `peso` |
| `cadastro.incidentes_operacionais` | | `data`, `sistema`, `severidade`, `duracao_minutos` |
| `cartoes.contratos_gravames` | 60 mil | `cnpj_titular` → empresas; `ispb_financiador` → participantes; `status_contrato` (Ativo, Inadimplente, Liquidado); `saldo_devedor`, `taxa_am_pct`, `prazo_meses`, `tipo_efeito` |
| `cartoes.unidades_recebiveis` | 516 mil | `id_ur`, `cnpj_recebedor`, `ispb_credenciadora`, `arranjo`, `valor_constituido`, `valor_cancelado`, `valor_comprometido`, `status_ur` (A liquidar, Liquidada) |
| `cartoes.slc_liquidacoes` | 409 mil | `id_ur`, `cnpj_recebedor`, `status_liquidacao`, `motivo_ocorrencia` |
| `boletos.boletos_registro` | 1 milhão | `id_boleto`, `cnpj_beneficiario`, `valor_nominal`, `data_registro`, `data_vencimento`, `status_atual` (Liquidado, Vencido em aberto, ...) |
| `boletos.boletos_baixas` | | `id_boleto`, `valor_pago`, `divergencia_beneficiario` (boleto adulterado), `cnpj_creditado` |
| `boletos.siloc_liquidacoes` | | `produto`, `janela`, `ispb`, `resultado_liquido`, `atraso_minutos` |
| `credito.c3_cessoes` | 50 mil | `cnpj_originador_principal`, `ispb_cedente`, `tipo_cessionario`, `valor_face`, `com_coobrigacao` |
| `credito.ctc_portabilidades` | | `ispb_proponente`, `ispb_credor_original`, `cpf_cliente`, `sla_resposta_cumprido` |
| `duplicatas.duplicatas` | 406 mil | `cnpj_sacador`, `cnpj_sacado`, `nfe_validada`, `negociada`, `situacao_aceite` |
| `duplicatas.eventos_duplicata` | | `id_duplicata`, `tipo_evento`, `data_evento` |
| `pix.autorizacoes` / `pix.cobrancas` | / 334 mil | `id_autorizacao`, `cnpj_recebedor`, `status_autorizacao`, `motivo_cancelamento` / `status_cobranca` |
| `risco.consultas_cnpj` | 302 mil | `cnpj_consultado`, `ispb_consulente`, `data_hora_consulta`, `score_pj` (0 a 1000), `faixa_risco` (A a E) |
| `risco.alertas_fraude` | 14,7 mil | `cnpj_alvo`, `tipo_alerta`, `severidade`, `status_alerta` (Aberto, Em analise, Confirmado, Falso positivo) |

## Mapeamentos de negócio
- **Pequeno porte** = MEI, ME e EPP. **Médio** = Medio. **Grande** = Grande.
- **Regiões** por UF:
  - Sudeste: SP, RJ, MG, ES
  - Sul: PR, SC, RS
  - Centro-Oeste: GO, MT, MS, DF
  - Norte: AM, PA, AC, RO, RR, AP, TO
  - Nordeste: as demais
- **Carteira de crédito de uma instituição** = `contratos_gravames` onde `ispb_financiador = <ISPB>` e `status_contrato <> 'Liquidado'`.
- **% de inadimplência** = `sum(saldo_devedor de Inadimplente) / sum(saldo_devedor em aberto)`.

## Problemas de qualidade conhecidos (use em demos de Data Quality)
- 1 empresa com `data_abertura` em 1888.
- `faixa_risco` não é coerente com `score_pj`: a faixa D chega a ter score 799 e a C também. Só a faixa A (≥ 800) é consistente.
- Nomes de participante duplicados (ver a regra 3).
- O rótulo de fraude é muito desbalanceado (40 de 50 mil). Para ML, prefira a inadimplência de `contratos_gravames` ou `alertas_fraude` confirmados.

## Ativos já existentes no workspace
- **Salas Genie**, uma por base: "Nuclea - Boletos (PCR e SILOC)", "Nuclea - Cartoes (R2C3 e SLC)", "Nuclea - Duplicatas Escriturais", "Nuclea - Credito (CTC e C3)", "Nuclea - Pix Automatico", "Nuclea - Risco e Fraude".
- **App de referência `nuclea-monitor`** (Flask + Lakebase, aba Carteira de crédito): fica no workspace `fe-sandbox-stable-nuclea-workshop`, não neste.
- **Laboratórios:** `lab_ingestao` (Atos 1 e 2, prontos), `lab_ml` (Ato 3, pronto: endpoint `nuclea-score-inadimplencia` e `score_cnpj`), `lab_credito` (Ato 4: `carteira_contratos`, `filtra`, `resumo_carteira` e `instituicoes` prontos; as demais ferramentas são criadas ao vivo).

## Como explorar rápido
```sql
DESCRIBE TABLE EXTENDED workshop_nuclea_genie_catalog.cartoes.contratos_gravames;
SELECT table_schema, table_name, comment FROM workshop_nuclea_genie_catalog.information_schema.tables
WHERE table_schema NOT IN ('information_schema');
```
