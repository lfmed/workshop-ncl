"""Executa um arquivo .sql (varias instrucoes separadas por ';' no fim da linha) num SQL warehouse.
Uso: python scripts/run_sql.py <arquivo.sql> [--profile nuclea-workshop] [--warehouse fc961fe8e037f5d0]"""
import argparse
import re
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

ap = argparse.ArgumentParser()
ap.add_argument("arquivo")
ap.add_argument("--profile", default="nuclea-genie")
ap.add_argument("--warehouse", default="416525bdb6d93a9b")
a = ap.parse_args()

w = WorkspaceClient(profile=a.profile)
texto = "\n".join(l for l in open(a.arquivo).read().splitlines() if not l.strip().startswith("--"))
stmts = [s.strip() for s in re.split(r";\s*\n", texto + "\n") if s.strip()]
catalog = schema = None
for s in stmts:
    m = re.match(r"USE CATALOG (\S+)", s, re.I) or None
    if m:
        catalog = m.group(1); continue
    m = re.match(r"USE SCHEMA (\S+)", s, re.I)
    if m:
        schema = m.group(1); continue
    r = w.statement_execution.execute_statement(statement=s, warehouse_id=a.warehouse, catalog=catalog, schema=schema,
                                                wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
    print(f"[{r.status.state.value}] {s.splitlines()[0][:90]}")
    if r.status.state != StatementState.SUCCEEDED:
        print(r.status.error.message if r.status.error else r.status, file=sys.stderr)
        sys.exit(1)
