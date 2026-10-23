"""Clientes Databricks (service principal do app) e configuracao das salas Genie."""
import json
import os

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

CATALOG = os.getenv("NUCLEA_CATALOG", "workshop_nuclea_genie_catalog")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
LLM_ENDPOINT = os.getenv("SERVING_ENDPOINT", "databricks-claude-sonnet-5-5")

_ids_file = json.load(open(os.path.join(os.path.dirname(__file__), "genie_spaces.json")))

SALAS = {
    "boletos": {"titulo": "Boletos", "subtitulo": "PCR, Consulta de Status e SILOC", "icone": "🧾",
                "pergunta": "Para o CNPJ {cnpj}: quantos boletos emitiu por mes, valor total, % liquidado, e quantos pagamentos "
                            "foram creditados a este CNPJ com divergencia de beneficiario (boleto adulterado), com valor por mes?"},
    "cartoes": {"titulo": "Cartoes", "subtitulo": "R2C3 e SLC", "icone": "💳",
                "pergunta": "Para o CNPJ {cnpj}: valor constituido, cancelado e comprometido da agenda de recebiveis por mes, "
                            "numero de contratos de gravame, quantidade de bancos financiadores distintos e saldo devedor inadimplente."},
    "duplicatas": {"titulo": "Duplicatas", "subtitulo": "Duplicata Escritural", "icone": "📄",
                   "pergunta": "Para o CNPJ {cnpj} como sacador: quantidade e valor de duplicatas por mes, % com NF-e validada, "
                               "% negociadas, % recusadas pelo sacado e tentativas de registro duplicado bloqueadas."},
    "credito": {"titulo": "Credito", "subtitulo": "CTC e C3", "icone": "🏦",
                "pergunta": "Para o CNPJ {cnpj}: cessoes C3 em que ele e originador principal por mes, com quantidade, "
                            "valor de face, tipo de ativo e tipo de cessionario."},
    "pix": {"titulo": "Pix Automatico", "subtitulo": "Autorizacoes e cobrancas", "icone": "⚡",
            "pergunta": "Para o CNPJ {cnpj} como recebedor de Pix Automatico: autorizacoes criadas por mes, % canceladas por "
                        "contestacao e % de cobrancas devolvidas via MED."},
    "risco": {"titulo": "Risco e Fraude", "subtitulo": "Score PJ, Indicadores e Motor de Decisao", "icone": "🛡️",
              "pergunta": "Para o CNPJ {cnpj}: score PJ medio, quantidade de consultas e de participantes consulentes "
                          "distintos por mes, e a lista de alertas de fraude com tipo, data, severidade e status."},
}
# Roteiro do workshop: perguntas que conduzem a investigacao do anel de CNPJs de fachada
ROTEIRO = [
    {"etapa": "1. Detectar os sinais", "perguntas": [
        {"salas": ["risco"], "q": "Liste as 20 empresas abertas ha menos de 1 ano consultadas pelo maior numero de participantes distintos em junho de 2026, comparando com a media de todas as empresas do mesmo porte."},
        {"salas": ["boletos"], "q": "Valor de boletos pagos com divergencia de beneficiario por mes, separando participantes que adotam ou nao a Consulta de Status de Boleto"},
        {"salas": ["pix"], "q": "Quais recebedores de Pix Automatico tem a maior taxa de contestacao?"},
    ]},
    {"etapa": "2. Investigar a rede", "perguntas": [
        {"salas": ["risco"], "q": "Quais CPFs de socio administrador aparecem em mais de 3 CNPJs? Mostre os telefones e dominios de e-mail em comum."},
        {"salas": ["cartoes"], "q": "Empresas abertas ha menos de 1 ano com contratos de gravame em 3 ou mais bancos: valor contratado em relacao ao faturamento declarado"},
        {"salas": ["duplicatas"], "q": "Quais sacadores tem mais valor de duplicatas negociadas sem NF-e validada?"},
        {"salas": ["boletos"], "q": "Quais CNPJs mais receberam creditos de boletos com divergencia de beneficiario?"},
    ]},
    {"etapa": "3. Medir o impacto", "perguntas": [
        {"salas": ["cartoes"], "q": "Saldo devedor inadimplente de contratos de empresas abertas desde novembro de 2025, por banco financiador"},
        {"salas": ["credito"], "q": "Cessoes C3 para FIDC originadas por empresas abertas depois de novembro de 2025: quantidade, valor de face e coobrigacao"},
        {"salas": ["risco"], "q": "Alertas marcados como falso positivo em junho de 2026 para CNPJs que depois tiveram alerta confirmado"},
    ]},
    {"etapa": "4. Olhar um CNPJ em todas as bases", "perguntas": [
        {"salas": ["boletos", "cartoes", "duplicatas", "credito", "pix", "risco"], "q": "Resumo do CNPJ 05633259000193"},
        {"salas": ["cartoes", "boletos"], "q": "O que aconteceu com as liquidacoes do SLC e as janelas do SILOC em 14/08/2026?"},
        {"salas": ["credito"], "q": "Qual credor original mais retem pedidos de portabilidade na CTC?"},
    ]},
]

for k, v in SALAS.items():
    v["space_id"] = os.getenv(f"GENIE_{k.upper()}") or _ids_file[k]
