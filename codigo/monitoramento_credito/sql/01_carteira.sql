-- Tema 2 - Monitoramento de Credito com agentes especialistas
-- Base unica da carteira: 1 linha por contrato (gravame sobre recebiveis de cartao),
-- enriquecida com cadastro do tomador, score PJ, alertas de fraude, boletos e agenda de UR.
-- Data de referencia = ultimo dia com dados (2026-09-30), nao current_date.

CREATE SCHEMA IF NOT EXISTS workshop_nuclea_genie_catalog.lab_credito
COMMENT 'Tema 2 - Monitoramento de credito com agentes especialistas (workshop Nuclea)';

USE CATALOG workshop_nuclea_genie_catalog;
USE SCHEMA lab_credito;

CREATE OR REPLACE TABLE carteira_contratos
CLUSTER BY (ispb_financiador, setor, regiao)
COMMENT 'Carteira de credito com garantia em recebiveis (1 linha por contrato), enriquecida com sinais de risco do tomador. Dados SINTETICOS.'
AS
WITH ref AS (SELECT max(data_inicio) AS data_ref FROM cartoes.contratos_gravames),
score AS (
  SELECT cnpj_consultado AS cnpj,
         max_by(score_pj, data_hora_consulta)                                         AS score_atual,
         max_by(faixa_risco, data_hora_consulta)                                      AS faixa_atual,
         avg(CASE WHEN data_hora_consulta >= data_ref - INTERVAL 30 DAYS THEN score_pj END) AS score_medio_30d,
         avg(CASE WHEN data_hora_consulta <  data_ref - INTERVAL 30 DAYS
                   AND data_hora_consulta >= data_ref - INTERVAL 120 DAYS THEN score_pj END) AS score_medio_30_120d,
         count_if(data_hora_consulta >= data_ref - INTERVAL 30 DAYS)                  AS consultas_30d,
         count(DISTINCT CASE WHEN data_hora_consulta >= data_ref - INTERVAL 30 DAYS THEN ispb_consulente END) AS consulentes_30d
  FROM risco.consultas_cnpj CROSS JOIN ref GROUP BY 1
),
alertas AS (
  SELECT cnpj_alvo AS cnpj,
         count_if(status_alerta IN ('Aberto','Em analise'))        AS alertas_em_aberto,
         count_if(status_alerta = 'Confirmado')                    AS alertas_confirmados,
         concat_ws(', ', array_distinct(collect_list(CASE WHEN status_alerta <> 'Falso positivo' THEN tipo_alerta END))) AS tipos_alerta
  FROM risco.alertas_fraude GROUP BY 1
),
boletos AS (
  SELECT cnpj_beneficiario AS cnpj,
         count(*)                                                    AS boletos_emitidos,
         count_if(status_atual = 'Vencido em aberto')                AS boletos_vencidos_aberto,
         sum(CASE WHEN status_atual = 'Vencido em aberto' THEN valor_nominal END) AS valor_boletos_vencidos
  FROM boletos.boletos_registro GROUP BY 1
),
agenda AS (
  SELECT cnpj_recebedor AS cnpj,
         sum(valor_constituido - valor_cancelado) AS agenda_livre_bruta,
         sum(valor_comprometido)                  AS agenda_comprometida
  FROM cartoes.unidades_recebiveis WHERE status_ur = 'A liquidar' GROUP BY 1
)
SELECT
  g.id_contrato, g.ispb_financiador, p.nome_participante AS nome_financiador, p.tipo_instituicao AS tipo_financiador,
  g.cnpj_titular AS cnpj, e.razao_social, e.porte,
  CASE WHEN e.porte IN ('MEI','ME','EPP') THEN 'Pequeno' WHEN e.porte = 'Medio' THEN 'Medio' ELSE 'Grande' END AS porte_grupo,
  e.setor, e.uf,
  CASE WHEN e.uf IN ('SP','RJ','MG','ES') THEN 'Sudeste'
       WHEN e.uf IN ('PR','SC','RS') THEN 'Sul'
       WHEN e.uf IN ('GO','MT','MS','DF') THEN 'Centro-Oeste'
       WHEN e.uf IN ('AM','PA','AC','RO','RR','AP','TO') THEN 'Norte'
       ELSE 'Nordeste' END AS regiao,
  e.data_abertura, floor(months_between(ref.data_ref, e.data_abertura) / 12) AS idade_empresa_anos,
  e.faturamento_anual_declarado,
  g.tipo_efeito, g.data_inicio, date_trunc('MONTH', g.data_inicio) AS mes_inicio, g.prazo_meses,
  g.valor_contrato, g.taxa_am_pct, g.status_contrato, g.saldo_devedor,
  CASE WHEN g.status_contrato = 'Inadimplente' THEN g.saldo_devedor ELSE 0 END AS saldo_inadimplente,
  s.score_atual, s.faixa_atual, round(s.score_medio_30d) AS score_medio_30d, round(s.score_medio_30_120d) AS score_medio_30_120d,
  round(s.score_medio_30d - s.score_medio_30_120d) AS variacao_score,
  coalesce(s.consultas_30d, 0) AS consultas_30d, coalesce(s.consulentes_30d, 0) AS consulentes_30d,
  coalesce(a.alertas_em_aberto, 0) AS alertas_em_aberto, coalesce(a.alertas_confirmados, 0) AS alertas_confirmados,
  nullif(a.tipos_alerta, '') AS tipos_alerta,
  coalesce(b.boletos_emitidos, 0) AS boletos_emitidos, coalesce(b.boletos_vencidos_aberto, 0) AS boletos_vencidos_aberto,
  coalesce(b.valor_boletos_vencidos, 0) AS valor_boletos_vencidos,
  round(ag.agenda_comprometida / nullif(ag.agenda_livre_bruta, 0), 4) AS pct_agenda_comprometida,
  ref.data_ref
FROM cartoes.contratos_gravames g
CROSS JOIN ref
JOIN cadastro.empresas_pj e   ON e.cnpj = g.cnpj_titular
JOIN cadastro.participantes p ON p.ispb = g.ispb_financiador
LEFT JOIN score s   ON s.cnpj = g.cnpj_titular
LEFT JOIN alertas a ON a.cnpj = g.cnpj_titular
LEFT JOIN boletos b ON b.cnpj = g.cnpj_titular
LEFT JOIN agenda ag ON ag.cnpj = g.cnpj_titular;

ALTER TABLE carteira_contratos ALTER COLUMN ispb_financiador COMMENT 'ISPB da instituicao financiadora (dona da carteira)';
ALTER TABLE carteira_contratos ALTER COLUMN porte_grupo COMMENT 'Pequeno = MEI, ME, EPP; Medio; Grande';
ALTER TABLE carteira_contratos ALTER COLUMN regiao COMMENT 'Regiao geografica do tomador derivada da UF';
ALTER TABLE carteira_contratos ALTER COLUMN variacao_score COMMENT 'Score medio ultimos 30d menos score medio de 30 a 120d atras (negativo = piora)';
ALTER TABLE carteira_contratos ALTER COLUMN pct_agenda_comprometida COMMENT 'Agenda de recebiveis a liquidar comprometida / agenda livre (UR)';
ALTER TABLE carteira_contratos ALTER COLUMN saldo_inadimplente COMMENT 'Saldo devedor dos contratos com status Inadimplente';
