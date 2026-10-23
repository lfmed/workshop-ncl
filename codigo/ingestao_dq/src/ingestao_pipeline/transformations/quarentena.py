"""Quarentena: registros que violam alguma regra drop/fail, com a lista de motivos. Nada e perdido em silencio."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from dq_regras import condicao_valida, motivos
from entidades import ENTIDADES


def criar_quarentena(nome, cfg):
    @dp.table(name=f"quarentena_{nome}",
              comment=f"Quarentena - {cfg['descricao']} rejeitados pelas regras de qualidade, com _motivos. Dados SINTETICOS para workshop.",
              table_properties={"quality": "quarentena"})
    def _quarentena():
        return (spark.readStream.table(f"bronze_{nome}")
                .where(f"NOT ({condicao_valida(nome)})")
                .withColumn("_motivos", motivos(nome))
                .withColumn("_quarentenado_em", F.current_timestamp()))


for nome, cfg in ENTIDADES.items():
    criar_quarentena(nome, cfg)
