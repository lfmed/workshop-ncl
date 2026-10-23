"""Silver: deduplica reenvios e aplica as expectations (fail / drop / warn) definidas em dq_regras."""
from pyspark import pipelines as dp

from dq_regras import REGRAS, seguras
from entidades import ENTIDADES


def criar_silver(nome, cfg):
    r = REGRAS[nome]

    @dp.table(name=f"silver_{nome}", cluster_by=cfg["cluster_by"],
              comment=f"Silver - {cfg['descricao']} deduplicado e validado (expectations). Dados SINTETICOS para workshop.",
              table_properties={"quality": "silver"})
    @dp.expect_all_or_fail(seguras(r["fail"]))
    @dp.expect_all_or_drop(seguras(r["drop"]))
    @dp.expect_all(seguras(r["warn"]))
    def _silver():
        # duplicata = mesma linha de negocio reenviada (ignora metadados de arquivo/lote).
        # Chave fixa (entidades.py): colunas novas vindas de schema drift nao entram no estado da dedup.
        return spark.readStream.table(f"bronze_{nome}").dropDuplicates(cfg["chaves_dedup"])


for nome, cfg in ENTIDADES.items():
    criar_silver(nome, cfg)
