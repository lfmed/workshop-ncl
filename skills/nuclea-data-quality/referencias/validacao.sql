-- Validacao do Tema 6 (ingestao) + Tema 4 (DQ). Rodar no SQL warehouse.
USE CATALOG workshop_nuclea_genie_catalog;
USE SCHEMA lab_ingestao;

-- 1) Reconciliacao: arquivo x bronze x quarentena x duplicatas x silver vs. gabarito do gerador
SELECT * FROM vw_dq_reconciliacao ORDER BY entidade, lote;

-- 2) Quarentena por motivo (uma linha pode ter mais de um motivo)
SELECT entidade, motivo, sum(registros) AS registros FROM vw_dq_quarentena_motivos GROUP BY ALL ORDER BY 1, 3 DESC;

-- 3) Taxa de aprovacao por expectation (event log)
SELECT * FROM vw_dq_taxa_aprovacao ORDER BY tabela, acao, expectativa;

-- 4) Ingestao incremental: linhas escritas por tabela em cada update do pipeline
SELECT * FROM vw_dq_ingestao_por_update WHERE tabela LIKE 'bronze_%' ORDER BY inicio, tabela;

-- 5) Schema drift: coluna nova id_registradora aparece so a partir do lote 6
SELECT _lote, count(*) AS linhas, count(id_registradora) AS com_id_registradora
FROM bronze_unidades_recebiveis GROUP BY _lote ORDER BY _lote;

-- 6) Liquid clustering nas tabelas grandes
DESCRIBE DETAIL silver_boletos_registro;

-- 7) Gold: exemplo de consumo (Varejo, Sudeste)
SELECT date_trunc('month', data_registro) AS mes, porte, sum(qtd_boletos) AS boletos,
       sum(valor_vencido_em_aberto) AS vencido_em_aberto
FROM gold_posicao_diaria_boletos WHERE regiao = 'Sudeste' AND setor = 'Varejo' GROUP BY ALL ORDER BY 1, 2;
