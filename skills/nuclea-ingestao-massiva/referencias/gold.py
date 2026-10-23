"""Gold: posicoes diarias por UF/regiao/setor/porte (MVs com leitura batch da silver)."""
from pyspark import pipelines as dp

REGIAO = """CASE WHEN e.uf IN ('SP','RJ','MG','ES') THEN 'Sudeste'
                 WHEN e.uf IN ('PR','SC','RS') THEN 'Sul'
                 WHEN e.uf IN ('GO','MT','MS','DF') THEN 'Centro-Oeste'
                 WHEN e.uf IN ('AM','PA','AC','RO','RR','AP','TO') THEN 'Norte'
                 WHEN e.uf IS NULL THEN 'Nao identificado' ELSE 'Nordeste' END"""


@dp.materialized_view(name="gold_posicao_diaria_boletos", cluster_by=["data_registro", "uf"],
                      comment="Gold - posicao diaria de boletos registrados por UF/regiao/setor/porte do beneficiario. Dados SINTETICOS para workshop.")
def gold_posicao_diaria_boletos():
    return spark.sql(f"""
        SELECT b.data_registro, coalesce(e.uf, 'ND') AS uf, {REGIAO} AS regiao,
               coalesce(e.setor, 'Nao identificado') AS setor, coalesce(e.porte, 'Nao identificado') AS porte,
               count(*) AS qtd_boletos,
               round(sum(b.valor_nominal), 2) AS valor_nominal_total,
               count_if(b.status_atual = 'Vencido em aberto') AS qtd_vencidos_em_aberto,
               round(sum(CASE WHEN b.status_atual = 'Vencido em aberto' THEN b.valor_nominal ELSE 0 END), 2) AS valor_vencido_em_aberto,
               count_if(b.status_atual = 'Liquidado') AS qtd_liquidados
        FROM silver_boletos_registro b
        LEFT JOIN silver_empresas_pj e ON e.cnpj = b.cnpj_beneficiario
        GROUP BY ALL""")


@dp.materialized_view(name="gold_posicao_diaria_ur", cluster_by=["data_registro", "uf"],
                      comment="Gold - agenda de recebiveis de cartao (URs) registrada por dia/UF/setor/arranjo, com % comprometido. Dados SINTETICOS para workshop.")
def gold_posicao_diaria_ur():
    return spark.sql(f"""
        SELECT u.data_registro, coalesce(e.uf, 'ND') AS uf, {REGIAO} AS regiao,
               coalesce(e.setor, 'Nao identificado') AS setor, coalesce(e.porte, 'Nao identificado') AS porte, u.arranjo,
               count(*) AS qtd_urs,
               round(sum(u.valor_constituido), 2) AS valor_constituido,
               round(sum(u.valor_comprometido), 2) AS valor_comprometido,
               round(100 * sum(u.valor_comprometido) / nullif(sum(u.valor_constituido), 0), 2) AS pct_comprometido
        FROM silver_unidades_recebiveis u
        LEFT JOIN silver_empresas_pj e ON e.cnpj = u.cnpj_recebedor
        GROUP BY ALL""")


@dp.materialized_view(name="gold_baixas_diarias", cluster_by=["data_pagamento"],
                      comment="Gold - baixas de boletos por dia e canal, com divergencias de beneficiario. Dados SINTETICOS para workshop.")
def gold_baixas_diarias():
    return spark.sql("""
        SELECT data_pagamento, canal_pagamento, tipo_baixa,
               count(*) AS qtd_baixas, round(sum(valor_pago), 2) AS valor_pago,
               count_if(divergencia_beneficiario) AS qtd_divergencia_beneficiario,
               count_if(consulta_status_previa) AS qtd_com_consulta_previa
        FROM silver_boletos_baixas
        GROUP BY ALL""")
