"""Gera 05_score_cnpj.sql a partir da lista de features do treino (mantem funcao e modelo em sincronia)."""
import ast
import pathlib

src = pathlib.Path(__file__).with_name("02_train.py").read_text()
tree = ast.parse(src)
vals = {t.targets[0].id: ast.literal_eval(t.value) for t in tree.body
        if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name) and t.targets[0].id in ("CATEGORICAS", "NUMERICAS")}
pares = [f"'{c}', f.{c}" for c in vals["CATEGORICAS"]] + [f"'{c}', CAST(f.{c} AS DOUBLE)" for c in vals["NUMERICAS"]]
struct = ",\n        ".join(pares)
sql = f"""-- Tema 5 - funcao SQL de score em tempo real por CNPJ (monta as features e chama o endpoint via ai_query)
-- Gerado por gen_score_sql.py a partir de 02_train.py
CREATE OR REPLACE FUNCTION workshop_nuclea_genie_catalog.lab_ml.score_cnpj(cnpj STRING COMMENT 'CNPJ com ou sem mascara')
RETURNS TABLE (
  cnpj STRING, razao_social STRING, porte STRING, setor STRING, uf STRING,
  prob_inadimplencia DOUBLE, score BIGINT, faixa_risco STRING,
  risco_ultimo_score INT, ur_pct_comprometido DOUBLE, bol_pct_vencido_aberto DOUBLE, risco_alertas_qtd INT
)
COMMENT 'Score de inadimplencia PJ em tempo real (modelo lab_ml.score_inadimplencia_pj@champion servido no endpoint nuclea-score-inadimplencia). score 0-1000: maior = menor risco. faixa_risco A (melhor) a E (pior).'
RETURN
  SELECT x.cnpj, e.razao_social, x.porte, x.setor, x.uf,
         x.r.prob_inadimplencia, x.r.score, x.r.faixa_risco,
         x.risco_ultimo_score, x.ur_pct_comprometido, x.bol_pct_vencido_aberto, x.risco_alertas_qtd
  FROM (
    SELECT f.*, ai_query(
      'nuclea-score-inadimplencia',
      named_struct(
        {struct}),
      returnType => 'STRUCT<prob_inadimplencia: DOUBLE, score: BIGINT, faixa_risco: STRING>') AS r
    FROM workshop_nuclea_genie_catalog.lab_ml.features_pj f
    WHERE f.cnpj = regexp_replace(score_cnpj.cnpj, '[^0-9]', '')
  ) x
  JOIN workshop_nuclea_genie_catalog.cadastro.empresas_pj e ON e.cnpj = x.cnpj;
"""
pathlib.Path(__file__).with_name("05_score_cnpj.sql").write_text(sql)
print("ok", len(pares), "features")
