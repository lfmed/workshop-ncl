"""Nuclea Monitor - salas Genie por base + agentes de monitoramento por CNPJ."""
import json
import logging
import re

import markdown as md
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
from markupsafe import Markup

import credito
import db
import genie
import monitor
import usage
from clients import ROTEIRO, SALAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = Flask(__name__)

db.init()
usage.init()
monitor.start_scheduler()

FREQUENCIAS = [(1, "A cada hora"), (6, "A cada 6 horas"), (24, "Diaria"), (168, "Semanal")]
NIVEL_CLS = {"Baixo": "ok", "Medio": "warn", "Alto": "high", "Critico": "crit"}


def usuario():
    return request.headers.get("X-Forwarded-Email") or request.headers.get("X-Forwarded-User") or "local"


def so_digitos(cnpj):
    return re.sub(r"\D", "", cnpj or "")


@app.template_filter("markdown")
def _markdown(texto):
    return Markup(md.markdown(texto or "", extensions=["tables", "fenced_code"]))


@app.template_filter("num")
def _num(v):
    """Formata numeros no padrao pt-BR (mantem CNPJ/ISPB e outros codigos como texto)."""
    if v is None:
        return ""
    s = str(v)
    if re.fullmatch(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", s) and (re.search(r"[.eE]", s) or len(s.lstrip("-")) < 8):
        n = float(s)
        txt = f"{n:,.2f}" if n != int(n) else f"{int(n):,}"
        return txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


@app.template_filter("cnpj")
def _cnpj(c):
    c = so_digitos(c)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


@app.context_processor
def _ctx():
    return {"SALAS": SALAS, "NIVEL_CLS": NIVEL_CLS, "FREQ": dict(FREQUENCIAS)}


@app.get("/")
def index():
    return redirect(url_for("conversar"))


# ------------------------------------------------------------------ Conversar (Genie multi-sala)

@app.get("/conversar")
def conversar():
    return render_template("conversar.html", aba="conversar", roteiro=ROTEIRO)


@app.post("/api/ask")
def api_ask():
    d = request.get_json(force=True)
    sala, pergunta = d.get("sala"), (d.get("pergunta") or "").strip()
    if sala not in SALAS or not pergunta:
        abort(400)
    r = genie.ask(sala, pergunta, d.get("conversation_id"), uso={"origem": "chat", "usuario": usuario()})
    db.q("""INSERT INTO {S}.mensagens (sessao, sala, genie_conversation_id, pergunta, status, texto, sql, colunas, linhas, erro, usuario)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
         (d.get("sessao") or "-", sala, r["conversation_id"], pergunta, r["status"], r["texto"], r["sql"],
          json.dumps(r["colunas"]), json.dumps(r["linhas"], default=str), r["erro"], usuario()))
    r["texto_html"] = str(_markdown(r["texto"])) if r["texto"] else None
    return jsonify(r)


@app.get("/api/empresas")
def api_empresas():
    termo = (request.args.get("q") or "").strip()
    if len(termo) < 3:
        return jsonify([])
    return jsonify(genie.buscar_empresas(so_digitos(termo) if re.fullmatch(r"[\d./-]+", termo) else termo))


# ------------------------------------------------------------------ Agentes por CNPJ

@app.get("/agentes")
def agentes():
    mons = db.q("""SELECT m.*, e.nivel_risco, e.status AS ult_status, e.inicio AS ult_inicio
                   FROM {S}.monitores m LEFT JOIN LATERAL (
                     SELECT nivel_risco, status, inicio FROM {S}.execucoes x WHERE x.cnpj = m.cnpj ORDER BY inicio DESC LIMIT 1) e ON true
                   ORDER BY m.criado_em DESC""")
    recentes = db.q("SELECT id, cnpj, origem, status, nivel_risco, inicio FROM {S}.execucoes ORDER BY inicio DESC LIMIT 15")
    return render_template("agentes.html", aba="agentes", monitores=mons, recentes=recentes,
                           frequencias=FREQUENCIAS, cnpj_inicial=so_digitos(request.args.get("cnpj")))


@app.post("/agentes")
def criar_agente():
    f = request.form
    cnpj = so_digitos(f.get("cnpj"))
    salas = [s for s in f.getlist("salas") if s in SALAS]
    if len(cnpj) != 14 or not salas:
        abort(400, "Informe um CNPJ valido e ao menos uma base")
    perguntas = {s: (f.get(f"pergunta_{s}") or SALAS[s]["pergunta"]).strip() for s in salas}
    m = db.q1("""INSERT INTO {S}.monitores (cnpj, nome, salas, perguntas, frequencia_horas, criado_por)
                 VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
              (cnpj, f.get("nome") or None, salas, json.dumps(perguntas), int(f.get("frequencia", 24)), usuario()))
    if f.get("executar_agora"):
        db.q("UPDATE {S}.monitores SET proxima_execucao = now() + make_interval(hours => frequencia_horas) WHERE id = %s", (m["id"],))
        monitor.executar(cnpj, salas, perguntas, m["id"], "manual")
    return redirect(url_for("painel", cnpj=cnpj))


@app.post("/agentes/<int:mid>/<acao>")
def acao_agente(mid, acao):
    m = db.q1("SELECT * FROM {S}.monitores WHERE id = %s", (mid,)) or abort(404)
    if acao == "executar":
        monitor.executar(m["cnpj"], m["salas"], m["perguntas"], mid, "manual")
        return redirect(url_for("painel", cnpj=m["cnpj"]))
    if acao == "alternar":
        db.q("UPDATE {S}.monitores SET ativo = NOT ativo, proxima_execucao = greatest(proxima_execucao, now()) WHERE id = %s", (mid,))
    elif acao == "excluir":
        db.q("DELETE FROM {S}.monitores WHERE id = %s", (mid,))
    return redirect(url_for("agentes"))


@app.post("/api/analisar")
def api_analisar():
    d = request.get_json(force=True)
    cnpj = so_digitos(d.get("cnpj"))
    salas = [s for s in d.get("salas") or SALAS if s in SALAS]
    if len(cnpj) != 14:
        abort(400)
    ex = monitor.executar(cnpj, salas, {}, None, "manual")
    return jsonify({"execucao_id": ex, "url": url_for("painel", cnpj=cnpj)})


# ------------------------------------------------------------------ Painel do CNPJ

@app.get("/cnpj/<cnpj>")
def painel(cnpj):
    cnpj = so_digitos(cnpj)
    execs = db.q("SELECT * FROM {S}.execucoes WHERE cnpj = %s ORDER BY inicio DESC LIMIT 20", (cnpj,))
    sel = request.args.get("exec", type=int)
    atual = next((e for e in execs if e["id"] == sel), execs[0] if execs else None)
    resultados = db.q("SELECT * FROM {S}.resultados WHERE execucao_id = %s ORDER BY sala", (atual["id"],)) if atual else []
    ficha = (atual or {}).get("ficha")
    if not ficha:
        try:
            ficha = genie.ficha_cnpj(cnpj)
        except Exception:  # noqa: BLE001
            ficha = None
    mons = db.q("SELECT * FROM {S}.monitores WHERE cnpj = %s ORDER BY id", (cnpj,))
    return render_template("painel.html", aba="agentes", cnpj=cnpj, execs=execs, atual=atual,
                           resultados=resultados, ficha=ficha, monitores=mons)


@app.get("/api/execucao/<int:eid>")
def api_execucao(eid):
    e = db.q1("SELECT id, status, nivel_risco FROM {S}.execucoes WHERE id = %s", (eid,)) or abort(404)
    n = db.q1("SELECT count(*) AS n FROM {S}.resultados WHERE execucao_id = %s", (eid,))
    return jsonify({**e, "salas_concluidas": n["n"]})


# ------------------------------------------------------------------ Carteira de credito (agentes especialistas)

PERGUNTAS_CARTEIRA = [
    "Como esta a minha carteira de credito de empresas do segmento varejo, pequeno porte, com presenca na regiao sudeste?",
    "Quais tomadores da minha carteira eu devo olhar primeiro e por que?",
    "Minha inadimplencia em Servicos no Sul esta melhor ou pior que a do mercado? Em quais UFs?",
    "Como evoluiram as safras de credito para medias empresas na minha carteira?",
    "Investigue o tomador mais critico da minha carteira de Varejo pequeno porte no Sudeste em boletos e risco.",
]


@app.get("/carteira")
def carteira():
    insts = credito.instituicoes()
    ispb = request.args.get("ispb") or insts[0]["ispb"]
    return render_template("carteira.html", aba="carteira", instituicoes=insts, ispb=ispb,
                           perguntas=PERGUNTAS_CARTEIRA, score_ativo=bool(credito.SCORE_ENDPOINT))


@app.post("/api/carteira")
def api_carteira():
    d = request.get_json(force=True)
    ispb, pergunta = d.get("ispb"), (d.get("pergunta") or "").strip()
    if not ispb or not pergunta:
        abort(400)
    hist = [m for m in d.get("historico") or [] if m.get("role") in ("user", "assistant") and m.get("content")]
    r = credito.perguntar(ispb, pergunta, hist, usuario())
    r["resposta_html"] = str(_markdown(r["resposta"]))
    return jsonify(r)


# ------------------------------------------------------------------ Uso e custo

@app.get("/uso")
def uso():
    periodo = request.args.get("periodo", "7d")
    if periodo not in usage.PERIODOS:
        periodo = "7d"
    return render_template("uso.html", aba="uso", periodo=periodo, r=usage.resumo(periodo),
                           precos=usage.precos_lista())


@app.post("/uso/precos")
def uso_precos():
    usage.salvar_precos({k: v for k, v in request.form.items() if v.strip()})
    return redirect(url_for("uso", periodo=request.form.get("_periodo", "7d")))


@app.template_filter("brl")
def _brl(v, casas=2):
    txt = f"{float(v or 0):,.{casas}f}"
    return "R$ " + txt.replace(",", "X").replace(".", ",").replace("X", ".")


@app.template_filter("milhar")
def _milhar(v):
    v = float(v or 0)
    for lim, suf in ((1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
        if abs(v) >= lim:
            return f"{v / lim:.1f}".replace(".", ",") + suf
    return f"{v:.0f}"


@app.get("/healthz")
def healthz():
    return "ok"
