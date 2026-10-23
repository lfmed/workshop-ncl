"""Monitoramento de carteira de credito: orquestrador LLM + agentes especialistas (UC functions, Genie e score ML).

O ISPB da instituicao e injetado pelo app em toda chamada - o LLM nunca escolhe de quem e a carteira.
"""
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import db
import genie
import usage
from clients import CATALOG, LLM_ENDPOINT, SALAS, w

log = logging.getLogger("credito")
_pool = ThreadPoolExecutor(max_workers=8)

SCHEMA_UC = f"{CATALOG}.lab_credito"
SCORE_ENDPOINT = os.getenv("SCORE_ENDPOINT")  # tema 5 (opcional)
MAX_PASSOS = 8
MAX_LINHAS_LLM = 60

# Ferramenta UC -> agente especialista exibido na interface
AGENTES_UC = {
    "resumo_carteira": ("Agente Carteira", "📊"),
    "quebra_carteira": ("Agente Carteira", "📊"),
    "evolucao_carteira": ("Agente Carteira", "📊"),
    "maiores_exposicoes": ("Agente Exposicao", "🎯"),
    "sinais_alerta": ("Agente Alerta Precoce", "🚨"),
}

PROMPT = """Voce e o orquestrador de monitoramento de credito da Nuclea, atendendo a instituicao financeira {nome} (ISPB {ispb}).
Voce coordena agentes especialistas (ferramentas). Data de referencia dos dados: 30/09/2026.

Regras:
- SEMPRE use as ferramentas antes de responder; nunca invente numeros. Chame varias ferramentas em paralelo quando fizer sentido.
- A carteira e sempre a da instituicao atendida (o ISPB e aplicado automaticamente). Compare sempre com o mercado.
- Traduza o pedido em filtros: "pequeno porte" = porte "Pequeno" (MEI, ME, EPP); "medio porte" = "Medio";
  regioes: Sudeste, Sul, Nordeste, Norte, Centro-Oeste (ou UFs como "SP,RJ"). Setores: Varejo, Servicos, Industria, Atacado,
  Construcao, Saude, Agronegocio, Tecnologia, Educacao, Logistica.
- Para "como esta minha carteira": resumo_carteira + evolucao_carteira + quebra (dimensao relevante) + maiores_exposicoes + sinais_alerta.
- Use investigar_cnpj apenas para aprofundar 1 a 3 tomadores criticos da carteira, quando o usuario pedir detalhe ou houver sinais graves.
{score_regra}
Formato da resposta (markdown, portugues, objetivo, valores em R$ no padrao brasileiro):
1. **Resumo executivo** (3-4 frases com o veredito)
2. **Indicadores vs mercado** (tabela curta)
3. **Tendencia** (safras)
4. **Concentracao** (maiores exposicoes e distribuicao)
5. **Sinais de alerta** (tomadores que exigem acao, com o motivo)
6. **Recomendacoes** (acoes praticas de monitoramento/cobranca/limite)
Para perguntas pontuais, responda direto sem forcar o formato completo.
"""


def _tipo_json(t):
    return {"INT": "integer", "LONG": "integer", "BIGINT": "integer", "DOUBLE": "number", "BOOLEAN": "boolean"}.get(t, "string")


_tools_cache = {}


def ferramentas():
    """Monta as definicoes de ferramentas a partir dos metadados das UC functions (fonte unica da verdade)."""
    if "tools" in _tools_cache:
        return _tools_cache["tools"]
    tools = []
    for nome in AGENTES_UC:
        f = w.functions.get(f"{SCHEMA_UC}.{nome}")
        props = {}
        for p in (f.input_params.parameters if f.input_params else []):
            if p.name == "p_ispb":
                continue
            props[p.name] = {"type": _tipo_json(p.type_name.value if p.type_name else "STRING"),
                             "description": p.comment or p.name}
        tools.append({"type": "function", "function": {"name": nome, "description": f.comment or nome,
                                                       "parameters": {"type": "object", "properties": props}}})
    tools.append({"type": "function", "function": {
        "name": "investigar_cnpj",
        "description": "Agente Investigador: aprofunda um tomador DA SUA CARTEIRA consultando as salas Genie das bases Nuclea "
                       "(boletos, cartoes, duplicatas, credito, pix, risco). Use para 1 a 3 CNPJs criticos.",
        "parameters": {"type": "object", "required": ["cnpj", "bases"], "properties": {
            "cnpj": {"type": "string", "description": "CNPJ com 14 digitos"},
            "bases": {"type": "array", "items": {"type": "string", "enum": list(SALAS)},
                      "description": "Bases a consultar (max 3)"},
            "pergunta": {"type": "string", "description": "Pergunta especifica (opcional); padrao = pergunta da base"}}}}})
    if SCORE_ENDPOINT:
        tools.append({"type": "function", "function": {
            "name": "score_inadimplencia",
            "description": "Agente Score ML: probabilidade de inadimplencia (modelo servido em tempo real) para ate 50 CNPJs da carteira.",
            "parameters": {"type": "object", "required": ["cnpjs"], "properties": {
                "cnpjs": {"type": "array", "items": {"type": "string"}, "description": "Lista de CNPJs (14 digitos)"}}}}})
    _tools_cache["tools"] = tools
    return tools


def instituicoes():
    if "inst" not in _tools_cache:
        _tools_cache["inst"] = genie.sql(f"SELECT * FROM {SCHEMA_UC}.instituicoes()", origem="credito_inst")
    return _tools_cache["inst"]


def _sql_tabela(statement, params, ctx):
    rows = genie.sql(statement, params, origem="credito_tool", **ctx)
    cols = list(rows[0].keys()) if rows else []
    return cols, [list(r.values()) for r in rows]


def _uc(nome, args, ispb, ctx):
    tool = next(t for t in ferramentas() if t["function"]["name"] == nome)["function"]
    validos = {k: v for k, v in args.items() if k in tool["parameters"]["properties"] and v not in (None, "")}
    params = {"p_ispb": ispb, **{k: str(v) for k, v in validos.items()}}
    tipos = {k: tool["parameters"]["properties"][k]["type"] for k in validos}
    chamada = ", ".join(f"{k} => " + (f"CAST(:{k} AS INT)" if tipos.get(k) == "integer" else f":{k}") for k in params)
    return _sql_tabela(f"SELECT * FROM {SCHEMA_UC}.{nome}({chamada})", params, ctx)


def _na_carteira(cnpj, ispb, ctx):
    r = genie.sql(f"SELECT count(*) n FROM {SCHEMA_UC}.carteira_contratos WHERE cnpj = :c AND ispb_financiador = :i",
                  {"c": cnpj, "i": ispb}, origem="credito_tool", **ctx)
    return int(r[0]["n"]) > 0


def _investigar(args, ispb, ctx):
    cnpj = re.sub(r"\D", "", args.get("cnpj", ""))
    if not _na_carteira(cnpj, ispb, ctx):
        return {"erro": f"CNPJ {cnpj} nao pertence a carteira desta instituicao - acesso negado."}
    bases = [b for b in args.get("bases") or [] if b in SALAS][:3] or ["risco"]
    futs = {b: _pool.submit(genie.ask, b, (args.get("pergunta") or SALAS[b]["pergunta"]).replace("{cnpj}", cnpj),
                            uso={"origem": "credito_agente", "cnpj": cnpj, "usuario": ctx.get("usuario")}, retry=True)
            for b in bases}
    out = {}
    for b, f in futs.items():
        r = f.result()
        out[b] = {"texto": r["texto"], "erro": r["erro"], "colunas": r["colunas"], "linhas": r["linhas"][:30]}
    return out


def _score(args, ispb, ctx):
    cnpjs = [re.sub(r"\D", "", c) for c in args.get("cnpjs") or []][:50]
    if not cnpjs:
        return {"erro": "informe cnpjs"}
    fora = [c for c in cnpjs if not _na_carteira(c, ispb, ctx)]
    cnpjs = [c for c in cnpjs if c not in fora]
    t0 = time.time()
    resp = w.api_client.do("POST", f"/serving-endpoints/{SCORE_ENDPOINT}/invocations",
                           body={"dataframe_records": [{"cnpj": c} for c in cnpjs]})
    usage.registrar("llm", "credito_score", sala="score", status="OK", duracao_ms=int((time.time() - t0) * 1000),
                    usuario=ctx.get("usuario"))
    preds = resp.get("predictions", [])
    return {"colunas": ["cnpj", "prob_inadimplencia"], "linhas": [[c, p] for c, p in zip(cnpjs, preds)],
            "negados_fora_da_carteira": fora, "latencia_ms": int((time.time() - t0) * 1000)}


def executar_ferramenta(nome, args, ispb, ctx):
    """Retorna (agente, icone, resultado_para_ui, texto_para_llm)."""
    t0 = time.time()
    try:
        if nome in AGENTES_UC:
            agente, icone = AGENTES_UC[nome]
            cols, linhas = _uc(nome, args, ispb, ctx)
            res = {"colunas": cols, "linhas": linhas}
            llm = {"colunas": cols, "linhas": linhas[:MAX_LINHAS_LLM], "total_linhas": len(linhas)}
        elif nome == "investigar_cnpj":
            agente, icone = "Agente Investigador (Genie)", "🔎"
            res = llm = _investigar(args, ispb, ctx)
        elif nome == "score_inadimplencia" and SCORE_ENDPOINT:
            agente, icone = "Agente Score ML", "🤖"
            res = llm = _score(args, ispb, ctx)
        else:
            return "?", "❓", {"erro": f"ferramenta desconhecida {nome}"}, json.dumps({"erro": "ferramenta desconhecida"})
    except Exception as e:  # noqa: BLE001 - o LLM recebe o erro e pode corrigir os argumentos
        log.exception("ferramenta %s", nome)
        agente, icone = AGENTES_UC.get(nome, (nome, "⚠️"))
        res = llm = {"erro": str(e)[:500]}
    res["ms"] = int((time.time() - t0) * 1000)
    return agente, icone, res, json.dumps(llm, ensure_ascii=False, default=str)


def _texto(msg):
    c = msg.get("content")
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return c or ""


def perguntar(ispb, pergunta, historico, usuario=None):
    """Executa o loop orquestrador. historico = [{role, content}] das trocas anteriores (so texto)."""
    inst = next((i for i in instituicoes() if i["ispb"] == ispb), None)
    if not inst:
        raise ValueError("ISPB sem carteira")
    ctx = {"usuario": usuario}
    sistema = PROMPT.format(nome=inst["nome_participante"], ispb=ispb, score_regra=(
        "- Use score_inadimplencia para estimar o risco futuro dos maiores tomadores ou dos que tem sinais de alerta."
        if SCORE_ENDPOINT else ""))
    msgs = [{"role": "system", "content": sistema}] + historico[-10:] + [{"role": "user", "content": pergunta}]
    passos, tokens_in, tokens_out, t0 = [], 0, 0, time.time()
    for _ in range(MAX_PASSOS):
        resp = w.api_client.do("POST", f"/serving-endpoints/{LLM_ENDPOINT}/invocations",
                               body={"messages": msgs, "tools": ferramentas(), "max_tokens": 8000})
        u = resp.get("usage") or {}
        tokens_in += u.get("prompt_tokens") or 0
        tokens_out += u.get("completion_tokens") or 0
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            resposta = _texto(msg)
            break
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        futs = [(c, _pool.submit(executar_ferramenta, c["function"]["name"],
                                 json.loads(c["function"].get("arguments") or "{}"), ispb, ctx)) for c in calls]
        for c, f in futs:
            agente, icone, res, llm = f.result()
            passos.append({"agente": agente, "icone": icone, "ferramenta": c["function"]["name"],
                           "args": json.loads(c["function"].get("arguments") or "{}"), "resultado": res})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": llm})
    else:
        resposta = "_Limite de passos atingido; refine a pergunta._"
    duracao = int((time.time() - t0) * 1000)
    usage.registrar("llm", "credito_agente", sala="carteira", status="OK", duracao_ms=duracao,
                    tokens_entrada=tokens_in, tokens_saida=tokens_out, usuario=usuario)
    db.q("""INSERT INTO {S}.credito_mensagens (ispb, usuario, pergunta, resposta, passos, duracao_ms, tokens_entrada, tokens_saida)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
         (ispb, usuario, pergunta, resposta, json.dumps(passos, default=str), duracao, tokens_in, tokens_out))
    return {"resposta": resposta, "passos": passos, "duracao_ms": duracao, "tokens": tokens_in + tokens_out}
