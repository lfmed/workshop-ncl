"""Tema 5 - valida o endpoint: 20 CNPJs (10 inadimplentes + 10 adimplentes), latencia p50/p95 pos-warmup."""
import json
import statistics
import time

from databricks.sdk import WorkspaceClient

PROFILE, WAREHOUSE, ENDPOINT = "nuclea-genie", "416525bdb6d93a9b", "nuclea-score-inadimplencia"
w = WorkspaceClient(profile=PROFILE)

r = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE, wait_timeout="50s", statement="""
  (SELECT * FROM workshop_nuclea_genie_catalog.lab_ml.features_pj WHERE tomador = 1 AND rotulo_inadimplente = 1 ORDER BY hash(cnpj) LIMIT 10)
  UNION ALL
  (SELECT * FROM workshop_nuclea_genie_catalog.lab_ml.features_pj WHERE tomador = 1 AND rotulo_inadimplente = 0 ORDER BY hash(cnpj) LIMIT 10)""")
cols = [c.name for c in r.manifest.schema.columns]
linhas = [dict(zip(cols, v)) for v in r.result.data_array]
NAO_FEATURE = {"cnpj", "tomador", "rotulo_inadimplente"}
CAT = {"porte", "setor", "uf"}


def payload(l):
    return {k: (v if k in CAT else (None if v is None else float(v))) for k, v in l.items() if k not in NAO_FEATURE}


def chamar(registros):
    t0 = time.perf_counter()
    resp = w.api_client.do("POST", f"/serving-endpoints/{ENDPOINT}/invocations", body={"dataframe_records": registros})
    return resp["predictions"], (time.perf_counter() - t0) * 1000


for _ in range(3):  # warmup
    chamar([payload(linhas[0])])

lat, res = [], []
for l in linhas:
    pred, ms = chamar([payload(l)])
    lat.append(ms)
    res.append({"cnpj": l["cnpj"], "inadimplente": int(l["rotulo_inadimplente"]), **pred[0]})

lat_s = sorted(lat)
p95 = lat_s[min(len(lat_s) - 1, int(round(0.95 * len(lat_s))) - 1)]
media = lambda g: statistics.mean(x["prob_inadimplencia"] for x in res if x["inadimplente"] == g)
_, ms_lote = chamar([payload(l) for l in linhas])
out = {
    "latencia_ms_p50": round(statistics.median(lat), 1), "latencia_ms_p95": round(p95, 1),
    "latencia_ms_lote_20": round(ms_lote, 1),
    "prob_media_inadimplentes": round(media(1), 4), "prob_media_adimplentes": round(media(0), 4),
    "resultados": res,
}
print(json.dumps(out, indent=2, ensure_ascii=False))
json.dump(out, open("resultado_validacao.json", "w"), indent=2, ensure_ascii=False)
