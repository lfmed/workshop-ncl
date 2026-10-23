"""Tema 5 - treina o score de inadimplencia PJ (LightGBM) e registra no Unity Catalog com alias champion.

Roda como job serverless (ver 03_submit_train.json). Populacao: CNPJs tomadores (tem ao menos um gravame).
"""
import mlflow
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from pyspark.sql import SparkSession
from sklearn.compose import ColumnTransformer
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

CATALOG, SCHEMA = "workshop_nuclea_genie_catalog", "lab_ml"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.score_inadimplencia_pj"
EXPERIMENT = "/Users/leandro.medeiros@databricks.com/nuclea_tema5_score_pj"

CATEGORICAS = ["porte", "setor", "uf"]
NUMERICAS = [
    "idade_anos", "log_faturamento", "aceita_cartao",
    "ur_valor_constituido", "ur_valor_comprometido", "ur_pct_comprometido", "ur_qtd", "ur_qtd_credenciadoras",
    "grav_qtd_contratos", "grav_valor_contratado", "grav_taxa_media_am", "grav_prazo_medio_meses", "grav_qtd_financiadores",
    "bol_emitidos", "bol_pct_vencido_aberto", "bol_qtd_divergencia_benef", "bol_pagador_qtd", "bol_pagador_pct_vencido_aberto",
    "dup_sacador_qtd", "dup_sacador_pct_nfe_nao_validada", "dup_sacador_pct_negociada", "dup_sacado_qtd",
    "risco_ultimo_score", "risco_consultas_30d", "risco_consultas_total",
    "risco_alertas_qtd", "risco_alertas_alta", "risco_valor_exposto",
]
FEATURES = CATEGORICAS + NUMERICAS


def faixa(p):
    # cortes calibrados na taxa base (~7% entre tomadores)
    return np.select([p < 0.03, p < 0.07, p < 0.15, p < 0.30], ["A", "B", "C", "D"], "E")


class ScoreInadimplencia(mlflow.pyfunc.PythonModel):
    """Recebe as features de um ou mais CNPJs e devolve probabilidade, score 0-1000 (maior = melhor) e faixa."""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def predict(self, context, model_input, params=None):
        x = model_input.copy()
        for c in FEATURES:
            if c not in x.columns:
                x[c] = None
        x = x[FEATURES]
        x[NUMERICAS] = x[NUMERICAS].apply(pd.to_numeric, errors="coerce").astype("float64")
        x[CATEGORICAS] = x[CATEGORICAS].astype("object")
        p = self.pipeline.predict_proba(x)[:, 1]
        return pd.DataFrame({
            "prob_inadimplencia": p.round(6),
            "score": np.round((1 - p) * 1000).astype("int64"),
            "faixa_risco": faixa(p),
        })


def ks(y, p):
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def main():
    spark = SparkSession.builder.getOrCreate()
    df = spark.table(f"{CATALOG}.{SCHEMA}.features_pj").where("tomador = 1").toPandas()
    X, y = df[FEATURES].copy(), df["rotulo_inadimplente"].astype(int)
    X[NUMERICAS] = X[NUMERICAS].astype("float64")
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    pre = ColumnTransformer([
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1), CATEGORICAS),
        ("num", "passthrough", NUMERICAS),
    ])
    clf = LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=40,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                         scale_pos_weight=float((y_tr == 0).sum() / (y_tr == 1).sum()) ** 0.5, verbose=-1)
    pipe = Pipeline([("pre", pre), ("clf", clf)])

    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name="lgbm_inadimplencia_pj") as run:
        pipe.fit(X_tr, y_tr)
        p_te = pipe.predict_proba(X_te)[:, 1]
        auc, k = roc_auc_score(y_te, p_te), ks(y_te, p_te)
        corte = np.quantile(p_te, 0.9)
        lift = float(y_te[p_te >= corte].mean() / y_te.mean())
        mlflow.log_params({"n_treino": len(X_tr), "n_teste": len(X_te), "taxa_positivos": round(float(y.mean()), 4),
                           **{k_: v for k_, v in clf.get_params().items() if k_ in ("n_estimators", "learning_rate", "num_leaves")}})
        mlflow.log_metrics({"auc_teste": auc, "ks_teste": k, "lift_top10": lift})
        imp = pd.Series(clf.feature_importances_, index=FEATURES).sort_values(ascending=False)
        mlflow.log_text(imp.to_string(), "feature_importance.txt")
        print(f"AUC={auc:.4f} KS={k:.4f} lift_top10={lift:.2f}")
        print(imp.head(12).to_string())

        modelo = ScoreInadimplencia(pipe)
        exemplo = X_te.head(3).reset_index(drop=True)
        sig = infer_signature(exemplo, modelo.predict(None, exemplo))
        import lightgbm, sklearn
        info = mlflow.pyfunc.log_model(
            name="model", python_model=modelo, signature=sig, input_example=exemplo,
            registered_model_name=MODEL_NAME,
            pip_requirements=[f"lightgbm=={lightgbm.__version__}", f"scikit-learn=={sklearn.__version__}",
                              f"pandas=={pd.__version__}", f"numpy=={np.__version__}", f"mlflow=={mlflow.__version__}"],
        )
        versao = info.registered_model_version
        cli = MlflowClient(registry_uri="databricks-uc")
        cli.set_registered_model_alias(MODEL_NAME, "champion", versao)
        cli.update_model_version(MODEL_NAME, versao, description=f"LightGBM | AUC={auc:.4f} KS={k:.4f} | run {run.info.run_id}")
        print(f"REGISTRADO {MODEL_NAME} v{versao} alias=champion")


if __name__ == "__main__":
    main()
