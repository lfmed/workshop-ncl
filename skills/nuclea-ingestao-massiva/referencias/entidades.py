"""Metadados das entidades ingeridas (ingestor orientado a configuracao: nova base = nova entrada aqui).

chaves_dedup e uma lista FIXA de colunas: a deduplicacao em streaming guarda estado com o schema dessas
colunas. Se ela fosse derivada do schema do arquivo (df.columns), uma coluna nova (schema drift) mudaria a
chave do estado e o flow falharia com STATE_STORE_KEY_SCHEMA_NOT_COMPATIBLE.
"""

ENTIDADES = {
    "boletos_registro": {
        "chaves_dedup": ["id_boleto", "nosso_numero", "ispb_beneficiario", "cnpj_beneficiario", "tipo_pagador", "documento_pagador", "especie", "valor_nominal", "data_registro", "data_vencimento", "canal_registro", "status_atual"],
        "formato": "csv",
        "opcoes": {"header": "true", "pathGlobFilter": "*.csv"},
        # ids/CNPJ/ISPB sempre STRING: inferencia transformaria em numero e perderia zeros a esquerda
        "hints": "id_boleto STRING, nosso_numero STRING, ispb_beneficiario STRING, cnpj_beneficiario STRING, "
                 "documento_pagador STRING, valor_nominal DOUBLE, data_registro DATE, data_vencimento DATE",
        "cluster_by": ["data_registro", "cnpj_beneficiario"],
        "descricao": "Boletos registrados na PCR",
    },
    "boletos_baixas": {
        "chaves_dedup": ["id_baixa", "id_boleto", "data_pagamento", "valor_pago", "ispb_recebedor", "canal_pagamento", "tipo_baixa", "consulta_status_previa", "ispb_creditado", "cnpj_creditado", "divergencia_beneficiario"],
        "formato": "csv",
        "opcoes": {"header": "true", "pathGlobFilter": "*.csv"},
        "hints": "id_baixa STRING, id_boleto STRING, ispb_recebedor STRING, ispb_creditado STRING, cnpj_creditado STRING, "
                 "data_pagamento DATE, valor_pago DOUBLE, consulta_status_previa BOOLEAN, divergencia_beneficiario BOOLEAN",
        "cluster_by": ["data_pagamento"],
        "descricao": "Baixas/pagamentos de boletos",
    },
    "unidades_recebiveis": {
        "chaves_dedup": ["arranjo", "cnpj_recebedor", "data_liquidacao_prevista", "data_registro", "id_ur", "ispb_credenciadora", "ispb_domicilio", "parcela", "qtd_contratos_vinculados", "status_ur", "valor_cancelado", "valor_comprometido", "valor_constituido"],
        "formato": "json",
        "opcoes": {"pathGlobFilter": "*.json"},
        "hints": "id_ur STRING, ispb_credenciadora STRING, cnpj_recebedor STRING, ispb_domicilio STRING, "
                 "data_registro DATE, data_liquidacao_prevista DATE, parcela INT, qtd_contratos_vinculados INT, "
                 "valor_constituido DOUBLE, valor_cancelado DOUBLE, valor_comprometido DOUBLE",
        "cluster_by": ["data_registro", "cnpj_recebedor"],
        "descricao": "Unidades de recebiveis de cartao (R2C3)",
    },
    "empresas_pj": {
        "chaves_dedup": ["idx_empresa", "cnpj", "razao_social", "porte", "setor", "uf", "data_abertura", "faturamento_anual_declarado", "ispb_banco_principal", "telefone_contato", "dominio_email", "cpf_socio_administrador", "aceita_cartao", "rotulo_fraude_gt"],
        "formato": "parquet",
        "opcoes": {"pathGlobFilter": "*.parquet"},
        "hints": None,
        "cluster_by": ["cnpj"],
        "descricao": "Cadastro de empresas PJ",
    },
}
