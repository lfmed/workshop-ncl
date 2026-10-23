"""Lakebase (Postgres) - pool com token OAuth renovado e schema do app."""
import os
import threading
import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from clients import w

SCHEMA = "nuclea_monitor"
ENDPOINT = os.getenv("LAKEBASE_ENDPOINT", "projects/nuclea-monitor/branches/production/endpoints/primary")

_tok = {"value": None, "exp": 0.0}
_tok_lock = threading.Lock()


def _token():
    with _tok_lock:
        if time.time() > _tok["exp"]:
            _tok["value"] = w.postgres.generate_database_credential(endpoint=ENDPOINT).token
            _tok["exp"] = time.time() + 40 * 60
        return _tok["value"]


class _TokenConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        kwargs["password"] = _token()
        return super().connect(conninfo, **kwargs)


def _user():
    return os.getenv("PGUSER") or w.current_user.me().user_name


pool = ConnectionPool(
    kwargs={"host": os.getenv("PGHOST"), "port": int(os.getenv("PGPORT", "5432")),
            "dbname": os.getenv("PGDATABASE", "databricks_postgres"), "user": _user(),
            "sslmode": "require", "row_factory": dict_row, "autocommit": True,
            "options": "-c timezone=America/Sao_Paulo"},
    connection_class=_TokenConnection, min_size=1, max_size=10, max_lifetime=30 * 60,
    check=ConnectionPool.check_connection, open=False,
)

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE IF NOT EXISTS {SCHEMA}.mensagens (
  id BIGSERIAL PRIMARY KEY, sessao TEXT NOT NULL, sala TEXT NOT NULL, genie_conversation_id TEXT,
  pergunta TEXT NOT NULL, status TEXT, texto TEXT, sql TEXT, colunas JSONB, linhas JSONB, erro TEXT,
  usuario TEXT, criado_em TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS {SCHEMA}.monitores (
  id BIGSERIAL PRIMARY KEY, cnpj TEXT NOT NULL, nome TEXT, salas TEXT[] NOT NULL, perguntas JSONB NOT NULL,
  frequencia_horas INT NOT NULL, ativo BOOLEAN DEFAULT true, proxima_execucao TIMESTAMPTZ DEFAULT now(),
  criado_por TEXT, criado_em TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS {SCHEMA}.execucoes (
  id BIGSERIAL PRIMARY KEY, monitor_id BIGINT REFERENCES {SCHEMA}.monitores(id) ON DELETE CASCADE,
  cnpj TEXT NOT NULL, origem TEXT, status TEXT, ficha JSONB, parecer TEXT, nivel_risco TEXT,
  inicio TIMESTAMPTZ DEFAULT now(), fim TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS {SCHEMA}.resultados (
  id BIGSERIAL PRIMARY KEY, execucao_id BIGINT REFERENCES {SCHEMA}.execucoes(id) ON DELETE CASCADE,
  sala TEXT NOT NULL, pergunta TEXT, status TEXT, texto TEXT, sql TEXT, colunas JSONB, linhas JSONB, erro TEXT,
  genie_conversation_id TEXT, criado_em TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS {SCHEMA}.credito_mensagens (
  id BIGSERIAL PRIMARY KEY, ispb TEXT NOT NULL, usuario TEXT, pergunta TEXT NOT NULL, resposta TEXT, passos JSONB,
  duracao_ms INT, tokens_entrada INT, tokens_saida INT, criado_em TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_exec_cnpj ON {SCHEMA}.execucoes (cnpj, inicio DESC);
CREATE INDEX IF NOT EXISTS ix_msg_sessao ON {SCHEMA}.mensagens (sessao, criado_em);
"""


def init():
    pool.open(wait=True, timeout=60)
    with pool.connection() as c:
        c.execute(DDL)


def q(sql, params=None):
    with pool.connection() as c:
        cur = c.execute(sql.replace("{S}", SCHEMA), params)
        return cur.fetchall() if cur.description else []


def q1(sql, params=None):
    rows = q(sql, params)
    return rows[0] if rows else None
