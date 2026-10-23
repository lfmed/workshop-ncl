"""Chamadas a Genie Conversation API e ao SQL warehouse."""
import time

from databricks.sdk.service.sql import StatementState

import usage
from clients import CATALOG, SALAS, WAREHOUSE_ID, w

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}
MAX_ROWS = 200


def ask(sala, pergunta, conversation_id=None, timeout=240, uso=None, retry=False):
    """Pergunta a uma sala. Retorna dict com status, texto, sql, colunas, linhas, conversation_id.
    uso: contexto para o registro de requisicoes (origem, usuario, cnpj, execucao_id, monitor_id)."""
    ctx = dict(uso or {"origem": "chat"})
    origem = ctx.pop("origem", "chat")
    t0 = time.time()
    out = _ask(sala, pergunta, conversation_id, timeout)
    usage.registrar("genie", origem, sala=sala, status=out["status"],
                    duracao_ms=int((time.time() - t0) * 1000), statement_id=out.get("statement_id"), **ctx)
    # agentes rodam sem ninguem olhando: se o SQL gerado falhar, pede uma correcao na mesma conversa
    if retry and out["status"] == "FAILED" and out.get("conversation_id") and out.get("erro"):
        corr = (f"A consulta anterior falhou com o erro: {out['erro'][:400]}. "
                f"Refaca com um SQL mais simples (sem sequence/explode) respondendo a mesma pergunta: {pergunta}")
        t0 = time.time()
        novo = _ask(sala, corr, out["conversation_id"], timeout)
        usage.registrar("genie", origem, sala=sala, status=novo["status"],
                        duracao_ms=int((time.time() - t0) * 1000), statement_id=novo.get("statement_id"), **ctx)
        if novo["status"] == "COMPLETED":
            novo["pergunta"] = pergunta
            return novo
    return out


def _ask(sala, pergunta, conversation_id, timeout):
    space = SALAS[sala]["space_id"]
    out = {"sala": sala, "pergunta": pergunta, "status": "FAILED", "texto": None, "sql": None,
           "colunas": [], "linhas": [], "erro": None, "conversation_id": conversation_id}
    try:
        if conversation_id:
            m = w.genie.create_message(space, conversation_id, pergunta).response
        else:
            m = w.genie.start_conversation(space, pergunta).response
        out["conversation_id"] = m.conversation_id
        t0 = time.time()
        while True:
            m = w.genie.get_message(space, m.conversation_id, m.message_id)
            st = m.status.value if m.status else ""
            if st in TERMINAL:
                break
            if time.time() - t0 > timeout:
                out["erro"] = "Tempo esgotado aguardando a Genie"
                return out
            time.sleep(2)
        out["status"] = st
        if m.error:
            out["erro"] = m.error.error
        textos = []
        for a in m.attachments or []:
            if a.text and a.text.content:
                textos.append(a.text.content)
            if a.query:
                out["sql"] = a.query.query
                out["statement_id"] = a.query.statement_id
                if a.query.description:
                    textos.insert(0, a.query.description)
                r = w.genie.get_message_attachment_query_result(space, m.conversation_id, m.message_id, a.attachment_id)
                sr = r.statement_response
                if sr and sr.manifest and sr.manifest.schema:
                    out["colunas"] = [c.name for c in sr.manifest.schema.columns]
                    out["linhas"] = ((sr.result.data_array if sr.result else None) or [])[:MAX_ROWS]
        out["texto"] = "\n\n".join(textos) if textos else None
    except Exception as e:  # noqa: BLE001 - erro exibido ao usuario
        out["erro"] = str(e)
    return out


def sql(statement, params=None, origem="ficha", **ctx):
    from databricks.sdk.service.sql import StatementParameterListItem
    t0 = time.time()
    ps = [StatementParameterListItem(name=k, value=v) for k, v in (params or {}).items()]
    r = w.statement_execution.execute_statement(statement=statement, warehouse_id=WAREHOUSE_ID,
                                                parameters=ps, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(1)
        r = w.statement_execution.get_statement(r.statement_id)
    usage.registrar_async("sql", origem, status="OK" if r.status.state == StatementState.SUCCEEDED else r.status.state.value,
                          duracao_ms=int((time.time() - t0) * 1000), statement_id=r.statement_id, **ctx)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(r.status.error.message if r.status.error else r.status.state.value)
    cols = [c.name for c in r.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (r.result.data_array or [])]


def ficha_cnpj(cnpj, **ctx):
    """Ficha cadastral + vinculos (mesmo socio/telefone/dominio) direto do Unity Catalog."""
    e = f"{CATALOG}.cadastro.empresas_pj"
    p = f"{CATALOG}.cadastro.participantes"
    rows = sql(f"""
        SELECT e.cnpj, e.razao_social, e.porte, e.setor, e.uf, CAST(e.data_abertura AS STRING) data_abertura,
               e.faturamento_anual_declarado, e.telefone_contato, e.dominio_email, e.cpf_socio_administrador,
               p.nome_participante banco_principal,
               (SELECT count(*) - 1 FROM {e} x WHERE x.cpf_socio_administrador = e.cpf_socio_administrador) cnpjs_mesmo_socio,
               (SELECT count(*) - 1 FROM {e} x WHERE x.telefone_contato = e.telefone_contato) cnpjs_mesmo_telefone,
               (SELECT count(*) - 1 FROM {e} x WHERE x.dominio_email = e.dominio_email) cnpjs_mesmo_dominio
        FROM {e} e LEFT JOIN {p} p ON p.ispb = e.ispb_banco_principal WHERE e.cnpj = :cnpj""", {"cnpj": cnpj},
               "ficha", cnpj=cnpj, **ctx)
    return rows[0] if rows else None


def buscar_empresas(termo, limite=10):
    e = f"{CATALOG}.cadastro.empresas_pj"
    return sql(f"""SELECT cnpj, razao_social, porte, uf FROM {e}
                   WHERE cnpj LIKE :t OR upper(razao_social) LIKE upper(:t) ORDER BY idx_empresa LIMIT {int(limite)}""",
               {"t": f"%{termo}%"}, "busca")
