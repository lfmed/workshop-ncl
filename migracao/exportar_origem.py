# Exporta os 7 schemas de origem do workshop (somente leitura) para Parquet num volume, com os comentarios.
import json
SRC = "stable_nuclea_workshop_catalog"
DEST = f"/Volumes/{SRC}/lab_ingestao/export_migracao"
SCHEMAS = ["boletos", "cadastro", "cartoes", "credito", "duplicatas", "pix", "risco"]
meta = {}
for sch in SCHEMAS:
    for t in spark.sql(f"SHOW TABLES IN {SRC}.{sch}").collect():
        nome = f"{sch}.{t.tableName}"
        df = spark.table(f"{SRC}.{nome}")
        df.coalesce(4).write.mode("overwrite").parquet(f"{DEST}/{sch}/{t.tableName}")
        info = spark.sql(f"DESCRIBE TABLE EXTENDED {SRC}.{nome}").collect()
        comentario = next((r.data_type for r in info if r.col_name == "Comment"), None)
        colunas = {f.name: f.metadata.get("comment") for f in df.schema.fields if f.metadata.get("comment")}
        meta[nome] = {"linhas": df.count(), "comentario": comentario, "colunas": colunas}
        print(nome, meta[nome]["linhas"])
dbutils.fs.put(f"{DEST}/_manifesto.json", json.dumps(meta, ensure_ascii=False, indent=1), overwrite=True)
