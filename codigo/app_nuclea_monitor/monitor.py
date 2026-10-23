"""Agentes por CNPJ: execucao (salas em paralelo + parecer LLM) e agendador em background."""
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import db
import genie
import usage
from clients import LLM_ENDPOINT, SALAS, w

log = logging.getLogger("monitor")
_pool = ThreadPoolExecutor(max_workers=12)

PROMPT = """Voce e um analista senior de prevencao a fraude e risco de credito da Nuclea (infraestrutura do mercado financeiro).
Varios agentes analisaram o mesmo CNPJ em bases diferentes (boletos, cartoes, duplicatas, credito, Pix Automatico, risco).
Cruze os achados e escreva um parecer em portugues, em markdown, com:

1. Primeira linha EXATAMENTE no formato: `NIVEL DE RISCO: <Baixo|Medio|Alto|Critico>`
2. **Resumo executivo** (3-4 frases)
3. **Achados por base** (bullets curtos, com numeros)
4. **Sinais cruzados** - padroes que so aparecem combinando bases (ex.: agenda comprometida + duplicatas sem lastro + rajada de consultas)
5. **Recomendacoes** para as instituicoes participantes

Seja objetivo, cite valores em R$ e datas. Se uma base nao trouxe dados, diga isso sem inventar.
"""


def _fmt_result(r):
    s = f"### Base: {SALAS[r['sala']]['titulo']}\nPergunta: {r['pergunta']}\n"
    if r.get("erro"):
        return s + f"ERRO: {r['erro']}\n"
    if r.get("texto"):
        s += f"Resposta: {r['texto']}\n"
    if r.get("colunas"):
        s += "Tabela:\n" + " | ".join(r["colunas"]) + "\n"
        for row in r["linhas"][:40]:
            s += " | ".join("" if v is None else str(v) for v in row) + "\n"
    return s


def parecer(cnpj, ficha, resultados, uso=None):
    contexto = f"CNPJ analisado: {cnpj}\nFicha cadastral: {json.dumps(ficha, ensure_ascii=False, default=str)}\n\n"
    contexto += "\n".join(_fmt_result(r) for r in resultados)
    t0 = time.time()
    resp = w.api_client.do("POST", f"/serving-endpoints/{LLM_ENDPOINT}/invocations", body={
        "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": contexto}],
        "max_tokens": 12000})
    u = resp.get("usage") or {}
    ctx = dict(uso or {})
    usage.registrar("llm", ctx.pop("origem", "manual"), sala="parecer", cnpj=cnpj, status="OK",
                    duracao_ms=int((time.time() - t0) * 1000), tokens_entrada=u.get("prompt_tokens"),
                    tokens_saida=u.get("completion_tokens"), **ctx)
    choice = resp["choices"][0]
    texto = choice["message"]["content"]
    if isinstance(texto, list):
        texto = "".join(p.get("text", "") for p in texto if isinstance(p, dict) and p.get("type") == "text")
    if choice.get("finish_reason") == "length":
        log.warning("parecer truncado (max_tokens)")
        texto += "\n\n_(parecer truncado pelo limite de tokens)_"
    m = re.search(r"NIVEL DE RISCO:\s*\**\s*(Baixo|Medio|Médio|Alto|Critico|Crítico)", texto, re.I)
    nivel = m.group(1).capitalize().replace("Médio", "Medio").replace("Crítico", "Critico") if m else "Indefinido"
    return texto, nivel


def executar(cnpj, salas, perguntas, monitor_id=None, origem="manual"):
    """Cria a execucao e roda tudo em background. Retorna o id da execucao."""
    ex = db.q1("INSERT INTO {S}.execucoes (monitor_id, cnpj, origem, status) VALUES (%s, %s, %s, 'Executando') RETURNING id",
               (monitor_id, cnpj, origem))
    _pool.submit(_run, ex["id"], cnpj, salas, perguntas,
                 {"origem": f"agente_{origem}", "cnpj": cnpj, "execucao_id": ex["id"], "monitor_id": monitor_id})
    return ex["id"]


def _run(ex_id, cnpj, salas, perguntas, uso):
    try:
        ficha_f = _pool.submit(genie.ficha_cnpj, cnpj, execucao_id=ex_id, monitor_id=uso["monitor_id"])
        futs = {s: _pool.submit(genie.ask, s, (perguntas.get(s) or SALAS[s]["pergunta"]).replace("{cnpj}", cnpj), uso=uso, retry=True)
                for s in salas}
        resultados = []
        for s, f in futs.items():
            r = f.result()
            resultados.append(r)
            db.q("""INSERT INTO {S}.resultados (execucao_id, sala, pergunta, status, texto, sql, colunas, linhas, erro, genie_conversation_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                 (ex_id, s, r["pergunta"], r["status"], r["texto"], r["sql"], json.dumps(r["colunas"]),
                  json.dumps(r["linhas"], default=str), r["erro"], r["conversation_id"]))
        ficha = ficha_f.result()
        db.q("UPDATE {S}.execucoes SET ficha = %s, status = 'Gerando parecer' WHERE id = %s", (json.dumps(ficha, default=str), ex_id))
        texto, nivel = parecer(cnpj, ficha, resultados,
                               {k: v for k, v in uso.items() if k in ("origem", "execucao_id", "monitor_id")})
        db.q("UPDATE {S}.execucoes SET parecer = %s, nivel_risco = %s, status = 'Concluida', fim = now() WHERE id = %s",
             (texto, nivel, ex_id))
    except Exception as e:  # noqa: BLE001
        log.exception("execucao %s falhou", ex_id)
        db.q("UPDATE {S}.execucoes SET status = 'Falhou', parecer = %s, fim = now() WHERE id = %s", (f"Erro: {e}", ex_id))


def _claim_due():
    """Reserva um monitor vencido (seguro com varios workers do gunicorn)."""
    return db.q1("""
        UPDATE {S}.monitores m SET proxima_execucao = now() + make_interval(hours => m.frequencia_horas)
        WHERE m.id = (SELECT id FROM {S}.monitores WHERE ativo AND proxima_execucao <= now()
                      ORDER BY proxima_execucao FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING m.*""")


def _loop():
    while True:
        try:
            while (m := _claim_due()) is not None:
                log.info("agendado: monitor %s cnpj %s", m["id"], m["cnpj"])
                executar(m["cnpj"], m["salas"], m["perguntas"], m["id"], "agendada")
        except Exception:  # noqa: BLE001
            log.exception("erro no agendador")
        try:
            usage.enriquecer()
        except Exception:  # noqa: BLE001
            log.exception("erro ao buscar metricas de queries")
        time.sleep(30)


def start_scheduler():
    threading.Thread(target=_loop, name="agendador", daemon=True).start()
