"""Bronze: Auto Loader incremental sobre o volume landing. Ingere tudo (inclusive registros ruins),
guarda o que nao parseou em _rescued_data e adiciona metadados do arquivo de origem."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from entidades import ENTIDADES

LANDING = spark.conf.get("landing_path")


def criar_bronze(nome, cfg):
    @dp.table(name=f"bronze_{nome}", cluster_by=cfg["cluster_by"],
              comment=f"Bronze - {cfg['descricao']} (Auto Loader, {cfg['formato'].upper()}, dados brutos). Dados SINTETICOS para workshop.",
              table_properties={"quality": "bronze"})
    def _bronze():
        r = (spark.readStream.format("cloudFiles")
             .option("cloudFiles.format", cfg["formato"])
             .option("cloudFiles.inferColumnTypes", "true")
             .option("cloudFiles.schemaEvolutionMode", "addNewColumns")  # coluna nova -> evolui o schema
             .option("rescuedDataColumn", "_rescued_data")                # tipo invalido -> resgatado, nao perdido
             .option("cloudFiles.maxFilesPerTrigger", "200"))
        if cfg["hints"]:
            r = r.option("cloudFiles.schemaHints", cfg["hints"])
        for k, v in cfg["opcoes"].items():
            r = r.option(k, v)
        return (r.load(f"{LANDING}/{nome}")
                .withColumn("_arquivo", F.col("_metadata.file_path"))
                .withColumn("_arquivo_tamanho", F.col("_metadata.file_size"))
                .withColumn("_arquivo_modificado_em", F.col("_metadata.file_modification_time"))
                .withColumn("_lote", F.regexp_extract("_metadata.file_path", r"lote_(\d+)", 1).cast("int"))
                .withColumn("_ingerido_em", F.current_timestamp()))


for nome, cfg in ENTIDADES.items():
    criar_bronze(nome, cfg)
