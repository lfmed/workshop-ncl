"""Registro de requisicoes (Genie, LLM, SQL) e estimativa de custo."""
import logging
import threading

from databricks.sdk.service.sql import QueryFilter

import db
from clients import w

log = logging.getLogger("usage")

# Precos de referencia (estimativas, editaveis na aba "Uso e custo")
PRECOS_PADRAO = {
    "usd_por_dbu_sql": (0.70, "US$ por DBU - Serverless SQL"),
    "warehouse_dbu_hora": (12.0, "DBU/hora do warehouse (Small serverless = 12)"),
    "llm_usd_milhao_entrada": (3.00, "US$ por 1M tokens de entrada do LLM"),
    "llm_usd_milhao_saida": (15.00, "US$ por 1M tokens de saida do LLM"),
    "genie_usd_mensagem": (0.00, "US$ por mensagem Genie (alem do warehouse)"),
    "app_usd_hora": (0.35, "US$ por hora do app (compute Medium)"),
    "lakebase_usd_hora": (0.15, "US$ por hora de Lakebase ativo (estimativa)"),
    "cotacao_brl": (5.40, "Cotacao US$ -> R$"),
}

DDL = """
CREATE TABLE IF NOT EXISTS {S}.uso (
  id BIGSERIAL PRIMARY KEY, criado_em TIMESTAMPTZ DEFAULT now(), tipo TEXT NOT NULL, origem TEXT,
  sala TEXT, cnpj TEXT, execucao_id BIGINT, monitor_id BIGINT, usuario TEXT, status TEXT, duracao_ms INT,
  statement_id TEXT, exec_ms INT, linhas_lidas BIGINT, bytes_lidos BIGINT, metricas_ok BOOLEAN DEFAULT false,
  tokens_entrada INT, tokens_saida INT);
CREATE INDEX IF NOT EXISTS ix_uso_data ON {S}.uso (criado_em);
CREATE INDEX IF NOT EXISTS ix_uso_stmt ON {S}.uso (statement_id) WHERE NOT metricas_ok;
CREATE TABLE IF NOT EXISTS {S}.precos (chave TEXT PRIMARY KEY, valor NUMERIC NOT NULL, descricao TEXT);
"""


def init():
    db.q(DDL)
    for k, (v, d) in PRECOS_PADRAO.items():
        db.q("INSERT INTO {S}.precos VALUES (%s, %s, %s) ON CONFLICT (chave) DO NOTHING", (k, v, d))


def registrar(tipo, origem, **kw):
    """Grava uma requisicao. Nunca deixa a falha do registro quebrar a chamada principal."""
    cols = ["tipo", "origem"] + list(kw)
    try:
        db.q(f"INSERT INTO {{S}}.uso ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
             (tipo, origem, *kw.values()))
    except Exception:  # noqa: BLE001
        log.exception("falha ao registrar uso")


def registrar_async(tipo, origem, **kw):
    threading.Thread(target=registrar, args=(tipo, origem), kwargs=kw, daemon=True).start()


def enriquecer():
    """Busca tempo de execucao e bytes lidos no query history para as queries registradas."""
    rows = db.q("""SELECT DISTINCT statement_id FROM {S}.uso WHERE NOT metricas_ok AND statement_id IS NOT NULL
                   AND criado_em < now() - interval '20 seconds' AND criado_em > now() - interval '2 days' LIMIT 50""")
    ids = [r["statement_id"] for r in rows]
    if not ids:
        return
    achados = set()
    resp = w.query_history.list(filter_by=QueryFilter(statement_ids=ids), include_metrics=True, max_results=100)
    for qi in getattr(resp, "res", None) or []:
        m = qi.metrics
        if not qi.query_id or (qi.status and qi.status.value in ("QUEUED", "RUNNING")):
            continue
        db.q("""UPDATE {S}.uso SET exec_ms = %s, linhas_lidas = %s, bytes_lidos = %s, metricas_ok = true
                WHERE statement_id = %s""",
             ((m.total_time_ms if m else None) or qi.duration, m.rows_read_count if m else None,
              m.read_bytes if m else None, qi.query_id))
        achados.add(qi.query_id)
    # o query history pode demorar; desiste apos 1 dia para nao reconsultar para sempre
    db.q("""UPDATE {S}.uso SET metricas_ok = true WHERE NOT metricas_ok AND statement_id IS NOT NULL
            AND criado_em < now() - interval '1 day'""")


def precos():
    return {r["chave"]: float(r["valor"]) for r in db.q("SELECT chave, valor FROM {S}.precos")}


def precos_lista():
    return db.q("SELECT chave, valor, descricao FROM {S}.precos ORDER BY chave")


def salvar_precos(valores):
    for k, v in valores.items():
        if k in PRECOS_PADRAO:
            db.q("UPDATE {S}.precos SET valor = %s WHERE chave = %s", (float(v), k))


PERIODOS = {"24h": "1 day", "7d": "7 days", "30d": "30 days", "tudo": "100 years"}


def _custo_sql(p, a=""):
    """Expressao SQL de custo estimado (US$) por linha de {S}.uso (a = prefixo de alias, ex.: 'u.')."""
    usd_seg_wh = p["usd_por_dbu_sql"] * p["warehouse_dbu_hora"] / 3600.0
    return f"""(coalesce({a}exec_ms, 0) / 1000.0 * {usd_seg_wh}
               + coalesce({a}tokens_entrada, 0) / 1e6 * {p['llm_usd_milhao_entrada']}
               + coalesce({a}tokens_saida, 0) / 1e6 * {p['llm_usd_milhao_saida']}
               + CASE WHEN {a}tipo = 'genie' THEN {p['genie_usd_mensagem']} ELSE 0 END)"""


def _floats(x):
    """Converte Decimal (NUMERIC do Postgres) em float, em dicts ou listas de dicts."""
    from decimal import Decimal
    if isinstance(x, list):
        return [_floats(i) for i in x]
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in x.items()}


def resumo(periodo="7d"):
    p = precos()
    iv = PERIODOS.get(periodo, "7 days")
    c = _custo_sql(p)
    f = f"criado_em > now() - interval '{iv}'"
    kpi = db.q1(f"""SELECT count(*) total, count(*) FILTER (WHERE tipo='genie') genie, count(*) FILTER (WHERE tipo='llm') llm,
                    count(*) FILTER (WHERE tipo='sql') sql, count(*) FILTER (WHERE status NOT IN ('COMPLETED','OK')) falhas,
                    coalesce(sum(tokens_entrada),0) tok_in, coalesce(sum(tokens_saida),0) tok_out,
                    coalesce(sum(exec_ms),0) / 1000.0 seg_warehouse, coalesce(sum({c}),0) custo_var,
                    count(*) FILTER (WHERE statement_id IS NOT NULL AND NOT metricas_ok) pendentes,
                    min(criado_em) primeiro FROM {{S}}.uso WHERE {f}""")
    por_dia = db.q(f"""SELECT to_char(date_trunc('day', criado_em), 'YYYY-MM-DD') dia, count(*) n,
                       count(*) FILTER (WHERE tipo='genie') genie, round(sum({c})::numeric, 4) custo
                       FROM {{S}}.uso WHERE {f} GROUP BY 1 ORDER BY 1""")
    por_tipo = db.q(f"""SELECT tipo, coalesce(sala, '-') sala, count(*) n, round(avg(duracao_ms)) lat_ms,
                        round(sum(coalesce(exec_ms,0))/1000.0, 1) seg_wh, sum(coalesce(tokens_entrada,0)) tok_in,
                        sum(coalesce(tokens_saida,0)) tok_out, round(sum({c})::numeric, 4) custo
                        FROM {{S}}.uso WHERE {f} GROUP BY 1, 2 ORDER BY custo DESC, n DESC""")
    por_origem = db.q(f"""SELECT origem, count(*) n, round(sum({c})::numeric, 4) custo FROM {{S}}.uso WHERE {f}
                          GROUP BY 1 ORDER BY n DESC""")
    por_usuario = db.q(f"""SELECT coalesce(usuario, '-') usuario, count(*) n, round(sum({c})::numeric, 4) custo
                           FROM {{S}}.uso WHERE {f} GROUP BY 1 ORDER BY n DESC LIMIT 15""")
    # custo medio por execucao de agente e projecao mensal dos monitores ativos
    por_exec = db.q1(f"""SELECT count(DISTINCT execucao_id) n, coalesce(sum({c}) / nullif(count(DISTINCT execucao_id),0), 0) medio
                         FROM {{S}}.uso WHERE execucao_id IS NOT NULL""")
    monitores = db.q(f"""SELECT m.id, m.cnpj, m.nome, m.frequencia_horas, m.ativo, cardinality(m.salas) n_salas,
                         (SELECT count(DISTINCT u.execucao_id) FROM {{S}}.uso u JOIN {{S}}.execucoes e ON e.id = u.execucao_id
                          WHERE e.cnpj = m.cnpj) execucoes,
                         (SELECT sum({_custo_sql(p, 'u.')})
                                 / nullif(count(DISTINCT u.execucao_id), 0)
                          FROM {{S}}.uso u JOIN {{S}}.execucoes e ON e.id = u.execucao_id WHERE e.cnpj = m.cnpj) custo_exec
                         FROM {{S}}.monitores m ORDER BY m.id""")
    kpi, por_dia, por_tipo, por_origem, por_usuario, por_exec, monitores = (
        _floats(x) for x in (kpi, por_dia, por_tipo, por_origem, por_usuario, por_exec, monitores))
    medio = float(por_exec["medio"] or 0)
    for m in monitores:
        m["custo_exec"] = float(m["custo_exec"]) if m["custo_exec"] is not None else medio
        m["exec_mes"] = (720 / m["frequencia_horas"]) if m["ativo"] else 0
        m["custo_mes"] = m["custo_exec"] * m["exec_mes"]
    fixo_mes = (p["app_usd_hora"] + p["lakebase_usd_hora"]) * 720
    return {"kpi": kpi, "por_dia": por_dia, "por_tipo": por_tipo, "por_origem": por_origem, "por_usuario": por_usuario,
            "custo_medio_exec": medio, "n_exec": por_exec["n"], "monitores": monitores, "precos": p,
            "fixo_mes": fixo_mes, "agentes_mes": sum(m["custo_mes"] for m in monitores)}
