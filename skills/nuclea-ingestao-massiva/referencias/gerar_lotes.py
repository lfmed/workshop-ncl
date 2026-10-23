"""Gera lotes de arquivos brutos no volume landing, simulando a chegada massiva de dados.

Cada lote corresponde a um mes de movimento (lote 1 = abr/2026 ... lote 6 = set/2026):
  boletos_registro  -> CSV     (landing/boletos_registro/lote_NNN/*.csv)
  boletos_baixas    -> CSV     (landing/boletos_baixas/lote_NNN/*.csv)
  unidades_recebiveis -> JSON  (landing/unidades_recebiveis/lote_NNN/*.json)
  empresas_pj       -> Parquet (landing/empresas_pj/lote_001/*.parquet; cadastro so vem no lote 1)

Em cada lote sao injetados problemas de qualidade CONTROLADOS (quantidades fixas, linhas disjuntas)
e registrados em <schema>.manifesto_injecoes para a reconciliacao com o pipeline.
O lote 6 de unidades_recebiveis traz uma coluna nova (id_registradora) -> schema drift.

Uso: gerar_lotes.py --catalog C --schema S --lotes 1,2,3 [--forcar true]
"""
import argparse
import os

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--schema", required=True)
p.add_argument("--lotes", required=True)
p.add_argument("--forcar", default="false")
a = p.parse_args()

spark = SparkSession.builder.getOrCreate()
C, S = a.catalog, a.schema
LANDING = f"/Volumes/{C}/{S}/landing"
FORCAR = a.forcar.lower() == "true"
MANIFESTO = f"{C}.{S}.manifesto_injecoes"

spark.sql(f"""CREATE TABLE IF NOT EXISTS {MANIFESTO} (
  lote INT, entidade STRING, problema STRING, regra_esperada STRING, qtd BIGINT, gerado_em TIMESTAMP)
  COMMENT 'Problemas de qualidade injetados pelo gerador de lotes (gabarito para a reconciliacao)'""")


def numerar(df: DataFrame, chave: str, lote: int) -> DataFrame:
    """Numeracao deterministica (1..n) para escolher as linhas que recebem cada problema."""
    return df.withColumn("_r", F.row_number().over(Window.orderBy(F.xxhash64(F.col(chave), F.lit(lote)))))


def mascarar_cnpj(c):
    """14 digitos -> 'XX.XXX.XXX/XXXX-XX' (CNPJ mal formatado para a regra de 14 digitos)."""
    return F.concat(F.substring(c, 1, 2), F.lit("."), F.substring(c, 3, 3), F.lit("."), F.substring(c, 6, 3),
                    F.lit("/"), F.substring(c, 9, 4), F.lit("-"), F.substring(c, 13, 2))


def entre(i, j):
    return F.col("_r").between(i, j)


def duplicar(df: DataFrame, i: int, j: int) -> DataFrame:
    """Reenvia copias exatas de linhas limpas (simula reprocessamento/reenvio do participante)."""
    return df.unionByName(df.where(entre(i, j)))


def gravar(df: DataFrame, entidade: str, lote: int, fmt: str, arquivos: int) -> bool:
    destino = f"{LANDING}/{entidade}/lote_{lote:03d}"
    if os.path.exists(destino) and not FORCAR:
        print(f"[pulado] {destino} ja existe (use --forcar true para regravar)")
        return False
    w = df.drop("_r").repartition(arquivos).write.mode("overwrite")
    if fmt == "csv":
        w.option("header", True).csv(destino)
    elif fmt == "json":
        w.json(destino)
    else:
        w.parquet(destino)
    print(f"[ok] {destino}")
    return True


def boletos_registro(lote, mes):
    src = spark.table(f"{C}.boletos.boletos_registro").where(F.month("data_registro") == mes)
    df = numerar(src.select([F.col(c).cast("string") for c in src.columns]), "id_boleto", lote)
    df = (df.withColumn("id_boleto", F.when(entre(1, 50), None).otherwise(F.col("id_boleto")))
            .withColumn("valor_nominal", F.when(entre(51, 90), (-F.col("valor_nominal").cast("double")).cast("string"))
                                          .when(entre(121, 140), F.lit("R$ 1.234,56"))
                                          .otherwise(F.col("valor_nominal")))
            .withColumn("data_vencimento", F.when(entre(91, 120), F.date_sub(F.col("data_registro").cast("date"), 10).cast("string"))
                                            .when(entre(141, 150), F.lit("2026-02-30"))
                                            .otherwise(F.col("data_vencimento")))
            .withColumn("cnpj_beneficiario", F.when(entre(151, 210), mascarar_cnpj(F.col("cnpj_beneficiario")))
                                              .otherwise(F.col("cnpj_beneficiario"))))
    return duplicar(df, 1001, 1100), [
        ("id_boleto nulo", "id_boleto_obrigatorio", 50),
        ("valor_nominal negativo", "valor_nominal_positivo", 40),
        ("data_vencimento anterior ao registro", "vencimento_apos_registro", 30),
        ("valor_nominal texto ('R$ 1.234,56') -> _rescued_data", "sem_dados_resgatados", 20),
        ("data_vencimento invalida ('2026-02-30') -> _rescued_data", "sem_dados_resgatados", 10),
        ("cnpj_beneficiario com mascara", "cnpj_beneficiario_14_digitos", 60),
        ("linhas duplicadas (reenvio)", "dedup", 100),
    ]


def boletos_baixas(lote, mes):
    src = spark.table(f"{C}.boletos.boletos_baixas").where(F.month("data_pagamento") == mes)
    df = numerar(src.select([F.col(c).cast("string") for c in src.columns]), "id_baixa", lote)
    df = (df.withColumn("id_boleto", F.when(entre(1, 10), None).otherwise(F.col("id_boleto")))
            .withColumn("valor_pago", F.when(entre(11, 30), (-F.col("valor_pago").cast("double")).cast("string"))
                                       .otherwise(F.col("valor_pago"))))
    return duplicar(df, 501, 530), [
        ("id_boleto nulo", "id_boleto_obrigatorio", 10),
        ("valor_pago negativo", "valor_pago_positivo", 20),
        ("linhas duplicadas (reenvio)", "dedup", 30),
    ]


def unidades_recebiveis(lote, mes):
    df = numerar(spark.table(f"{C}.cartoes.unidades_recebiveis").where(F.month("data_registro") == mes), "id_ur", lote)
    df = (df.withColumn("id_ur", F.when(entre(1, 20), None).otherwise(F.col("id_ur")))
            .withColumn("valor_constituido", F.when(entre(21, 50), -F.col("valor_constituido")).otherwise(F.col("valor_constituido")))
            .withColumn("cnpj_recebedor", F.when(entre(51, 90), mascarar_cnpj(F.col("cnpj_recebedor"))).otherwise(F.col("cnpj_recebedor")))
            .withColumn("valor_comprometido", F.when(entre(91, 110), F.round(F.col("valor_constituido") * 1.5, 2))
                                               .otherwise(F.col("valor_comprometido"))))
    problemas = [
        ("id_ur nulo", "id_ur_obrigatorio", 20),
        ("valor_constituido negativo", "valor_constituido_positivo", 30),
        ("cnpj_recebedor com mascara", "cnpj_recebedor_14_digitos", 40),
        ("valor_comprometido > valor_constituido (alerta, nao descarta)", "comprometido_ate_constituido", 20),
        ("linhas duplicadas (reenvio)", "dedup", 50),
    ]
    if lote >= 6:  # schema drift: a registradora passa a mandar uma coluna nova
        df = df.withColumn("id_registradora", F.lit("R2C3-NUCLEA"))
        problemas.append(("schema drift: coluna nova id_registradora", "schema_evolution", 0))
    return duplicar(df, 1001, 1050), problemas


def empresas_pj(lote, mes):
    df = numerar(spark.table(f"{C}.cadastro.empresas_pj"), "cnpj", lote)
    df = (df.withColumn("cnpj", F.when(entre(1, 25), mascarar_cnpj(F.col("cnpj"))).otherwise(F.col("cnpj")))
            .withColumn("data_abertura", F.when(entre(26, 35), F.date_add(F.current_date(), 400)).otherwise(F.col("data_abertura")))
            .withColumn("faturamento_anual_declarado", F.when(entre(36, 50), -F.col("faturamento_anual_declarado"))
                                                       .otherwise(F.col("faturamento_anual_declarado"))))
    # problema que ja existe na origem (nao injetado), fora das faixas acima: entra no gabarito para fechar a conta
    origem = df.where(~entre(1, 50) & (F.col("data_abertura") < F.lit("1900-01-01"))).count()
    return duplicar(df, 1001, 1030), [
        ("data_abertura anterior a 1900 (ja existia na origem)", "data_abertura_valida", origem),
        ("cnpj com mascara", "cnpj_14_digitos", 25),
        ("data_abertura no futuro", "data_abertura_valida", 10),
        ("faturamento negativo", "faturamento_nao_negativo", 15),
        ("linhas duplicadas (reenvio)", "dedup", 30),
    ]


ENTIDADES = [  # (nome, gerador, formato, n arquivos, lotes em que chega)
    ("boletos_registro", boletos_registro, "csv", 16, range(1, 7)),
    ("boletos_baixas", boletos_baixas, "csv", 8, range(1, 7)),
    ("unidades_recebiveis", unidades_recebiveis, "json", 8, range(1, 7)),
    ("empresas_pj", empresas_pj, "parquet", 4, [1]),
]

for lote in [int(x) for x in a.lotes.split(",") if x.strip()]:
    mes = 3 + lote  # lote 1 = abril/2026
    for nome, gerador, fmt, arquivos, lotes_validos in ENTIDADES:
        if lote not in lotes_validos:
            continue
        df, problemas = gerador(lote, mes)
        total = df.count()  # serverless nao suporta cache(): o plano e deterministico (hash) e recalcula igual
        if not gravar(df, nome, lote, fmt, arquivos):
            continue
        spark.sql(f"DELETE FROM {MANIFESTO} WHERE lote = {lote} AND entidade = '{nome}'")
        linhas = [(lote, nome, "linhas_no_arquivo", "total", total)] + [(lote, nome, p, r, q) for p, r, q in problemas]
        (spark.createDataFrame(linhas, "lote INT, entidade STRING, problema STRING, regra_esperada STRING, qtd BIGINT")
              .withColumn("gerado_em", F.current_timestamp())
              .write.mode("append").saveAsTable(MANIFESTO))
        print(f"   {nome} lote {lote}: {total} linhas")
