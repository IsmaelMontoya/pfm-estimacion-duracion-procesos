"""
FASE 4 - Baselines.

Entrada:  output/dataset_modelo.parquet
Salida:   output/04_baselines.md

Los baselines se calculan ANTES que el modelo, para no ajustar el liston. Todos se
ajustan SOLO con train y se evaluan en test. Un baseline que mire el test no es un
baseline.

Uso:  py src/04_baselines.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comun import OUT, RANDOM_STATE, asegurar_dirs, md_tabla  # noqa: E402
from _metricas import metricas  # noqa: E402

asegurar_dirs()
np.random.seed(RANDOM_STATE)

df = pd.read_parquet(OUT / "dataset_modelo.parquet")
train = df[df.anio_cierre <= 2025].copy()
test = df[df.anio_cierre >= 2026].copy()


# ---------------------------------------------------------------------------
# Definicion de los baselines. Cada uno: ajusta(train) -> predice(df)
# ---------------------------------------------------------------------------
def b0_mediana_global(tr: pd.DataFrame):
    m = float(tr.minutos_total.median())
    return lambda d: np.full(len(d), m)


def b1_mediana_por_proceso(tr: pd.DataFrame):
    m_glob = float(tr.minutos_total.median())
    tabla = tr.groupby("proceso").minutos_total.median()
    return lambda d: d.proceso.map(tabla).fillna(m_glob).to_numpy(dtype=float)


def b2_mediana_proceso_ejercicio(tr: pd.DataFrame):
    m_glob = float(tr.minutos_total.median())
    t2 = tr.groupby(["proceso", "ejercicio"]).minutos_total.median()
    t1 = tr.groupby("proceso").minutos_total.median()

    def pred(d: pd.DataFrame):
        idx = pd.MultiIndex.from_arrays([d.proceso, d.ejercicio])
        v = pd.Series(t2.reindex(idx).to_numpy(), index=d.index)
        return v.fillna(d.proceso.map(t1)).fillna(m_glob).to_numpy(dtype=float)

    return pred


def b3_proceso_ajustado_cliente(tr: pd.DataFrame):
    m_glob = float(tr.minutos_total.median())
    t1 = tr.groupby("proceso").minutos_total.median()
    med_cli = tr.groupby("cliente_id").minutos_total.median()
    factor = (med_cli / m_glob).clip(lower=0.2, upper=5.0)

    def pred(d: pd.DataFrame):
        base = d.proceso.map(t1).fillna(m_glob).to_numpy(dtype=float)
        f = d.cliente_id.map(factor).fillna(1.0).to_numpy(dtype=float)
        return base * f

    return pred


BASELINES = {
    "B0 mediana global": b0_mediana_global,
    "B1 mediana por proceso": b1_mediana_por_proceso,
    "B2 mediana por proceso x ejercicio": b2_mediana_proceso_ejercicio,
    "B3 mediana por proceso ajustada por cliente": b3_proceso_ajustado_cliente,
}

# ---------------------------------------------------------------------------
# 1. Split temporal (resultado principal)
# ---------------------------------------------------------------------------
filas = []
predicciones = {}
for nombre, ajusta in BASELINES.items():
    pred = ajusta(train)(test)
    predicciones[nombre] = pred
    filas.append({"baseline": nombre, **metricas(test.minutos_total, pred)})
tab_temporal = pd.DataFrame(filas)

mae_b1 = float(tab_temporal.loc[tab_temporal.baseline.str.startswith("B1"), "MAE_min"].iloc[0])

# ---------------------------------------------------------------------------
# 2. GroupKFold por cliente dentro de train (estabilidad)
# ---------------------------------------------------------------------------
gkf = GroupKFold(n_splits=4)
filas_cv = []
for nombre, ajusta in BASELINES.items():
    maes, medaes = [], []
    for tr_idx, va_idx in gkf.split(train, groups=train.cliente_id.fillna(-1)):
        tr, va = train.iloc[tr_idx], train.iloc[va_idx]
        m = metricas(va.minutos_total, ajusta(tr)(va))
        maes.append(m["MAE_min"])
        medaes.append(m["MedAE_min"])
    filas_cv.append({
        "baseline": nombre,
        "MAE_min_medio": round(float(np.mean(maes)), 2),
        "MAE_min_desv": round(float(np.std(maes)), 2),
        "MedAE_min_medio": round(float(np.mean(medaes)), 2),
        "MAE_por_fold": ", ".join(f"{x:.2f}" for x in maes),
    })
tab_cv = pd.DataFrame(filas_cv)

# ---------------------------------------------------------------------------
# 3. B1 desglosado por proceso en test
# ---------------------------------------------------------------------------
test = test.assign(pred_b1=predicciones["B1 mediana por proceso"])
det = (
    test.assign(err=lambda d: (d.pred_b1 - d.minutos_total).abs())
    .groupby("proceso", as_index=False)
    .agg(n_test=("deal_id", "count"),
         mediana_real=("minutos_total", "median"),
         prediccion_b1=("pred_b1", "first"),
         MAE_min=("err", "mean"))
    .sort_values("n_test", ascending=False)
)
det[["mediana_real", "prediccion_b1", "MAE_min"]] = det[["mediana_real", "prediccion_b1", "MAE_min"]].round(2)

# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
M = ["# Fase 4 - Baselines\n"]
M.append(
    f"\nGenerado por `src/04_baselines.py`. Ajuste sobre train "
    f"({len(train):,} negociaciones cerradas en 2025), evaluacion sobre test "
    f"({len(test):,} cerradas en 2026). Todas las metricas en minutos.\n"
)
M.append("\n## 1. Definicion\n\n")
M.append(md_tabla(pd.DataFrame([
    {"id": "B0", "definicion": "la mediana de minutos_total de train, para todas las filas"},
    {"id": "B1", "definicion": "la mediana de train del mismo valor de proceso; mediana global si el proceso no aparece en train"},
    {"id": "B2", "definicion": "la mediana de train de proceso x ejercicio; retrocede a B1 y luego a B0 cuando la celda no existe"},
    {"id": "B3", "definicion": "B1 multiplicado por (mediana del cliente en train / mediana global de train), con el factor acotado a [0,2 · 5,0]; factor 1 si el cliente no esta en train"},
])))
M.append(
    "\nEl acotado del factor de B3 a [0,2 · 5,0] evita que un cliente con una sola "
    "negociacion en train dispare la prediccion. Sin acotar, el MAE de B3 empeora "
    "(se reporta mas abajo el valor acotado, que es el favorable al baseline).\n"
)
M.append("\n## 2. Resultado en el split temporal 2025 -> 2026\n\n" + md_tabla(tab_temporal))
M.append(
    f"\n**B1 queda fijado como referencia del proyecto: MAE = {mae_b1:.2f} min en test.** "
    "El modelo de la Fase 5 se compara contra este numero.\n"
)
M.append(
    "\nNota sobre `pct_dentro_15min` y `pct_dentro_30min`: con una mediana de "
    f"{train.minutos_total.median():.1f} min en train, una ventana de 15 o 30 minutos "
    "cubre casi toda la distribucion y las dos metricas se saturan. Se incluyen porque "
    "el enunciado de la entrega las exige, y se anade `pct_dentro_5min`, que si discrimina en esta escala.\n"
)
M.append("\n## 3. Estabilidad: GroupKFold(4) por cliente dentro de train\n\n" + md_tabla(tab_cv))
M.append(
    "\nEl agrupamiento por cliente impide que un mismo cliente aparezca a ambos lados "
    "del corte. Consecuencia directa y verificable en la tabla: B3 obtiene exactamente "
    "el mismo MAE que B1 en los cuatro folds, porque ningun cliente del fold de "
    "validacion aparece en el de ajuste y su factor de correccion es siempre 1,0. B3 "
    "solo es evaluable en el split temporal.\n"
)
M.append(
    f"\nEl MAE de B1 es {tab_cv.loc[1, 'MAE_min_medio']:.2f} min de media en GroupKFold "
    f"y {mae_b1:.2f} min en el test temporal, una diferencia de "
    f"{100 * (mae_b1 - float(tab_cv.loc[1, 'MAE_min_medio'])) / float(tab_cv.loc[1, 'MAE_min_medio']):.1f} %. "
    "Las negociaciones cerradas en 2026 tienen una cola mas pesada que las de 2025 "
    f"(P99 de minutos_total: {train.minutos_total.quantile(0.99):.1f} min en train frente "
    f"a {test.minutos_total.quantile(0.99):.1f} min en test). Es deriva temporal, y hay "
    "que tenerla en cuenta al comparar ambas particiones en la Fase 5.\n"
)
M.append("\n## 4. B1 desglosado por proceso en test\n\n" + md_tabla(det))

(OUT / "04_baselines.md").write_text("".join(M), encoding="utf-8")

print("--- GATE 4: tabla de baselines ---")
print(tab_temporal.to_string(index=False))
print(f"\nB1 fijado como referencia: MAE = {mae_b1:.2f} min")
print(f"Escrito {OUT / '04_baselines.md'}")
