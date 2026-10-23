-- Tema 2 - Ferramentas (UC functions) dos agentes especialistas de monitoramento de credito.
-- Convencao dos filtros: NULL ou '' = sem filtro; listas separadas por virgula (ex.: 'SP,RJ').
-- p_porte aceita porte (MEI, ME, EPP, Medio, Grande) ou grupo (Pequeno, Medio, Grande).
-- p_ispb NULL = mercado inteiro (todas as instituicoes).

USE CATALOG workshop_nuclea_genie_catalog;
USE SCHEMA lab_credito;

-- Filtro comum reutilizado pelas demais funcoes
CREATE OR REPLACE FUNCTION filtra(lista STRING, valor STRING)
RETURNS BOOLEAN
COMMENT 'Helper: TRUE se lista vazia/NULL ou se valor esta na lista separada por virgula (case-insensitive)'
RETURN lista IS NULL OR trim(lista) = ''
    OR array_contains(transform(split(lower(lista), ','), x -> trim(x)), lower(valor));

CREATE OR REPLACE FUNCTION resumo_carteira(
  p_ispb   STRING DEFAULT NULL COMMENT 'ISPB da instituicao dona da carteira; NULL = mercado',
  p_setor  STRING DEFAULT NULL COMMENT 'Setores separados por virgula: Varejo, Servicos, Industria, Atacado, Construcao, Saude, Agronegocio, Tecnologia, Educacao, Logistica',
  p_porte  STRING DEFAULT NULL COMMENT 'Portes (MEI, ME, EPP, Medio, Grande) ou grupos (Pequeno, Medio, Grande)',
  p_regiao STRING DEFAULT NULL COMMENT 'Regioes (Sudeste, Sul, Nordeste, Norte, Centro-Oeste) ou UFs (SP, RJ...)'
)
RETURNS TABLE (escopo STRING, contratos_ativos BIGINT, tomadores BIGINT, saldo_devedor DOUBLE, saldo_inadimplente DOUBLE,
               pct_inadimplencia DOUBLE, taxa_media_am_pct DOUBLE, prazo_medio_meses DOUBLE, score_medio DOUBLE,
               pct_tomadores_faixa_d_e DOUBLE, pct_tomadores_com_alerta DOUBLE, pct_tomadores_score_em_queda DOUBLE, data_ref DATE)
COMMENT 'Agente Carteira: KPIs da carteira de credito em aberto (Ativo + Inadimplente) da instituicao versus o mercado com os mesmos filtros. Use para "como esta minha carteira".'
RETURN
  SELECT CASE WHEN copia = 1 THEN 'Minha carteira' ELSE 'Mercado (todas as IFs)' END,
         count(*), count(DISTINCT cnpj), round(sum(saldo_devedor), 2), round(sum(saldo_inadimplente), 2),
         round(100 * sum(saldo_inadimplente) / nullif(sum(saldo_devedor), 0), 2),
         round(avg(taxa_am_pct), 2), round(avg(prazo_meses), 1), round(avg(score_atual)),
         round(100 * count(DISTINCT CASE WHEN faixa_atual IN ('D','E') THEN cnpj END) / count(DISTINCT cnpj), 2),
         round(100 * count(DISTINCT CASE WHEN alertas_em_aberto + alertas_confirmados > 0 THEN cnpj END) / count(DISTINCT cnpj), 2),
         round(100 * count(DISTINCT CASE WHEN variacao_score <= -50 THEN cnpj END) / count(DISTINCT cnpj), 2),
         max(data_ref)
  FROM carteira_contratos c
  LATERAL VIEW explode(CASE WHEN p_ispb IS NULL THEN array(0) ELSE array(0, 1) END) t AS copia
  WHERE status_contrato <> 'Liquidado'
    AND filtra(p_setor, setor) AND (filtra(p_porte, porte) OR filtra(p_porte, porte_grupo))
    AND (filtra(p_regiao, regiao) OR filtra(p_regiao, uf))
    AND (copia = 0 OR ispb_financiador = p_ispb)
  GROUP BY copia ORDER BY copia DESC;

CREATE OR REPLACE FUNCTION instituicoes()
RETURNS TABLE (ispb STRING, nome_participante STRING, tipo_instituicao STRING, contratos_ativos BIGINT, saldo_devedor DOUBLE)
COMMENT 'Lista as instituicoes financiadoras com carteira em aberto (para escolher o ISPB).'
RETURN
  SELECT ispb_financiador, max(nome_financiador), max(tipo_financiador), count(*), round(sum(saldo_devedor), 2)
  FROM carteira_contratos WHERE status_contrato <> 'Liquidado' GROUP BY 1 ORDER BY 5 DESC;
