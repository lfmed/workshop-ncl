"""Teste local do orquestrador de credito (sem Lakebase). Uso:
DATABRICKS_CONFIG_PROFILE=nuclea-workshop python testar_agente_local.py "<pergunta>" [ispb]"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "nuclea-monitor"))
os.environ.setdefault("DATABRICKS_WAREHOUSE_ID", "416525bdb6d93a9b")
import db  # noqa: E402
db.q = lambda *a, **k: []  # sem Lakebase no teste local
import credito  # noqa: E402

pergunta = sys.argv[1]
ispb = sys.argv[2] if len(sys.argv) > 2 else "42691787"
r = credito.perguntar(ispb, pergunta, [], "teste-local")
for p in r["passos"]:
    res = p["resultado"]
    print(f"- {p['agente']} :: {p['ferramenta']}({json.dumps(p['args'], ensure_ascii=False)}) -> "
          f"{len(res.get('linhas', [])) if 'linhas' in res else list(res)} linhas, {res.get('ms')} ms {res.get('erro') or ''}")
print(f"\n{r['duracao_ms']/1000:.1f}s, {r['tokens']} tokens\n")
print(r["resposta"])
