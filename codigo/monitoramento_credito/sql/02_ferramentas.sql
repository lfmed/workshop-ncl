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

CREATE OR REPLACE FUNCTION quebra_carteira(
  p_ispb     STRING DEFAULT NULL COMMENT 'ISPB da instituicao dona da carteira; NULL = mercado',
  p_dimensao STRING DEFAULT 'setor' COMMENT 'Dimensao da quebra: setor, porte, uf, regiao, tipo_efeito, faixa_risco',
  p_setor    STRING DEFAULT NULL COMMENT 'Filtro de setores (virgula)',
  p_porte    STRING DEFAULT NULL COMMENT 'Filtro de portes ou grupos (virgula)',
  p_regiao   STRING DEFAULT NULL COMMENT 'Filtro de regioes ou UFs (virgula)'
)
RETURNS TABLE (grupo STRING, contratos_ativos BIGINT, saldo_devedor DOUBLE, pct_do_saldo DOUBLE, pct_inadimplencia DOUBLE,
               pct_inadimplencia_mercado DOUBLE, score_medio DOUBLE)
COMMENT 'Agente Carteira: distribuicao da carteira em aberto por uma dimensao, com inadimplencia da instituicao e do mercado no mesmo grupo. Use para concentracao e comparacao.'
RETURN
  WITH base AS (
    SELECT CASE lower(p_dimensao) WHEN 'porte' THEN porte WHEN 'uf' THEN uf WHEN 'regiao' THEN regiao
                WHEN 'tipo_efeito' THEN tipo_efeito WHEN 'faixa_risco' THEN coalesce(faixa_atual, 'Sem score') ELSE setor END AS grupo, *
    FROM carteira_contratos
    WHERE status_contrato <> 'Liquidado'
      AND filtra(p_setor, setor) AND (filtra(p_porte, porte) OR filtra(p_porte, porte_grupo))
      AND (filtra(p_regiao, regiao) OR filtra(p_regiao, uf))
  ),
  mercado AS (SELECT grupo, 100 * sum(saldo_inadimplente) / nullif(sum(saldo_devedor), 0) AS inad FROM base GROUP BY 1),
  minha AS (SELECT * FROM base WHERE p_ispb IS NULL OR ispb_financiador = p_ispb)
  SELECT m.grupo, count(*), round(sum(m.saldo_devedor), 2),
         round(100 * sum(m.saldo_devedor) / sum(sum(m.saldo_devedor)) OVER (), 2),
         round(100 * sum(m.saldo_inadimplente) / nullif(sum(m.saldo_devedor), 0), 2),
         round(max(k.inad), 2), round(avg(m.score_atual))
  FROM minha m JOIN mercado k ON k.grupo = m.grupo
  GROUP BY m.grupo ORDER BY 3 DESC;

CREATE OR REPLACE FUNCTION evolucao_carteira(
  p_ispb   STRING DEFAULT NULL COMMENT 'ISPB da instituicao; NULL = mercado',
  p_setor  STRING DEFAULT NULL COMMENT 'Filtro de setores (virgula)',
  p_porte  STRING DEFAULT NULL COMMENT 'Filtro de portes ou grupos (virgula)',
  p_regiao STRING DEFAULT NULL COMMENT 'Filtro de regioes ou UFs (virgula)'
)
RETURNS TABLE (mes DATE, contratos_novos BIGINT, valor_contratado DOUBLE, taxa_media_am_pct DOUBLE,
               pct_safra_inadimplente DOUBLE, pct_safra_inadimplente_mercado DOUBLE)
COMMENT 'Agente Carteira: evolucao mensal por safra (mes de inicio do contrato) - originacao, taxa e % do valor da safra inadimplente, versus mercado. Use para tendencia.'
RETURN
  WITH base AS (
    SELECT * FROM carteira_contratos
    WHERE filtra(p_setor, setor) AND (filtra(p_porte, porte) OR filtra(p_porte, porte_grupo))
      AND (filtra(p_regiao, regiao) OR filtra(p_regiao, uf))
  ),
  mercado AS (SELECT mes_inicio, 100 * sum(saldo_inadimplente) / sum(valor_contrato) AS inad FROM base GROUP BY 1)
  SELECT b.mes_inicio, count(*), round(sum(b.valor_contrato), 2), round(avg(b.taxa_am_pct), 2),
         round(100 * sum(b.saldo_inadimplente) / sum(b.valor_contrato), 2), round(max(k.inad), 2)
  FROM base b JOIN mercado k ON k.mes_inicio = b.mes_inicio
  WHERE p_ispb IS NULL OR b.ispb_financiador = p_ispb
  GROUP BY b.mes_inicio ORDER BY 1;

CREATE OR REPLACE FUNCTION maiores_exposicoes(
  p_ispb   STRING DEFAULT NULL COMMENT 'ISPB da instituicao; NULL = mercado',
  p_setor  STRING DEFAULT NULL COMMENT 'Filtro de setores (virgula)',
  p_porte  STRING DEFAULT NULL COMMENT 'Filtro de portes ou grupos (virgula)',
  p_regiao STRING DEFAULT NULL COMMENT 'Filtro de regioes ou UFs (virgula)',
  p_limite INT    DEFAULT 10   COMMENT 'Quantidade de tomadores (max 50)'
)
RETURNS TABLE (cnpj STRING, razao_social STRING, porte STRING, setor STRING, uf STRING, contratos BIGINT, saldo_devedor DOUBLE,
               pct_da_carteira DOUBLE, saldo_inadimplente DOUBLE, score_atual INT, faixa_atual STRING, variacao_score DOUBLE,
               alertas_ativos BIGINT, pct_agenda_comprometida DOUBLE)
COMMENT 'Agente Exposicao: maiores tomadores por saldo devedor em aberto, com participacao na carteira e sinais de risco. Use para concentracao por cliente.'
RETURN
  WITH base AS (
    SELECT * FROM carteira_contratos
    WHERE status_contrato <> 'Liquidado' AND (p_ispb IS NULL OR ispb_financiador = p_ispb)
      AND filtra(p_setor, setor) AND (filtra(p_porte, porte) OR filtra(p_porte, porte_grupo))
      AND (filtra(p_regiao, regiao) OR filtra(p_regiao, uf))
  ),
  agg AS (
    SELECT cnpj, max(razao_social) razao_social, max(porte) porte, max(setor) setor, max(uf) uf, count(*) contratos,
           sum(saldo_devedor) saldo, sum(saldo_inadimplente) inad, max(score_atual) score, max(faixa_atual) faixa,
           max(variacao_score) var_score, max(alertas_em_aberto + alertas_confirmados) alertas, max(pct_agenda_comprometida) agenda
    FROM base GROUP BY cnpj
  )
  SELECT cnpj, razao_social, porte, setor, uf, contratos, round(saldo, 2), round(pct, 2), round(inad, 2), score, faixa, var_score, alertas, agenda
  FROM (SELECT *, 100 * saldo / sum(saldo) OVER () pct, row_number() OVER (ORDER BY saldo DESC) rn FROM agg)
  WHERE rn <= least(coalesce(p_limite, 10), 50) ORDER BY rn;

CREATE OR REPLACE FUNCTION sinais_alerta(
  p_ispb   STRING DEFAULT NULL COMMENT 'ISPB da instituicao; NULL = mercado',
  p_setor  STRING DEFAULT NULL COMMENT 'Filtro de setores (virgula)',
  p_porte  STRING DEFAULT NULL COMMENT 'Filtro de portes ou grupos (virgula)',
  p_regiao STRING DEFAULT NULL COMMENT 'Filtro de regioes ou UFs (virgula)',
  p_limite INT    DEFAULT 20   COMMENT 'Quantidade de tomadores (max 100)'
)
RETURNS TABLE (cnpj STRING, razao_social STRING, porte STRING, setor STRING, uf STRING, saldo_ativo DOUBLE, saldo_inadimplente DOUBLE,
               pontos_risco INT, sinais STRING, score_atual INT, faixa_atual STRING, variacao_score DOUBLE, tipos_alerta STRING)
COMMENT 'Agente Alerta Precoce: tomadores com saldo em aberto e sinais de deterioracao (score em queda, faixa D/E, alertas de fraude, boletos vencidos, agenda de recebiveis comprometida), ordenados por pontos de risco e saldo. Use para "quem devo olhar primeiro".'
RETURN
  WITH base AS (
    SELECT cnpj, max(razao_social) razao_social, max(porte) porte, max(setor) setor, max(uf) uf,
           sum(CASE WHEN status_contrato = 'Ativo' THEN saldo_devedor ELSE 0 END) saldo_ativo, sum(saldo_inadimplente) inad,
           max(score_atual) score, max(faixa_atual) faixa, max(variacao_score) var_score,
           max(alertas_em_aberto) al_aberto, max(alertas_confirmados) al_conf, max(tipos_alerta) tipos,
           max(boletos_vencidos_aberto) bol_venc, max(boletos_emitidos) bol_emit, max(pct_agenda_comprometida) agenda
    FROM carteira_contratos
    WHERE status_contrato <> 'Liquidado' AND (p_ispb IS NULL OR ispb_financiador = p_ispb)
      AND filtra(p_setor, setor) AND (filtra(p_porte, porte) OR filtra(p_porte, porte_grupo))
      AND (filtra(p_regiao, regiao) OR filtra(p_regiao, uf))
    GROUP BY cnpj
  ),
  pontuado AS (
    SELECT *,
      filter(array(
        CASE WHEN inad > 0 THEN 'ja inadimplente' END,
        CASE WHEN var_score <= -50 THEN concat('score caiu ', cast(-var_score AS INT), ' pts') END,
        CASE WHEN faixa IN ('D','E') THEN concat('faixa ', faixa) END,
        CASE WHEN al_conf > 0 THEN concat(al_conf, ' alerta(s) de fraude confirmado(s)') END,
        CASE WHEN al_aberto > 0 THEN concat(al_aberto, ' alerta(s) em aberto') END,
        CASE WHEN bol_emit >= 5 AND bol_venc / bol_emit >= 0.3 THEN concat(round(100 * bol_venc / bol_emit), '% dos boletos vencidos em aberto') END,
        CASE WHEN agenda >= 0.9 THEN concat(round(100 * agenda), '% da agenda de recebiveis comprometida') END
      ), x -> x IS NOT NULL) AS lista
    FROM base
  )
  SELECT cnpj, razao_social, porte, setor, uf, saldo_ativo, inad, pontos, sinais, score, faixa, var_score, tipos FROM (
  SELECT cnpj, razao_social, porte, setor, uf, round(saldo_ativo, 2) saldo_ativo, round(inad, 2) inad,
         CAST((CASE WHEN inad > 0 THEN 3 ELSE 0 END) + (CASE WHEN var_score <= -50 THEN 2 ELSE 0 END)
            + (CASE WHEN faixa IN ('D','E') THEN 2 ELSE 0 END) + (CASE WHEN al_conf > 0 THEN 3 ELSE 0 END)
            + (CASE WHEN al_aberto > 0 THEN 1 ELSE 0 END)
            + (CASE WHEN bol_emit >= 5 AND bol_venc / bol_emit >= 0.3 THEN 1 ELSE 0 END)
            + (CASE WHEN agenda >= 0.9 THEN 1 ELSE 0 END) AS INT) AS pontos,
         concat_ws('; ', lista) sinais, score, faixa, var_score, tipos,
         row_number() OVER (ORDER BY (CASE WHEN inad > 0 THEN 3 ELSE 0 END) + (CASE WHEN var_score <= -50 THEN 2 ELSE 0 END)
            + (CASE WHEN faixa IN ('D','E') THEN 2 ELSE 0 END) + (CASE WHEN al_conf > 0 THEN 3 ELSE 0 END)
            + (CASE WHEN al_aberto > 0 THEN 1 ELSE 0 END) + (CASE WHEN bol_emit >= 5 AND bol_venc / bol_emit >= 0.3 THEN 1 ELSE 0 END)
            + (CASE WHEN agenda >= 0.9 THEN 1 ELSE 0 END) DESC, saldo_ativo + inad DESC) rn
  FROM pontuado WHERE size(lista) > 0)
  WHERE rn <= least(coalesce(p_limite, 20), 100) ORDER BY rn;

CREATE OR REPLACE FUNCTION instituicoes()
RETURNS TABLE (ispb STRING, nome_participante STRING, tipo_instituicao STRING, contratos_ativos BIGINT, saldo_devedor DOUBLE)
COMMENT 'Lista as instituicoes financiadoras com carteira em aberto (para escolher o ISPB).'
RETURN
  SELECT ispb_financiador, max(nome_financiador), max(tipo_financiador), count(*), round(sum(saldo_devedor), 2)
  FROM carteira_contratos WHERE status_contrato <> 'Liquidado' GROUP BY 1 ORDER BY 5 DESC;
