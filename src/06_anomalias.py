"""
FASE 6 - Anomalias y validacion con experto.

Entrada:  output/predicciones_planificacion.parquet
Salida:   output/06_anomalias.md
          output/validacion_experto.csv   (40 casos, sin la columna de prediccion)
          output/figuras/06_*.png

La anomalia NO es un segundo modelo: es el residuo estandarizado del modelo de
planificacion de la Fase 5.

    residuo    = minutos_reales - minutos_predichos
    sigma_proc = desviacion tipica de los residuos de train, por proceso
    z          = residuo / sigma_proc
    anomalia   = |z| > 3

La sigma se estima con los residuos OUT-OF-FOLD de train (GroupKFold por cliente), no
con residuos dentro de muestra, que la subestimarian.

Uso:  py src/06_anomalias.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comun import FIGURAS, OUT, RANDOM_STATE, asegurar_dirs, md_tabla  # noqa: E402

UMBRAL_Z = 3.0
N_CASOS_VALIDACION = 40

asegurar_dirs()
rng = np.random.default_rng(RANDOM_STATE)

pred = pd.read_parquet(OUT / "predicciones_planificacion.parquet")
pred["residuo"] = pred.minutos_total - pred.prediccion_min

train = pred[pred.particion == "train"].copy()
test = pred[pred.particion == "test"].copy()

# ---------------------------------------------------------------------------
# 1. Sigma por proceso, estimada SOLO con train
# ---------------------------------------------------------------------------
sigma_proc = train.groupby("proceso").residuo.std()
n_proc_train = train.groupby("proceso").residuo.size()
sigma_global = float(train.residuo.std())
# Procesos con menos de 20 casos en train no tienen una sigma fiable: usan la global.
sigma_usada = sigma_proc.where(n_proc_train >= 20, sigma_global)

test["sigma"] = test.proceso.map(sigma_usada).fillna(sigma_global)
test["z"] = test.residuo / test.sigma
test["anomalia_z"] = test.z.abs() > UMBRAL_Z
test["tipo"] = np.where(test.z > UMBRAL_Z, "exceso",
                        np.where(test.z < -UMBRAL_Z, "defecto", "normal"))

tasa_global = float(test.anomalia_z.mean() * 100)
reparto_tipo = (
    test.tipo.value_counts().rename("n").reset_index()
    .assign(pct=lambda d: (100 * d.n / len(test)).round(2))
)

por_proceso = (
    test.groupby("proceso", as_index=False)
    .agg(n_test=("deal_id", "count"),
         n_marcadas=("anomalia_z", "sum"),
         n_exceso=("tipo", lambda s: int((s == "exceso").sum())),
         n_defecto=("tipo", lambda s: int((s == "defecto").sum())),
         sigma_train=("sigma", "first"))
    .assign(pct_marcadas=lambda d: (100 * d.n_marcadas / d.n_test).round(2),
            sigma_train=lambda d: d.sigma_train.round(2))
    .sort_values("n_test", ascending=False)
)

# ---------------------------------------------------------------------------
# 1bis. Rama alternativa: el mismo residuo en escala log1p
# ---------------------------------------------------------------------------
# En minutos, el residuo esta acotado por abajo: no puede bajar de -prediccion_min,
# porque los minutos no son negativos. Con predicciones de pocos minutos y sigmas de
# decenas de minutos, z no puede alcanzar -3 y el marcado por defecto es estructuralmente
# imposible. Se mide y se reporta la cota, y se calcula la misma regla en escala log1p,
# donde el residuo si es simetrico.
z_min_posible = float((-test.prediccion_min / test.sigma).max())

for d in (train, test):
    d["res_log"] = np.log1p(d.minutos_total) - np.log1p(d.prediccion_min.clip(lower=0))

sigma_log_proc = train.groupby("proceso").res_log.std()
n_log = train.groupby("proceso").res_log.size()
sigma_log_global = float(train.res_log.std())
sigma_log_usada = sigma_log_proc.where(n_log >= 20, sigma_log_global)

test["z_log"] = test.res_log / test.proceso.map(sigma_log_usada).fillna(sigma_log_global)
test["anomalia_log"] = test.z_log.abs() > UMBRAL_Z
test["tipo_log"] = np.where(test.z_log > UMBRAL_Z, "exceso",
                            np.where(test.z_log < -UMBRAL_Z, "defecto", "normal"))
tasa_log = float(test.anomalia_log.mean() * 100)
reparto_log = (
    test.tipo_log.value_counts().rename("n").reset_index()
    .assign(pct=lambda d: (100 * d.n / len(test)).round(2))
)

# ---------------------------------------------------------------------------
# 2. Definicion alternativa: fuera del intervalo [q10, q90] de M3
# ---------------------------------------------------------------------------
test["fuera_intervalo"] = (test.minutos_total < test.q10_min) | (test.minutos_total > test.q90_min)
tasa_intervalo = float(test.fuera_intervalo.mean() * 100)

comparacion = pd.DataFrame([
    {"definicion": f"(a) residuo en minutos, |z| > {UMBRAL_Z:.0f}",
     "n_marcadas": int(test.anomalia_z.sum()),
     "pct_marcadas": round(tasa_global, 2),
     "n_exceso": int((test.tipo == "exceso").sum()),
     "n_defecto": int((test.tipo == "defecto").sum()),
     "manejable_bajo_5pct": "si" if tasa_global < 5 else "no"},
    {"definicion": f"(b) residuo en escala log1p, |z| > {UMBRAL_Z:.0f}",
     "n_marcadas": int(test.anomalia_log.sum()),
     "pct_marcadas": round(tasa_log, 2),
     "n_exceso": int((test.tipo_log == "exceso").sum()),
     "n_defecto": int((test.tipo_log == "defecto").sum()),
     "manejable_bajo_5pct": "si" if tasa_log < 5 else "no"},
    {"definicion": "(c) fuera del intervalo [q10, q90] de M3",
     "n_marcadas": int(test.fuera_intervalo.sum()),
     "pct_marcadas": round(tasa_intervalo, 2),
     "n_exceso": int((test.minutos_total > test.q90_min).sum()),
     "n_defecto": int((test.minutos_total < test.q10_min).sum()),
     "manejable_bajo_5pct": "si" if tasa_intervalo < 5 else "no"},
])
solape = int((test.anomalia_z & test.fuera_intervalo).sum())

# ---------------------------------------------------------------------------
# 3. Archivo de validacion ciega con experto
# ---------------------------------------------------------------------------
anomalas = test[test.anomalia_z]
normales = test[~test.anomalia_z]
n_lado = N_CASOS_VALIDACION // 2
n_anom = min(n_lado, len(anomalas))
n_norm = N_CASOS_VALIDACION - n_anom

muestra = pd.concat([
    anomalas.sample(n=n_anom, random_state=RANDOM_STATE),
    normales.sample(n=n_norm, random_state=RANDOM_STATE),
])
muestra = muestra.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True)

validacion = muestra[["deal_id", "proceso", "ejercicio", "minutos_total"]].copy()
validacion["minutos_total"] = validacion.minutos_total.round(1)
validacion["veredicto_experto"] = ""
validacion.to_csv(OUT / "validacion_experto.csv", index=False, encoding="utf-8")

# La clave se guarda aparte para poder calcular el acuerdo cuando el experto devuelva
# el archivo. No se entrega junto con el CSV de validacion.
clave = muestra[["deal_id", "anomalia_z", "tipo", "z", "prediccion_min"]].copy()
clave["z"] = clave.z.round(2)
clave["prediccion_min"] = clave.prediccion_min.round(1)
clave.to_csv(OUT / "validacion_experto_clave.csv", index=False, encoding="utf-8")

# ---------------------------------------------------------------------------
# 4. Si el experto ya ha devuelto el archivo, calcular el acuerdo
# ---------------------------------------------------------------------------
ruta_relleno = OUT / "validacion_experto_relleno.csv"
seccion_acuerdo = (
    "\nEl archivo `output/validacion_experto.csv` esta generado y pendiente de que el "
    "experto lo rellene. Cuando devuelva el archivo relleno como "
    "`output/validacion_experto_relleno.csv` y se vuelva a ejecutar este script, esta "
    "seccion se completa con el acuerdo, la precision y el recall frente al criterio "
    "experto. No se rellena con datos inventados.\n"
)
if ruta_relleno.exists():
    rel = pd.read_csv(ruta_relleno)
    m = rel.merge(clave, on="deal_id", how="inner")
    m = m[m.veredicto_experto.isin(["razonable", "anomalo"])]
    if len(m):
        exp_anom = m.veredicto_experto == "anomalo"
        mod_anom = m.anomalia_z
        vp = int((exp_anom & mod_anom).sum())
        fp = int((~exp_anom & mod_anom).sum())
        fn = int((exp_anom & ~mod_anom).sum())
        vn = int((~exp_anom & ~mod_anom).sum())
        acuerdo = 100 * (vp + vn) / len(m)
        precision = 100 * vp / (vp + fp) if (vp + fp) else float("nan")
        recall = 100 * vp / (vp + fn) if (vp + fn) else float("nan")
        seccion_acuerdo = (
            f"\nCasos con veredicto utilizable: {len(m)} de {len(rel)} "
            f"(se descartan los marcados `no_se`).\n\n"
            + md_tabla(pd.DataFrame([
                {"metrica": "acuerdo", "valor_pct": round(acuerdo, 2)},
                {"metrica": "precision del marcado", "valor_pct": round(precision, 2)},
                {"metrica": "recall del marcado", "valor_pct": round(recall, 2)},
            ]))
            + "\n" + md_tabla(pd.DataFrame([
                {"": "modelo marca", "experto: anomalo": vp, "experto: razonable": fp},
                {"": "modelo no marca", "experto: anomalo": fn, "experto: razonable": vn},
            ]))
        )

# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
plt.rcParams.update({"figure.dpi": 120, "font.size": 9})

fig, ax = plt.subplots(figsize=(7, 3.8))
ax.hist(test.z.clip(-10, 10), bins=80, color="#4c72b0")
for x in (-UMBRAL_Z, UMBRAL_Z):
    ax.axvline(x, color="#c44e52", lw=1)
ax.set_xlabel("residuo estandarizado z (recortado a [-10, 10])")
ax.set_ylabel("negociaciones de test")
ax.set_title(f"Distribucion de z y umbral |z| > {UMBRAL_Z:.0f}")
fig.tight_layout()
fig.savefig(FIGURAS / "06_distribucion_z.png")
plt.close(fig)

top = por_proceso[por_proceso.n_test >= 50].sort_values("pct_marcadas", ascending=False).head(15)
fig, ax = plt.subplots(figsize=(7.5, 4))
ax.bar(top.proceso.astype(str), top.pct_marcadas, color="#4c72b0")
ax.set_ylabel("% de negociaciones marcadas")
ax.set_title("Tasa de marcado por proceso (procesos con >= 50 casos en test)")
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
fig.tight_layout()
fig.savefig(FIGURAS / "06_tasa_por_proceso.png")
plt.close(fig)

# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
M = ["# Fase 6 - Anomalias y validacion con experto\n"]
M.append(
    f"\nGenerado por `src/06_anomalias.py`. Se aplica sobre las {len(test):,} "
    "negociaciones de test (cerradas en 2026), que es el escenario de uso: control al "
    "cerrar la campana.\n"
)
M.append(
    "\n## 1. Definicion\n"
    "\nLa anomalia no es un segundo modelo. Es el residuo del modelo de planificacion "
    "de la Fase 5, estandarizado por la dispersion propia de cada proceso:\n\n"
    "```\n"
    "residuo    = minutos_reales - minutos_predichos\n"
    "sigma_proc = desviacion tipica de los residuos de train, por proceso\n"
    "z          = residuo / sigma_proc\n"
    f"anomalia   = |z| > {UMBRAL_Z:.0f}\n"
    "```\n"
    "\nLa sigma se estima con los residuos out-of-fold de train (GroupKFold por "
    "cliente). Usar residuos dentro de muestra la subestimaria y elevaria la tasa de "
    "marcado de forma artificial. Los procesos con menos de 20 casos en train usan la "
    f"sigma global ({sigma_global:.2f} min) en lugar de la suya.\n"
)
M.append(
    f"\n## 2. Tasa de marcado\n"
    f"\nTasa global: **{tasa_global:.2f} %** ({int(test.anomalia_z.sum())} de "
    f"{len(test):,} negociaciones de test).\n\n"
)
M.append(md_tabla(reparto_tipo))
M.append(
    "\nLas marcadas por exceso (z > 3) son negociaciones que han consumido mucho mas "
    "tiempo del estimado. Las marcadas por defecto (z < -3) apuntarian a "
    "infraimputacion: trabajo hecho que no se ha registrado.\n"
    f"\nNo hay ninguna marcada por defecto, y no es un hallazgo sobre los datos sino "
    "una consecuencia aritmetica de la definicion. Los minutos no son negativos, asi "
    "que el residuo no puede bajar de `-prediccion_min`; con predicciones de pocos "
    "minutos y sigmas de decenas de minutos, el valor mas negativo que z puede tomar en "
    f"todo el conjunto de test es {z_min_posible:.3f}, muy lejos de -3. **En escala de "
    "minutos, esta definicion solo puede detectar exceso.**\n"
    "\nPor eso se calcula tambien la misma regla sobre el residuo en escala `log1p`, "
    "donde el residuo si es simetrico (seccion 4, rama b).\n"
)
M.append("\n## 3. Tasa de marcado por proceso\n\n" + md_tabla(por_proceso))
M.append("\n## 4. Comparacion de las tres definiciones\n\n" + md_tabla(comparacion))
M.append("\nReparto de la rama (b), en escala log1p:\n\n" + md_tabla(reparto_log))
M.append(
    f"\nLas ramas (a) y (c) coinciden en {solape} negociaciones. El criterio de "
    "eleccion declarado es el volumen manejable: por encima de un 5 % de "
    "casos marcados la deteccion es inutil en la practica.\n"
    f"\n- (a) marca el {tasa_global:.2f} %, todo por exceso.\n"
    f"- (b) marca el {tasa_log:.2f} %, y es la unica capaz de senalar infraimputacion.\n"
    f"- (c) marca el {tasa_intervalo:.2f} %: queda descartada por volumen, y ademas "
    "hereda el problema de calibracion medido en la Fase 5 (cobertura observada del "
    "54,80 % frente al 80 % nominal).\n"
    "\nSe adopta **(a)** como definicion principal, por ser la que fija el alcance del "
    "proyecto y la que produce una lista revisable de casos con sobrecoste de tiempo. "
    "**(b)** se reporta como complemento porque cubre el unico caso que (a) no puede "
    "ver por construccion. Las dos usan el mismo modelo y el mismo residuo: cambian "
    "solo de escala.\n"
)
M.append(
    "\n## 5. Validacion ciega con experto\n"
    f"\nSe ha generado `output/validacion_experto.csv` con {len(validacion)} casos: "
    f"{n_anom} marcados como anomalos y {n_norm} normales, mezclados con "
    "`random_state=42` y sin la columna de prediccion ni la de z. Columnas: `deal_id`, "
    "`proceso`, `ejercicio`, `minutos_total`, `veredicto_experto`.\n"
    "\nValores admitidos en `veredicto_experto`: `razonable`, `anomalo`, `no_se`.\n"
    "\nLa clave (que caso estaba marcado y con que z) queda en "
    "`output/validacion_experto_clave.csv`, que no se entrega al experto.\n"
    "\n### 5.1 Resultado del contraste\n"
    + seccion_acuerdo
)
M.append(
    "\n## 6. Gate 6\n\n"
    + md_tabla(pd.DataFrame([
        {"criterio": "Informe con la tasa de marcado", "valor": f"{tasa_global:.2f} %",
         "resultado": "cumple"},
        {"criterio": "Archivo de validacion generado",
         "valor": f"{len(validacion)} casos", "resultado": "cumple"},
        {"criterio": "Volumen de marcado por debajo del 5 %",
         "valor": f"{tasa_global:.2f} %",
         "resultado": "cumple" if tasa_global < 5 else "NO cumple"},
        {"criterio": "Contraste con el experto",
         "valor": "pendiente" if not ruta_relleno.exists() else "calculado",
         "resultado": "pendiente de que el usuario devuelva el archivo relleno"
         if not ruta_relleno.exists() else "cumple"},
    ]))
)
M.append(
    "\n## 7. Figuras\n\n"
    "- `figuras/06_distribucion_z.png`\n"
    "- `figuras/06_tasa_por_proceso.png`\n"
)

(OUT / "06_anomalias.md").write_text("".join(M), encoding="utf-8")

print("--- GATE 6 ---")
print(f"tasa de marcado global: {tasa_global:.2f} % ({int(test.anomalia_z.sum())} de {len(test):,})")
print(reparto_tipo.to_string(index=False))
print(f"definicion alternativa (fuera de [q10,q90]): {tasa_intervalo:.2f} %")
print(f"validacion_experto.csv: {len(validacion)} casos ({n_anom} marcados / {n_norm} normales)")
print(f"Escrito {OUT / '06_anomalias.md'}")
