"""Cria/atualiza as views de Data Quality sobre o event log do pipeline, a quarentena e o manifesto do gerador.

  vw_dq_expectativas         -> aprovados/reprovados por expectation em cada update (event log)
  vw_dq_taxa_aprovacao       -> taxa de aprovacao acumulada por tabela/expectation
  vw_dq_ingestao_por_update  -> linhas escritas por flow em cada update (prova da ingestao incremental)
  vw_dq_quarentena_motivos   -> registros em quarentena por entidade/lote/motivo
  vw_dq_reconciliacao        -> arquivo x bronze x silver x quarentena x duplicatas vs. gabarito do gerador
"""
import argparse

from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--schema", required=True)
a = p.parse_args()
spark = SparkSession.builder.getOrCreate()
S = f"{a.catalog}.{a.schema}"
ENTIDADES = ["boletos_registro", "boletos_baixas", "unidades_recebiveis", "empresas_pj"]

VIEWS = {
    "vw_dq_expectativas": f"""
        SELECT timestamp, origin.update_id, origin.flow_name,
               e.dataset AS tabela, e.name AS expectativa, e.passed_records AS aprovados, e.failed_records AS reprovados
        FROM {S}.event_log_ingestao
        LATERAL VIEW explode(from_json(details:flow_progress.data_quality.expectations,
                     'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) x AS e
        WHERE event_type = 'flow_progress' AND details:flow_progress.data_quality.expectations IS NOT NULL""",
    "vw_dq_taxa_aprovacao": f"""
        SELECT tabela, expectativa,
               CASE WHEN expectativa IN ('lote_identificado','arquivo_rastreavel') THEN 'fail'
                    WHEN expectativa IN ('especie_conhecida','valor_ate_1_milhao','sem_divergencia_beneficiario',
                                         'comprometido_ate_constituido','uf_preenchida','porte_conhecido') THEN 'warn'
                    ELSE 'drop' END AS acao,
               sum(aprovados) AS aprovados, sum(reprovados) AS reprovados,
               round(100 * sum(aprovados) / nullif(sum(aprovados) + sum(reprovados), 0), 4) AS taxa_aprovacao_pct,
               count(DISTINCT update_id) AS updates, max(timestamp) AS ultimo_update
        FROM {S}.vw_dq_expectativas GROUP BY tabela, expectativa""",
    "vw_dq_ingestao_por_update": f"""
        SELECT origin.update_id, min(timestamp) AS inicio, origin.flow_name AS tabela,
               sum(details:flow_progress.metrics.num_output_rows::bigint) AS linhas_escritas,
               sum(details:flow_progress.data_quality.dropped_records::bigint) AS linhas_descartadas
        FROM {S}.event_log_ingestao
        WHERE event_type = 'flow_progress' AND details:flow_progress.metrics.num_output_rows IS NOT NULL
        GROUP BY origin.update_id, origin.flow_name""",
    "vw_dq_quarentena_motivos": " UNION ALL ".join(
        f"SELECT '{e}' AS entidade, _lote AS lote, motivo, count(*) AS registros "
        f"FROM {S}.quarentena_{e} LATERAL VIEW explode(_motivos) m AS motivo GROUP BY _lote, motivo"
        for e in ENTIDADES),
    "vw_dq_reconciliacao": f"""
        WITH obs AS ({" UNION ALL ".join(
            f"SELECT '{e}' AS entidade, _lote AS lote, 'bronze' AS camada, count(*) AS n FROM {S}.bronze_{e} GROUP BY _lote "
            f"UNION ALL SELECT '{e}', _lote, 'silver', count(*) FROM {S}.silver_{e} GROUP BY _lote "
            f"UNION ALL SELECT '{e}', _lote, 'quarentena', count(*) FROM {S}.quarentena_{e} GROUP BY _lote"
            for e in ENTIDADES)}),
        piv AS (SELECT * FROM obs PIVOT (sum(n) FOR camada IN ('bronze' AS bronze, 'silver' AS silver, 'quarentena' AS quarentena))),
        gab AS (SELECT entidade, lote,
                       sum(CASE WHEN problema = 'linhas_no_arquivo' THEN qtd END) AS linhas_no_arquivo,
                       sum(CASE WHEN regra_esperada = 'dedup' THEN qtd END) AS dup_injetadas,
                       sum(CASE WHEN regra_esperada NOT IN ('dedup','total','schema_evolution','comprometido_ate_constituido') THEN qtd END) AS invalidas_injetadas
                FROM {S}.manifesto_injecoes GROUP BY entidade, lote)
        SELECT g.entidade, g.lote, g.linhas_no_arquivo, p.bronze, g.invalidas_injetadas, p.quarentena,
               g.dup_injetadas, p.bronze - p.silver - p.quarentena AS dup_removidas, p.silver,
               g.linhas_no_arquivo - g.dup_injetadas - g.invalidas_injetadas AS silver_esperado,
               (p.bronze = g.linhas_no_arquivo AND p.quarentena = g.invalidas_injetadas
                AND p.bronze - p.silver - p.quarentena = g.dup_injetadas) AS confere
        FROM gab g LEFT JOIN piv p USING (entidade, lote)""",
}

for nome, sql in VIEWS.items():
    spark.sql(f"CREATE OR REPLACE VIEW {S}.{nome} COMMENT 'Data Quality - workshop Nuclea' AS {sql}")
    print(f"[ok] {S}.{nome}")

spark.table(f"{S}.vw_dq_reconciliacao").orderBy("entidade", "lote").show(50, truncate=False)
