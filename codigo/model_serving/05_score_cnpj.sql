-- Tema 5 - funcao SQL de score em tempo real por CNPJ (monta as features e chama o endpoint via ai_query)
-- Gerado por gen_score_sql.py a partir de 02_train.py
CREATE OR REPLACE FUNCTION workshop_nuclea_genie_catalog.lab_ml.score_cnpj(cnpj STRING COMMENT 'CNPJ com ou sem mascara')
RETURNS TABLE (
  cnpj STRING, razao_social STRING, porte STRING, setor STRING, uf STRING,
  prob_inadimplencia DOUBLE, score BIGINT, faixa_risco STRING,
  risco_ultimo_score INT, ur_pct_comprometido DOUBLE, bol_pct_vencido_aberto DOUBLE, risco_alertas_qtd INT
)
COMMENT 'Score de inadimplencia PJ em tempo real (modelo lab_ml.score_inadimplencia_pj@champion servido no endpoint nuclea-score-inadimplencia). score 0-1000: maior = menor risco. faixa_risco A (melhor) a E (pior).'
RETURN
  SELECT x.cnpj, e.razao_social, x.porte, x.setor, x.uf,
         x.r.prob_inadimplencia, x.r.score, x.r.faixa_risco,
         x.risco_ultimo_score, x.ur_pct_comprometido, x.bol_pct_vencido_aberto, x.risco_alertas_qtd
  FROM (
    SELECT f.*, ai_query(
      'nuclea-score-inadimplencia',
      named_struct(
        'porte', f.porte,
        'setor', f.setor,
        'uf', f.uf,
        'idade_anos', CAST(f.idade_anos AS DOUBLE),
        'log_faturamento', CAST(f.log_faturamento AS DOUBLE),
        'aceita_cartao', CAST(f.aceita_cartao AS DOUBLE),
        'ur_valor_constituido', CAST(f.ur_valor_constituido AS DOUBLE),
        'ur_valor_comprometido', CAST(f.ur_valor_comprometido AS DOUBLE),
        'ur_pct_comprometido', CAST(f.ur_pct_comprometido AS DOUBLE),
        'ur_qtd', CAST(f.ur_qtd AS DOUBLE),
        'ur_qtd_credenciadoras', CAST(f.ur_qtd_credenciadoras AS DOUBLE),
        'grav_qtd_contratos', CAST(f.grav_qtd_contratos AS DOUBLE),
        'grav_valor_contratado', CAST(f.grav_valor_contratado AS DOUBLE),
        'grav_taxa_media_am', CAST(f.grav_taxa_media_am AS DOUBLE),
        'grav_prazo_medio_meses', CAST(f.grav_prazo_medio_meses AS DOUBLE),
        'grav_qtd_financiadores', CAST(f.grav_qtd_financiadores AS DOUBLE),
        'bol_emitidos', CAST(f.bol_emitidos AS DOUBLE),
        'bol_pct_vencido_aberto', CAST(f.bol_pct_vencido_aberto AS DOUBLE),
        'bol_qtd_divergencia_benef', CAST(f.bol_qtd_divergencia_benef AS DOUBLE),
        'bol_pagador_qtd', CAST(f.bol_pagador_qtd AS DOUBLE),
        'bol_pagador_pct_vencido_aberto', CAST(f.bol_pagador_pct_vencido_aberto AS DOUBLE),
        'dup_sacador_qtd', CAST(f.dup_sacador_qtd AS DOUBLE),
        'dup_sacador_pct_nfe_nao_validada', CAST(f.dup_sacador_pct_nfe_nao_validada AS DOUBLE),
        'dup_sacador_pct_negociada', CAST(f.dup_sacador_pct_negociada AS DOUBLE),
        'dup_sacado_qtd', CAST(f.dup_sacado_qtd AS DOUBLE),
        'risco_ultimo_score', CAST(f.risco_ultimo_score AS DOUBLE),
        'risco_consultas_30d', CAST(f.risco_consultas_30d AS DOUBLE),
        'risco_consultas_total', CAST(f.risco_consultas_total AS DOUBLE),
        'risco_alertas_qtd', CAST(f.risco_alertas_qtd AS DOUBLE),
        'risco_alertas_alta', CAST(f.risco_alertas_alta AS DOUBLE),
        'risco_valor_exposto', CAST(f.risco_valor_exposto AS DOUBLE)),
      returnType => 'STRUCT<prob_inadimplencia: DOUBLE, score: BIGINT, faixa_risco: STRING>') AS r
    FROM workshop_nuclea_genie_catalog.lab_ml.features_pj f
    WHERE f.cnpj = regexp_replace(score_cnpj.cnpj, '[^0-9]', '')
  ) x
  JOIN workshop_nuclea_genie_catalog.cadastro.empresas_pj e ON e.cnpj = x.cnpj;
