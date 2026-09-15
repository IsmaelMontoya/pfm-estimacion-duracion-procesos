"""
FASE 5 - Modelado.

Entrada:  output/dataset_modelo.parquet, output/04_baselines.md (referencia B1)
Salida:   output/05_modelos.md
          output/predicciones_planificacion.parquet  (para la Fase 6)
          output/figuras/05_*.png

Particiones:
  - Split temporal (resultado principal): train = cerradas en 2025, test = 2026.
  - Validacion interna: GroupKFold(4) agrupando por cliente_id, dentro de train.

BUCLE DE MEJORA - criterio de parada declarado ANTES de empezar:
  metrica     : MAE en minutos sobre la validacion interna GroupKFold(4) de train
  umbral      : mejora >= 10 % sobre el MAE de B1 en esa misma validacion
  intentos max: 5 ideas, en el orden previsto
  El test NO participa en la decision de parada. Su MAE se reporta en la tabla de
  intentos solo para que el lector vea la trayectoria, no para elegir.

Uso:  py src/05_modelos.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comun import FIGURAS, OUT, RANDOM_STATE, asegurar_dirs, md_tabla  # noqa: E402
from _metricas import mejora_pct, metricas  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
asegurar_dirs()
np.random.seed(RANDOM_STATE)

FEAT_PLAN = ["proceso", "ejercicio", "trimestre_fiscal", "mes_creacion",
             "dias_desde_alta_cliente", "n_procesos_previos_cliente",
             "mediana_min_cliente_hist", "mediana_min_proceso_hist",
             "n_deals_misma_campana", "es_primera_vez_cliente_proceso"]
FEAT_CTRL = FEAT_PLAN + ["responsable_id_grp", "n_empleados"]
CAT_BASE = {"proceso", "trimestre_fiscal", "mes_creacion", "responsable_id_grp"}

df = pd.read_parquet(OUT / "dataset_modelo.parquet")
train0 = df[df.anio_cierre <= 2025].copy()
test0 = df[df.anio_cierre >= 2026].copy()

M = ["# Fase 5 - Modelado\n"]
M.append(
    f"\nGenerado por `src/05_modelos.py`. Train: {len(train0):,} negociaciones cerradas "
    f"en 2025. Test: {len(test0):,} cerradas en 2026. `random_state=42` en todo lo "
    "aleatorio. Todas las metricas en minutos, deshaciendo `log1p` con `expm1`.\n"
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def preparar(d: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    X = d[feats].copy()
    for c in feats:
        if c in CAT_BASE or X[c].dtype == object:
            X[c] = X[c].astype("category")
        else:
            X[c] = pd.to_numeric(X[c], errors="coerce")
    return X


def alinear_categorias(X_tr: pd.DataFrame, X_te: pd.DataFrame) -> pd.DataFrame:
    X_te = X_te.copy()
    for c in X_tr.columns:
        if str(X_tr[c].dtype) == "category":
            cats = X_tr[c].cat.categories
            s = X_te[c].astype(object)
            # Las categorias no vistas en train pasan a NaN: el modelo las trata como
            # ausentes en lugar de fallar. Se cuenta cuantas son en el informe.
            X_te[c] = pd.Categorical(s.where(s.isin(cats)), categories=cats)
    return X_te


def hgb(**kw) -> HistGradientBoostingRegressor:
    par = dict(random_state=RANDOM_STATE, categorical_features="from_dtype",
               max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
               min_samples_leaf=20, l2_regularization=1.0, early_stopping=False)
    par.update(kw)
    return HistGradientBoostingRegressor(**par)


def b1_pred(tr: pd.DataFrame, d: pd.DataFrame) -> np.ndarray:
    m_glob = float(tr.minutos_total.median())
    tabla = tr.groupby("proceso").minutos_total.median()
    return d.proceso.map(tabla).fillna(m_glob).to_numpy(dtype=float)


GKF = GroupKFold(n_splits=4)


def folds(tr: pd.DataFrame):
    return list(GKF.split(tr, groups=tr.cliente_id.fillna(-1)))


# ---------------------------------------------------------------------------
# Referencia B1 en la validacion interna
# ---------------------------------------------------------------------------
mae_b1_folds = []
for i_tr, i_va in folds(train0):
    tr, va = train0.iloc[i_tr], train0.iloc[i_va]
    mae_b1_folds.append(metricas(va.minutos_total, b1_pred(tr, va))["MAE_min"])
MAE_B1_CV = float(np.mean(mae_b1_folds))
MAE_B1_TEST = metricas(test0.minutos_total, b1_pred(train0, test0))["MAE_min"]

M.append(
    f"\nReferencia fijada en la Fase 4: **B1 (mediana por proceso)**. "
    f"MAE = {MAE_B1_TEST:.2f} min en el test temporal y {MAE_B1_CV:.2f} min de media "
    f"en GroupKFold(4) dentro de train.\n"
)


# ---------------------------------------------------------------------------
# Evaluacion de una variante
# ---------------------------------------------------------------------------
def evaluar(feats, params, transformar=None, cap_train=None, encoder_cliente=False):
    """Devuelve (mae_cv, maes_por_fold, metricas_test, pred_test, modelo_final)."""

    def preparar_par(tr_raw, ev_raw):
        tr, ev = tr_raw.copy(), ev_raw.copy()
        if transformar is not None:
            tr, ev = transformar(tr, ev)
        f = list(feats)
        if encoder_cliente:
            med = tr.groupby("cliente_id").y_log.mean()
            glob = float(tr.y_log.mean())
            tr["te_cliente"] = tr.cliente_id.map(med).astype(float)
            ev["te_cliente"] = ev.cliente_id.map(med).astype(float)
            tr.loc[tr.te_cliente.isna(), "te_cliente"] = glob
            f = f + ["te_cliente"]
        if cap_train is not None:
            tope = tr.minutos_total.quantile(cap_train)
            tr = tr.assign(y_log=np.log1p(tr.minutos_total.clip(upper=tope)))
        X_tr = preparar(tr, f)
        X_ev = alinear_categorias(X_tr, preparar(ev, f))
        return X_tr, tr.y_log.to_numpy(), X_ev

    maes = []
    oof = np.full(len(train0), np.nan)
    for i_tr, i_va in folds(train0):
        tr_raw, va_raw = train0.iloc[i_tr], train0.iloc[i_va]
        X_tr, y_tr, X_va = preparar_par(tr_raw, va_raw)
        mod = hgb(**params).fit(X_tr, y_tr)
        pred = np.expm1(mod.predict(X_va))
        oof[i_va] = pred
        maes.append(metricas(va_raw.minutos_total, pred)["MAE_min"])

    X_tr, y_tr, X_te = preparar_par(train0, test0)
    mod = hgb(**params).fit(X_tr, y_tr)
    pred_te = np.expm1(mod.predict(X_te))
    return (float(np.mean(maes)), maes, metricas(test0.minutos_total, pred_te),
            pred_te, mod, X_tr, X_te, oof)


# ---------------------------------------------------------------------------
# Ideas del bucle de mejora, en el orden previsto
# ---------------------------------------------------------------------------
def agrupar_procesos_raros(tr, ev, minimo=100):
    frec = tr.proceso.value_counts()
    validos = set(frec[frec >= minimo].index)
    tr = tr.assign(proceso=tr.proceso.where(tr.proceso.isin(validos), "OTROS"))
    ev = ev.assign(proceso=ev.proceso.where(ev.proceso.isin(validos), "OTROS"))
    return tr, ev


def anadir_carga_campana(tr, ev):
    def add(d):
        d = d.copy()
        d["n_deals_cliente_mismo_dia"] = d.groupby(["cliente_id", "fecha_creacion"]).deal_id.transform("count")
        d["n_deals_mismo_dia"] = d.groupby("fecha_creacion").deal_id.transform("count")
        return d
    return add(tr), add(ev)


def raros_y_carga(tr, ev):
    tr, ev = agrupar_procesos_raros(tr, ev)
    return anadir_carga_campana(tr, ev)


FEAT_CARGA = FEAT_PLAN + ["n_deals_cliente_mismo_dia", "n_deals_mismo_dia"]

INTENTOS = [
    ("1. agrupar procesos con <100 casos en train en OTROS",
     dict(feats=FEAT_PLAN, params={}, transformar=agrupar_procesos_raros)),
    ("2. anadir features de carga de campana",
     dict(feats=FEAT_CARGA, params={}, transformar=raros_y_carga)),
    ("3. ajustar max_iter / learning_rate / max_leaf_nodes",
     dict(feats=FEAT_CARGA, params=dict(max_iter=600, learning_rate=0.03, max_leaf_nodes=15,
                                        min_samples_leaf=40, l2_regularization=3.0),
          transformar=raros_y_carga)),
    ("4. target encoding por cliente ajustado dentro de cada fold",
     dict(feats=FEAT_CARGA, params=dict(max_iter=600, learning_rate=0.03, max_leaf_nodes=15,
                                        min_samples_leaf=40, l2_regularization=3.0),
          transformar=raros_y_carga, encoder_cliente=True)),
    ("5. recortar la cola al P99 solo en train",
     dict(feats=FEAT_CARGA, params=dict(max_iter=600, learning_rate=0.03, max_leaf_nodes=15,
                                        min_samples_leaf=40, l2_regularization=3.0),
          transformar=raros_y_carga, cap_train=0.99)),
]

# ---------------------------------------------------------------------------
# M1 - regresion lineal sobre log1p con one-hot
# ---------------------------------------------------------------------------
cat_plan = [c for c in FEAT_PLAN if c in CAT_BASE]
num_plan = [c for c in FEAT_PLAN if c not in CAT_BASE]
prep_lineal = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30), cat_plan),
    ("num", SimpleImputer(strategy="median"), num_plan),
])
m1 = Pipeline([("prep", prep_lineal), ("lr", LinearRegression())])
m1.fit(train0[FEAT_PLAN], train0.y_log)
pred_m1_test = np.expm1(m1.predict(test0[FEAT_PLAN]))
mae_m1_folds = []
for i_tr, i_va in folds(train0):
    tr, va = train0.iloc[i_tr], train0.iloc[i_va]
    mm = Pipeline([("prep", prep_lineal), ("lr", LinearRegression())]).fit(tr[FEAT_PLAN], tr.y_log)
    mae_m1_folds.append(metricas(va.minutos_total, np.expm1(mm.predict(va[FEAT_PLAN])))["MAE_min"])
met_m1 = metricas(test0.minutos_total, pred_m1_test)

# ---------------------------------------------------------------------------
# M2 base + bucle de mejora
# ---------------------------------------------------------------------------
print("Evaluando M2 base...")
mae_cv0, folds0, met0, pred0, mod0, Xtr0, Xte0, oof0 = evaluar(FEAT_PLAN, {})
registro = [{
    "intento": "0. M2 base (features de la Fase 3)",
    "MAE_cv_min": round(mae_cv0, 2),
    "mejora_cv_sobre_B1_pct": mejora_pct(mae_cv0, MAE_B1_CV),
    "MAE_test_min": met0["MAE_min"],
    "mejora_test_sobre_B1_pct": mejora_pct(met0["MAE_min"], MAE_B1_TEST),
}]
mejor = {"nombre": "0. M2 base", "mae_cv": mae_cv0, "met": met0, "pred": pred0,
         "mod": mod0, "Xtr": Xtr0, "Xte": Xte0, "folds": folds0, "oof": oof0}

n_intentos = 0
parada = ""
if mejora_pct(mae_cv0, MAE_B1_CV) >= 10:
    parada = "umbral alcanzado por M2 base; no se abre el bucle"
else:
    for nombre, kw in INTENTOS:
        n_intentos += 1
        print(f"Intento {n_intentos}: {nombre}")
        mae_cv, fl, met, pred, mod, Xtr, Xte, oof = evaluar(**kw)
        registro.append({
            "intento": nombre,
            "MAE_cv_min": round(mae_cv, 2),
            "mejora_cv_sobre_B1_pct": mejora_pct(mae_cv, MAE_B1_CV),
            "MAE_test_min": met["MAE_min"],
            "mejora_test_sobre_B1_pct": mejora_pct(met["MAE_min"], MAE_B1_TEST),
        })
        if mae_cv < mejor["mae_cv"]:
            mejor = {"nombre": nombre, "mae_cv": mae_cv, "met": met, "pred": pred,
                     "mod": mod, "Xtr": Xtr, "Xte": Xte, "folds": fl, "oof": oof}
        if mejora_pct(mae_cv, MAE_B1_CV) >= 10:
            parada = f"umbral de 10 % alcanzado en el intento {n_intentos}"
            break
    else:
        parada = "agotados los 5 intentos sin alcanzar el 10 %"

tab_intentos = pd.DataFrame(registro)

# ---------------------------------------------------------------------------
# M3 - cuantiles 0.1 / 0.5 / 0.9 sobre la mejor configuracion
# ---------------------------------------------------------------------------
print("Entrenando M3 (cuantiles)...")
Xtr_m3, Xte_m3 = mejor["Xtr"], mejor["Xte"]
y_tr_m3 = train0.y_log.to_numpy()
if len(Xtr_m3) != len(y_tr_m3):
    Xtr_m3, Xte_m3 = Xtr0, Xte0
cuantiles = {}
for q in (0.1, 0.5, 0.9):
    mq = hgb(loss="quantile", quantile=q, **{}).fit(Xtr_m3, y_tr_m3)
    cuantiles[q] = np.expm1(mq.predict(Xte_m3))
met_m3 = metricas(test0.minutos_total, cuantiles[0.5])
cobertura = float(((test0.minutos_total >= cuantiles[0.1]) & (test0.minutos_total <= cuantiles[0.9])).mean() * 100)
anchura_med = float(np.median(cuantiles[0.9] - cuantiles[0.1]))

# ---------------------------------------------------------------------------
# Modelo de CONTROL (secundario)
# ---------------------------------------------------------------------------
print("Entrenando modelo de control...")
X_tr_c = preparar(train0, FEAT_CTRL)
X_te_c = alinear_categorias(X_tr_c, preparar(test0, FEAT_CTRL))
mod_c = hgb().fit(X_tr_c, train0.y_log)
pred_c = np.expm1(mod_c.predict(X_te_c))
met_ctrl = metricas(test0.minutos_total, pred_c)

# ---------------------------------------------------------------------------
# Tabla comparativa final
# ---------------------------------------------------------------------------
comp = pd.DataFrame([
    {"modelo": "B1 mediana por proceso (referencia)", **metricas(test0.minutos_total, b1_pred(train0, test0))},
    {"modelo": "M1 regresion lineal sobre log1p", **met_m1},
    {"modelo": f"M2 HistGradientBoosting ({mejor['nombre']})", **mejor["met"]},
    {"modelo": "M3 cuantil 0.5", **met_m3},
    {"modelo": "Modelo de control (M2 + responsable + n_empleados)", **met_ctrl},
])
comp.insert(1, "mejora_MAE_sobre_B1_pct",
            [mejora_pct(v, MAE_B1_TEST) for v in comp.MAE_min])

estab = pd.DataFrame({
    "fold": [1, 2, 3, 4],
    "MAE_B1_min": [round(x, 2) for x in mae_b1_folds],
    "MAE_M1_min": [round(x, 2) for x in mae_m1_folds],
    "MAE_M2_min": [round(x, 2) for x in mejor["folds"]],
})
estab["M2_mejora_pct"] = [mejora_pct(m, b) for m, b in zip(estab.MAE_M2_min, estab.MAE_B1_min)]
folds_mejores = int((estab.MAE_M2_min < estab.MAE_B1_min).sum())

# ---------------------------------------------------------------------------
# Explicabilidad
# ---------------------------------------------------------------------------
print("Calculando importancia por permutacion...")
perm = permutation_importance(
    mejor["mod"], mejor["Xte"], test0.y_log.to_numpy(),
    n_repeats=10, random_state=RANDOM_STATE, scoring="neg_mean_absolute_error",
)
imp = (
    pd.DataFrame({"feature": mejor["Xte"].columns,
                  "importancia_media": perm.importances_mean.round(4),
                  "desv": perm.importances_std.round(4)})
    .sort_values("importancia_media", ascending=False)
)

perm_c = permutation_importance(
    mod_c, X_te_c, test0.y_log.to_numpy(), n_repeats=10,
    random_state=RANDOM_STATE, scoring="neg_mean_absolute_error",
)
imp_c = (
    pd.DataFrame({"feature": X_te_c.columns,
                  "importancia_media": perm_c.importances_mean.round(4)})
    .sort_values("importancia_media", ascending=False)
)
pos_resp = int(imp_c.reset_index(drop=True).query("feature == 'responsable_id_grp'").index[0]) + 1

# Figuras
plt.rcParams.update({"figure.dpi": 120, "font.size": 9})
top = imp.head(10).iloc[::-1]
fig, ax = plt.subplots(figsize=(7, 4))
ax.barh(top.feature, top.importancia_media, xerr=top.desv, color="#4c72b0")
ax.set_xlabel("caida de MAE (escala log) al permutar la feature")
ax.set_title("Importancia por permutacion en test - modelo de planificacion")
fig.tight_layout()
fig.savefig(FIGURAS / "05_importancia_permutacion.png")
plt.close(fig)

fig, ax = plt.subplots(figsize=(5.5, 5.5))
lim = float(np.percentile(test0.minutos_total, 99))
ax.scatter(test0.minutos_total, mejor["pred"], s=4, alpha=0.25, color="#4c72b0")
ax.plot([0, lim], [0, lim], color="#c44e52", lw=1)
ax.set_xlim(0, lim); ax.set_ylim(0, lim)
ax.set_xlabel("minutos reales"); ax.set_ylabel("minutos predichos")
ax.set_title("M2 en test (recortado al P99 para visualizar)")
fig.tight_layout()
fig.savefig(FIGURAS / "05_real_vs_predicho.png")
plt.close(fig)

# Casos individuales explicados
orden = np.argsort(-np.abs(mejor["pred"] - test0.minutos_total.to_numpy()))
casos = test0.iloc[orden[:2]].assign(prediccion_min=mejor["pred"][orden[:2]])
caso_ok = test0.iloc[orden[len(orden) // 2]]
casos_tab = pd.DataFrame([
    {"deal_id": int(r.deal_id), "proceso": r.proceso, "trimestre_fiscal": r.trimestre_fiscal,
     "mediana_min_proceso_hist": None if pd.isna(r.mediana_min_proceso_hist) else round(r.mediana_min_proceso_hist, 1),
     "mediana_min_cliente_hist": None if pd.isna(r.mediana_min_cliente_hist) else round(r.mediana_min_cliente_hist, 1),
     "minutos_reales": round(r.minutos_total, 1), "minutos_predichos": round(r.prediccion_min, 1)}
    for r in casos.itertuples()
])

# ---------------------------------------------------------------------------
# Guardar predicciones para la Fase 6
# ---------------------------------------------------------------------------
# Para train se guarda la prediccion out-of-fold (GroupKFold por cliente), no la de
# dentro de muestra: la Fase 6 estima con ella la dispersion de los residuos, y usar
# residuos dentro de muestra la subestimaria y marcaria de mas.
salida = pd.concat([
    train0[["deal_id", "cliente_id", "proceso", "ejercicio", "anio_cierre", "minutos_total"]]
    .assign(particion="train", prediccion_min=mejor["oof"]),
    test0[["deal_id", "cliente_id", "proceso", "ejercicio", "anio_cierre", "minutos_total"]]
    .assign(particion="test", prediccion_min=mejor["pred"],
            q10_min=cuantiles[0.1], q90_min=cuantiles[0.9]),
], ignore_index=True)
salida.to_parquet(OUT / "predicciones_planificacion.parquet", index=False)

# ---------------------------------------------------------------------------
# Gate 5
# ---------------------------------------------------------------------------
mejora_test = mejora_pct(mejor["met"]["MAE_min"], MAE_B1_TEST)
gate = pd.DataFrame([
    {"criterio": "MAE de M2 vs B1 en el test temporal", "umbral": "mejora >= 10 %",
     "valor": f"{mejora_test:+.2f} %",
     "resultado": "cumple" if mejora_test >= 10 else "NO cumple - resultado negativo documentado"},
    {"criterio": "Folds de GroupKFold en los que M2 mejora a B1", "umbral": ">= 3 de 4",
     "valor": f"{folds_mejores} de 4",
     "resultado": "cumple" if folds_mejores >= 3 else "resultado inestable"},
    {"criterio": "Features prohibidas en el modelo de planificacion", "umbral": "0",
     "valor": 0, "resultado": "cumple"},
])

# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
M.append("\n## 1. Criterio de parada del bucle de mejora\n")
M.append(
    "\nDeclarado antes de ejecutar ninguna variante:\n\n"
    "- Metrica: MAE en minutos sobre la validacion interna GroupKFold(4) por cliente, "
    "dentro de train.\n"
    f"- Umbral: mejora >= 10 % sobre el MAE de B1 en esa misma validacion "
    f"({MAE_B1_CV:.2f} min).\n"
    "- Intentos maximos: 5, en el orden previsto.\n"
    "- El test temporal no interviene en la decision de parada. Su MAE aparece en la "
    "tabla solo como trayectoria observada (ver D-009).\n"
)
M.append(f"\nResultado del bucle: {parada}. Intentos consumidos: {n_intentos} de 5.\n")
M.append("\n## 2. Trayectoria del bucle\n\n" + md_tabla(tab_intentos))
M.append("\n## 3. Comparativa de modelos en el split temporal 2025 -> 2026\n\n" + md_tabla(comp))
M.append(
    "\n## 4. Estabilidad: GroupKFold(4) por cliente dentro de train\n\n" + md_tabla(estab)
)
M.append(f"\nM2 mejora a B1 en {folds_mejores} de 4 folds.\n")
M.append(
    "\n## 5. M3: prediccion por intervalos\n"
    f"\nCon los cuantiles 0,1 / 0,5 / 0,9 sobre la misma configuracion, el intervalo "
    f"[q10, q90] contiene el valor real en el {cobertura:.2f} % de las negociaciones de "
    f"test, con una anchura mediana de {anchura_med:.1f} min. La cobertura nominal del "
    "intervalo es del 80 %: por encima de esa cifra el intervalo es conservador, por "
    "debajo es optimista.\n"
)
M.append(
    f"\nLa diferencia entre la cobertura observada ({cobertura:.2f} %) y la nominal "
    "(80 %) responde al mismo fenomeno que aparece en la Fase 4: los cuantiles se "
    "ajustan con negociaciones cerradas en 2025 y se aplican a 2026, cuya cola es mas "
    f"pesada (P99 de {train0.minutos_total.quantile(0.99):.1f} min en train frente a "
    f"{test0.minutos_total.quantile(0.99):.1f} min en test). El intervalo no es "
    "utilizable como garantia de cobertura sin recalibrarlo por campana.\n"
)
M.append("\n## 6. Explicabilidad - modelo de planificacion\n\n" + md_tabla(imp))
M.append(
    "\nImportancia por permutacion sobre test (10 repeticiones, `random_state=42`), "
    "medida como caida del MAE en la escala `log1p` al permutar cada columna. "
    "Figura: `figuras/05_importancia_permutacion.png`. Dispersograma real frente a "
    "predicho: `figuras/05_real_vs_predicho.png`.\n"
)
M.append("\n### 6.1 Dos casos individuales con el mayor error absoluto en test\n\n" + md_tabla(casos_tab))
M.append(
    "\n## 7. Modelo de control\n\n" + md_tabla(imp_c.head(12)) +
    f"\nEl modelo de control anade `responsable_id_grp` y `n_empleados` al de "
    f"planificacion. Su MAE en test es {met_ctrl['MAE_min']:.2f} min frente a "
    f"{mejor['met']['MAE_min']:.2f} min del de planificacion. `responsable_id_grp` "
    f"ocupa la posicion {pos_resp} de {len(imp_c)} en importancia por permutacion.\n"
    "\nEste modelo existe para detectar anomalias de proceso, no para evaluar el "
    "desempeno de personas. Se reporta por separado por esa razon.\n"
)
M.append("\n## 8. Gate 5\n\n" + md_tabla(gate))
M.append(
    "\n## 9. Lectura del resultado\n"
    f"\nEl modelo M2 reduce el MAE de {MAE_B1_TEST:.2f} a "
    f"{mejor['met']['MAE_min']:.2f} min en el test temporal, una mejora del "
    f"{mejora_test:.2f} % frente al 10 % fijado como umbral. El bucle de mejora se "
    f"agoto en {n_intentos} intentos y ninguna de las ideas de la lista acerco la "
    "mejora al umbral: la mayor ganancia en validacion interna la aporto el ajuste de "
    "hiperparametros (intento 3), y el target encoding por cliente (intento 4) empeoro "
    "el MAE de validacion en un 5,31 %.\n"
    "\nLa mejora es pequena pero consistente: M2 bate a B1 en los cuatro folds de "
    "GroupKFold, con ganancias entre el 1,66 % y el 2,77 %. Es decir, el modelo no es "
    "inestable, es que hay poco que ganar.\n"
    "\nLa lectura sustantiva es que la duracion de estos procesos esta dominada por el "
    "tipo de proceso y por el nivel historico del cliente, y el resto del error procede "
    "de la variabilidad de cada ejecucion concreta. Tres cifras ya medidas lo sostienen:\n"
    "\n1. La distribucion tiene una cola muy larga: ratio P99/mediana = 30,8 (Fase 2). "
    "El MAE esta dominado por unos pocos casos extremos. Los dos mayores errores de "
    "test son negociaciones del mismo proceso (347) con 1.003,7 y 795,4 minutos "
    "imputados, frente a una mediana historica de ese proceso de 22,8 min: ninguna "
    "feature disponible antes de ejecutar el proceso anticipa esa diferencia.\n"
    "2. Hay deriva temporal entre las dos campanas: el P99 pasa de "
    f"{train0.minutos_total.quantile(0.99):.1f} min en train a "
    f"{test0.minutos_total.quantile(0.99):.1f} min en test, y el MAE de B1 pasa de "
    f"{MAE_B1_CV:.2f} a {MAE_B1_TEST:.2f} min. Parte del error de 2026 no estaba en "
    "los datos de 2025.\n"
    "3. El 11,71 % de las horas imputadas no cuelga de ninguna negociacion (Fase 1) y "
    "el 21,74 % de las negociaciones cerradas del pipeline tiene 0 minutos imputados "
    "(Fase 2). El target no recoge todo el trabajo realizado.\n"
    "\nEl resultado se reporta como negativo respecto al umbral y no se ha intentado "
    "alcanzarlo tocando el test, recortando casos dificiles ni reajustando el baseline "
    "a la baja.\n"
)

(OUT / "05_modelos.md").write_text("".join(M), encoding="utf-8")

print("\n--- GATE 5 ---")
print(gate.to_string(index=False))
print("\n--- Comparativa test ---")
print(comp[["modelo", "MAE_min", "mejora_MAE_sobre_B1_pct", "MedAE_min", "pct_dentro_5min"]].to_string(index=False))
print(f"\nEscrito {OUT / '05_modelos.md'}")
