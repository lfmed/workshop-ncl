-- Tema 5 - tabela de features por CNPJ (data de referencia 2026-09-30)
-- Alvo: rotulo_inadimplente = CNPJ tem ao menos um contrato_gravame 'Inadimplente'.
-- Anti-vazamento: nenhuma feature usa status_contrato nem saldo_devedor (saldo zera quando liquida).
CREATE SCHEMA IF NOT EXISTS workshop_nuclea_genie_catalog.lab_ml
  COMMENT 'Tema 5 - features, modelo e funcoes de score PJ (workshop Nuclea)';

CREATE OR REPLACE TABLE workshop_nuclea_genie_catalog.lab_ml.features_pj (
  cnpj STRING NOT NULL,
  porte STRING, setor STRING, uf STRING,
  idade_anos DOUBLE, log_faturamento DOUBLE, aceita_cartao INT,
  ur_valor_constituido DOUBLE, ur_valor_comprometido DOUBLE, ur_pct_comprometido DOUBLE, ur_qtd INT, ur_qtd_credenciadoras INT,
  grav_qtd_contratos INT, grav_valor_contratado DOUBLE, grav_taxa_media_am DOUBLE, grav_prazo_medio_meses DOUBLE, grav_qtd_financiadores INT,
  bol_emitidos INT, bol_pct_vencido_aberto DOUBLE, bol_qtd_divergencia_benef INT,
  bol_pagador_qtd INT, bol_pagador_pct_vencido_aberto DOUBLE,
  dup_sacador_qtd INT, dup_sacador_pct_nfe_nao_validada DOUBLE, dup_sacador_pct_negociada DOUBLE, dup_sacado_qtd INT,
  risco_ultimo_score INT, risco_consultas_30d INT, risco_consultas_total INT,
  risco_alertas_qtd INT, risco_alertas_alta INT, risco_valor_exposto DOUBLE,
  tomador INT, rotulo_inadimplente INT,
  CONSTRAINT features_pj_pk PRIMARY KEY (cnpj)
) COMMENT 'Features por CNPJ para o score de inadimplencia PJ (ref. 2026-09-30). Dados SINTETICOS.'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT OVERWRITE workshop_nuclea_genie_catalog.lab_ml.features_pj
WITH e AS (SELECT * FROM workshop_nuclea_genie_catalog.cadastro.empresas_pj),
ur AS (
  SELECT cnpj_recebedor cnpj, sum(valor_constituido) c, sum(valor_comprometido) m, count(*) n,
         count(DISTINCT ispb_credenciadora) nc
  FROM workshop_nuclea_genie_catalog.cartoes.unidades_recebiveis GROUP BY 1),
gr AS (
  SELECT cnpj_titular cnpj, count(*) n, sum(valor_contrato) v, avg(taxa_am_pct) t, avg(prazo_meses) p,
         count(DISTINCT ispb_financiador) nf, max(CASE WHEN status_contrato = 'Inadimplente' THEN 1 ELSE 0 END) y
  FROM workshop_nuclea_genie_catalog.cartoes.contratos_gravames GROUP BY 1),
be AS (
  SELECT r.cnpj_beneficiario cnpj, count(*) n, avg(CASE WHEN r.status_atual = 'Vencido em aberto' THEN 1 ELSE 0 END) pv,
         count_if(b.divergencia_beneficiario) dv
  FROM workshop_nuclea_genie_catalog.boletos.boletos_registro r
  LEFT JOIN workshop_nuclea_genie_catalog.boletos.boletos_baixas b ON b.id_boleto = r.id_boleto
  GROUP BY 1),
bp AS (
  SELECT documento_pagador cnpj, count(*) n, avg(CASE WHEN status_atual = 'Vencido em aberto' THEN 1 ELSE 0 END) pv
  FROM workshop_nuclea_genie_catalog.boletos.boletos_registro WHERE tipo_pagador = 'PJ' GROUP BY 1),
ds AS (
  SELECT cnpj_sacador cnpj, count(*) n, avg(CASE WHEN NOT nfe_validada THEN 1 ELSE 0 END) nv, avg(CASE WHEN negociada THEN 1 ELSE 0 END) ng
  FROM workshop_nuclea_genie_catalog.duplicatas.duplicatas GROUP BY 1),
dc AS (SELECT cnpj_sacado cnpj, count(*) n FROM workshop_nuclea_genie_catalog.duplicatas.duplicatas GROUP BY 1),
cs AS (
  SELECT cnpj_consultado cnpj, max_by(score_pj, data_hora_consulta) s,
         count_if(data_hora_consulta >= timestamp'2026-09-01') n30, count(*) n
  FROM workshop_nuclea_genie_catalog.risco.consultas_cnpj GROUP BY 1),
al AS (
  SELECT cnpj_alvo cnpj, count(*) n, count_if(severidade IN ('Alta', 'Critica')) na, sum(valor_exposto) ve
  FROM workshop_nuclea_genie_catalog.risco.alertas_fraude GROUP BY 1)
SELECT e.cnpj, e.porte, e.setor, e.uf,
  round(datediff(date'2026-09-30', greatest(e.data_abertura, date'1900-01-01')) / 365.25, 2),
  ln(1 + e.faturamento_anual_declarado), CAST(e.aceita_cartao AS INT),
  coalesce(ur.c, 0), coalesce(ur.m, 0), coalesce(ur.m / nullif(ur.c, 0), 0), coalesce(ur.n, 0), coalesce(ur.nc, 0),
  coalesce(gr.n, 0), coalesce(gr.v, 0), gr.t, gr.p, coalesce(gr.nf, 0),
  coalesce(be.n, 0), coalesce(be.pv, 0), coalesce(be.dv, 0),
  coalesce(bp.n, 0), coalesce(bp.pv, 0),
  coalesce(ds.n, 0), coalesce(ds.nv, 0), coalesce(ds.ng, 0), coalesce(dc.n, 0),
  cs.s, coalesce(cs.n30, 0), coalesce(cs.n, 0),
  coalesce(al.n, 0), coalesce(al.na, 0), coalesce(al.ve, 0),
  CASE WHEN gr.cnpj IS NULL THEN 0 ELSE 1 END, coalesce(gr.y, 0)
FROM e
LEFT JOIN ur ON ur.cnpj = e.cnpj LEFT JOIN gr ON gr.cnpj = e.cnpj
LEFT JOIN be ON be.cnpj = e.cnpj LEFT JOIN bp ON bp.cnpj = e.cnpj
LEFT JOIN ds ON ds.cnpj = e.cnpj LEFT JOIN dc ON dc.cnpj = e.cnpj
LEFT JOIN cs ON cs.cnpj = e.cnpj LEFT JOIN al ON al.cnpj = e.cnpj;
