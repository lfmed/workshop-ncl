"""Regras de qualidade (fonte unica) usadas pelas expectations da silver e pela quarentena.

Criticidade:
  fail -> invariante critico: aborta o update (nunca deveria acontecer; indica falha do processo de ingestao)
  drop -> registro invalido: sai da silver e vai para a quarentena com o motivo
  warn -> alerta de negocio: registro segue para a silver, mas a violacao fica medida no event log

Toda regra e embrulhada em coalesce(..., false): NULL conta como violacao, nunca como aprovacao.
"""
from pyspark.sql import functions as F

CNPJ_OK = "RLIKE '^[0-9]{14}$'"
FAIL_PADRAO = {"lote_identificado": "_lote IS NOT NULL", "arquivo_rastreavel": "_arquivo IS NOT NULL"}

REGRAS = {
    "boletos_registro": {
        "fail": FAIL_PADRAO,
        "drop": {
            "id_boleto_obrigatorio": "id_boleto IS NOT NULL",
            "valor_nominal_positivo": "valor_nominal > 0",
            "vencimento_apos_registro": "data_vencimento >= data_registro",
            "cnpj_beneficiario_14_digitos": f"cnpj_beneficiario {CNPJ_OK}",
            "sem_dados_resgatados": "_rescued_data IS NULL",
        },
        "warn": {
            "especie_conhecida": "especie IN ('DM','DS','CC','ME','FAT','BDP','OUT')",
            "valor_ate_1_milhao": "valor_nominal <= 1000000",
        },
    },
    "boletos_baixas": {
        "fail": FAIL_PADRAO,
        "drop": {
            "id_baixa_obrigatorio": "id_baixa IS NOT NULL",
            "id_boleto_obrigatorio": "id_boleto IS NOT NULL",
            "valor_pago_positivo": "valor_pago > 0",
            "sem_dados_resgatados": "_rescued_data IS NULL",
        },
        "warn": {"sem_divergencia_beneficiario": "NOT divergencia_beneficiario"},
    },
    "unidades_recebiveis": {
        "fail": FAIL_PADRAO,
        "drop": {
            "id_ur_obrigatorio": "id_ur IS NOT NULL",
            "valor_constituido_positivo": "valor_constituido > 0",
            "cnpj_recebedor_14_digitos": f"cnpj_recebedor {CNPJ_OK}",
            "liquidacao_apos_registro": "data_liquidacao_prevista >= data_registro",
            "sem_dados_resgatados": "_rescued_data IS NULL",
        },
        "warn": {"comprometido_ate_constituido": "valor_comprometido <= valor_constituido"},
    },
    "empresas_pj": {
        "fail": FAIL_PADRAO,
        "drop": {
            "cnpj_14_digitos": f"cnpj {CNPJ_OK}",
            "data_abertura_valida": "data_abertura BETWEEN DATE'1900-01-01' AND current_date()",
            "faturamento_nao_negativo": "faturamento_anual_declarado >= 0",
            "sem_dados_resgatados": "_rescued_data IS NULL",
        },
        "warn": {"uf_preenchida": "uf IS NOT NULL", "porte_conhecido": "porte IN ('MEI','ME','EPP','Medio','Grande')"},
    },
}


def seguras(regras: dict) -> dict:
    return {nome: f"coalesce(({cond}), false)" for nome, cond in regras.items()}


def condicao_valida(entidade: str) -> str:
    """Registro aceito na silver = passa em todas as regras fail + drop."""
    r = REGRAS[entidade]
    return " AND ".join(seguras({**r["fail"], **r["drop"]}).values())


def motivos(entidade: str):
    """Array com o nome de cada regra drop/fail violada (vai para a coluna _motivos da quarentena)."""
    r = REGRAS[entidade]
    falhas = [F.when(~F.expr(c), F.lit(n)) for n, c in seguras({**r["fail"], **r["drop"]}).items()]
    return F.filter(F.array(*falhas), lambda x: x.isNotNull())
