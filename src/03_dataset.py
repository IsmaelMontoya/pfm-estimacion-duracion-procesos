"""
FASE 3 - Construccion del dataset modelable.

Entrada:  output/deals.csv
Salida:   output/dataset_modelo.parquet
          output/03_diccionario_datos.md   (incluye embudo de filtros y Gate 3)

REGLA ANTI-LEAKAGE: toda feature historica se calcula usando exclusivamente
negociaciones cuya `fecha_cierre` es ANTERIOR a la `fecha_creacion` de la fila que se
esta construyendo. Ventana expansiva, nunca el dataset completo. Las filas sin
historial reciben NaN, no la media global.

Uso:  py src/03_dataset.py
"""

from __future__ import annotations

import bisect
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comun import OUT, asegurar_dirs, md_tabla  # noqa: E402

PIPELINE_OBJETIVO = "Modelos de impuestos"

# Se conocen solo DESPUES de ejecutar el proceso. Prohibidas como feature.
PROHIBIDAS = [
    "minutos_max_imputacion", "n_imputaciones", "n_tareas", "n_empleados",
    "fecha_ultima_imputacion", "fecha_cierre", "fecha_primera_imputacion",
    "etapa", "etapa_id", "semantica", "cerrada",
]

FEATURES_PLANIFICACION = [
    "proceso", "ejercicio", "trimestre_fiscal", "mes_creacion",
    "dias_desde_alta_cliente", "n_procesos_previos_cliente",
    "mediana_min_cliente_hist", "mediana_min_proceso_hist",
    "n_deals_misma_campana", "es_primera_vez_cliente_proceso",
]
FEATURES_CONTROL = FEATURES_PLANIFICACION + ["responsable_id_grp", "n_empleados"]
CATEGORICAS = ["proceso", "trimestre_fiscal", "mes_creacion", "responsable_id_grp"]

asegurar_dirs()

deals = pd.read_csv(
    OUT / "deals.csv",
    parse_dates=["fecha_creacion", "fecha_cierre", "fecha_primera_imputacion",
                 "fecha_ultima_imputacion"],
)

# ---------------------------------------------------------------------------
# 1. Embudo de filtros de inclusion
# ---------------------------------------------------------------------------
embudo = []


def paso(nombre: str, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    antes = len(df)
    df2 = df[mask]
    embudo.append({"filtro": nombre, "filas_antes": antes, "filas_caidas": antes - len(df2),
                   "filas_despues": len(df2)})
    return df2


df = deals
df = paso(f"pipeline == '{PIPELINE_OBJETIVO}'", df, df.pipeline == PIPELINE_OBJETIVO)
df = paso("cerrada == 'Y'", df, df.cerrada == "Y")
df = paso("semantica == 'S' (ganada)", df, df.semantica == "S")
df = paso("minutos_total > 0", df, df.minutos_total > 0)
df = paso("proceso no vacio", df, df.proceso.notna() & (df.proceso.astype(str).str.strip() != ""))
df = paso("fecha_cierre no nula", df, df.fecha_cierre.notna())
df = df.copy()

# Filtro 6 (tarea con enlace a un unico deal) se aplica en la Fase 1;
# ver D-002: 5 tareas y 1,98 h descartadas antes de agregar.

# ---------------------------------------------------------------------------
# 2. Variables derivadas
# ---------------------------------------------------------------------------
df["ejercicio"] = pd.to_numeric(df.ejercicio, errors="coerce")
df["mes_creacion"] = df.fecha_creacion.dt.month.astype(str)
df["anio_cierre"] = df.fecha_cierre.dt.year

# trimestre_fiscal: el trimestre natural al que se refiere la declaracion. Un modelo
# del trimestre Q se prepara al final de Q o durante el mes siguiente, por lo que se
# deriva como el trimestre de (fecha_creacion - 1 mes). Ver D-006.
ref = df.fecha_creacion - pd.DateOffset(months=1)
df["trimestre_fiscal"] = ref.dt.quarter.map({1: "1T", 2: "2T", 3: "3T", 4: "4T"})

# Validacion de la regla contra el campo `periodo` del CRM cuando este es trimestral.
val = df[df.periodo.isin(["1T", "2T", "3T", "4T"])]
acuerdo = float((val.trimestre_fiscal == val.periodo).mean() * 100) if len(val) else float("nan")

df["responsable_id_grp"] = df.responsable_id.astype("Int64").astype(str)
frec_resp = df.responsable_id_grp.value_counts()
df.loc[df.responsable_id_grp.map(frec_resp) < 30, "responsable_id_grp"] = "OTROS"

# n_deals_misma_campana: negociaciones de la misma campana (proceso x ejercicio x
# trimestre_fiscal) creadas en la misma fecha o antes. Es informacion disponible en el
# momento de planificar, no depende del resultado de ninguna de ellas.
df["campana"] = (
    df.proceso.astype(str) + "|" + df.ejercicio.astype(str) + "|" + df.trimestre_fiscal
)
df = df.sort_values(["fecha_creacion", "deal_id"]).reset_index(drop=True)
n_camp = np.zeros(len(df), dtype=int)
for _, idx in df.groupby("campana").groups.items():
    pos = np.asarray(idx)
    fechas = df.fecha_creacion.values[pos]
    orden = np.argsort(fechas, kind="stable")
    fechas_ord = fechas[orden]
    n_camp[pos] = np.searchsorted(fechas_ord, fechas, side="right")
df["n_deals_misma_campana"] = n_camp

# ---------------------------------------------------------------------------
# 3. Features historicas — VENTANA EXPANSIVA (regla anti-leakage)
# ---------------------------------------------------------------------------
cierres = df[["fecha_cierre", "cliente_id", "proceso", "minutos_total"]].sort_values(
    ["fecha_cierre", "cliente_id"]
).reset_index(drop=True)

c_fecha = cierres.fecha_cierre.values
c_cli = cierres.cliente_id.values
c_proc = cierres.proceso.values
c_min = cierres.minutos_total.values

hist_cliente: dict = defaultdict(list)
hist_proceso: dict = defaultdict(list)
cnt_cliente: dict = defaultdict(int)
cnt_cli_proc: dict = defaultdict(int)


def mediana_ordenada(lst: list) -> float:
    n = len(lst)
    if n == 0:
        return np.nan
    m = n // 2
    return float(lst[m]) if n % 2 else float((lst[m - 1] + lst[m]) / 2)


n_prev_cli = np.empty(len(df))
med_cli = np.empty(len(df))
med_proc = np.empty(len(df))
primera_vez = np.empty(len(df))

f_crea = df.fecha_creacion.values
d_cli = df.cliente_id.values
d_proc = df.proceso.values

j = 0
for i in range(len(df)):
    t = f_crea[i]
    while j < len(cierres) and c_fecha[j] < t:
        bisect.insort(hist_cliente[c_cli[j]], c_min[j])
        bisect.insort(hist_proceso[c_proc[j]], c_min[j])
        cnt_cliente[c_cli[j]] += 1
        cnt_cli_proc[(c_cli[j], c_proc[j])] += 1
        j += 1
    cli, proc = d_cli[i], d_proc[i]
    n_prev_cli[i] = cnt_cliente[cli]
    med_cli[i] = mediana_ordenada(hist_cliente[cli])
    med_proc[i] = mediana_ordenada(hist_proceso[proc])
    primera_vez[i] = 1.0 if cnt_cli_proc[(cli, proc)] == 0 else 0.0

df["n_procesos_previos_cliente"] = n_prev_cli
df["mediana_min_cliente_hist"] = med_cli
df["mediana_min_proceso_hist"] = med_proc
df["es_primera_vez_cliente_proceso"] = primera_vez

# ---------------------------------------------------------------------------
# 4. Target
# ---------------------------------------------------------------------------
df["y_log"] = np.log1p(df.minutos_total)

COLS_SALIDA = (
    ["deal_id", "cliente_id", "fecha_creacion", "fecha_cierre", "anio_cierre",
     "minutos_total", "y_log"]
    + FEATURES_CONTROL
)
dataset = df[COLS_SALIDA].copy()

# ---------------------------------------------------------------------------
# 5. Comprobaciones del Gate 3
# ---------------------------------------------------------------------------
# Columnas del parquet que NO son features: identificadores, fechas de control del
# split y el target. `fecha_cierre` esta aqui, no como feature: define la particion
# temporal y el corte de la ventana expansiva, y ningun modelo la recibe.
METADATOS = ["deal_id", "cliente_id", "fecha_creacion", "fecha_cierre", "anio_cierre",
             "minutos_total", "y_log"]

prohibidas_presentes = [c for c in PROHIBIDAS if c in FEATURES_PLANIFICACION]
prohibidas_en_parquet = [
    c for c in PROHIBIDAS
    if c in dataset.columns and c not in METADATOS and c != "n_empleados"
]

train = dataset[dataset.anio_cierre <= 2025]

fugas = []
for f in FEATURES_PLANIFICACION:
    s = train[f]
    if f in CATEGORICAS:
        # razon de correlacion (eta): varianza explicada por la categoria
        g = train.groupby(f)["y_log"]
        entre = ((g.transform("mean") - train.y_log.mean()) ** 2).sum()
        total = ((train.y_log - train.y_log.mean()) ** 2).sum()
        r = float(np.sqrt(entre / total)) if total else 0.0
        tipo = "eta"
    else:
        s = pd.to_numeric(s, errors="coerce")
        r = float(abs(s.corr(train.y_log))) if s.notna().sum() > 2 else 0.0
        tipo = "|pearson|"
    fugas.append({"feature": f, "tipo": tipo, "valor": round(r, 4),
                  "supera_0.95": "SI" if r > 0.95 else "no"})
fugas = pd.DataFrame(fugas).sort_values("valor", ascending=False)
n_fugas = int((fugas["supera_0.95"] == "SI").sum())

gate = pd.DataFrame(
    [
        {"criterio": "Filas tras filtros", "umbral": ">= 300", "valor": len(dataset),
         "resultado": "cumple" if len(dataset) >= 300 else "NO cumple"},
        {"criterio": "Features prohibidas en el modelo de planificacion", "umbral": "0",
         "valor": len(prohibidas_presentes),
         "resultado": "cumple" if not prohibidas_presentes else "BLOQUEO"},
        {"criterio": "Features prohibidas entre las columnas de features del parquet",
         "umbral": "0", "valor": len(prohibidas_en_parquet),
         "resultado": "cumple" if not prohibidas_en_parquet else "BLOQUEO"},
        {"criterio": "Features con correlacion > 0.95 con el target en train", "umbral": "0",
         "valor": n_fugas, "resultado": "cumple" if n_fugas == 0 else "revisar"},
    ]
)

if prohibidas_presentes or prohibidas_en_parquet:
    sys.exit(f"BLOQUEO DURO: features prohibidas {prohibidas_presentes or prohibidas_en_parquet}")

dataset.to_parquet(OUT / "dataset_modelo.parquet", index=False)

# ---------------------------------------------------------------------------
# 6. Diccionario de datos
# ---------------------------------------------------------------------------
reparto = (
    dataset.groupby("anio_cierre", as_index=False)
    .agg(n=("deal_id", "count"), mediana_min=("minutos_total", "median"),
         clientes=("cliente_id", "nunique"))
)
reparto["mediana_min"] = reparto.mediana_min.round(1)

desc = {
    "deal_id": ("identificador", "id de la negociacion; no es feature"),
    "cliente_id": ("identificador", "id numerico de la empresa; se usa como grupo en GroupKFold, no es feature"),
    "fecha_creacion": ("fecha", "inicio del proceso; corte de la ventana expansiva"),
    "fecha_cierre": ("fecha", "fin del proceso; define el split temporal, no es feature"),
    "anio_cierre": ("entero", "anio de fecha_cierre; 2025 = train, 2026 = test"),
    "minutos_total": ("numerica", "TARGET en minutos; suma de las imputaciones de la negociacion"),
    "y_log": ("numerica", "TARGET modelado: log1p(minutos_total)"),
    "proceso": ("categorica", "modelo presentado (UF_CRM_1715872169), valor legible del enum"),
    "ejercicio": ("numerica", "ejercicio fiscal declarado (UF_CRM_1741263970530)"),
    "trimestre_fiscal": ("categorica", "derivada: trimestre de (fecha_creacion - 1 mes); ver D-006"),
    "mes_creacion": ("categorica", "mes de fecha_creacion, 1-12"),
    "dias_desde_alta_cliente": ("numerica", "dias entre el alta de la empresa en el CRM y la creacion del deal"),
    "n_procesos_previos_cliente": ("numerica", "HISTORICA: negociaciones del cliente cerradas antes de fecha_creacion"),
    "mediana_min_cliente_hist": ("numerica", "HISTORICA: mediana de minutos del cliente en negociaciones cerradas antes de fecha_creacion; NaN si no hay historial"),
    "mediana_min_proceso_hist": ("numerica", "HISTORICA: idem por proceso"),
    "n_deals_misma_campana": ("numerica", "negociaciones de la misma campana (proceso x ejercicio x trimestre) creadas en la misma fecha o antes"),
    "es_primera_vez_cliente_proceso": ("binaria", "1 si el cliente no habia cerrado antes ese proceso"),
    "responsable_id_grp": ("categorica", "SOLO modelo de control: id del responsable; los que tienen <30 casos se agrupan en OTROS"),
    "n_empleados": ("numerica", "SOLO modelo de control: empleados distintos que imputaron"),
}
dic = pd.DataFrame(
    [{"columna": c, "tipo": desc[c][0], "descripcion": desc[c][1],
      "pct_nulos": round(100 * dataset[c].isna().mean(), 2)} for c in dataset.columns]
)

M = ["# Fase 3 - Diccionario de datos y construccion del dataset\n"]
M.append(f"\nGenerado por `src/03_dataset.py`. Pipeline objetivo: {PIPELINE_OBJETIVO}.\n")
M.append("\n## 1. Embudo de filtros de inclusion\n\n" + md_tabla(pd.DataFrame(embudo)))
M.append(
    "\nEl filtro 6 (tarea con enlace a un unico deal) se aplica en la Fase 1, "
    "antes de agregar el tiempo: 5 tareas y 1,98 h descartadas (D-002).\n"
)
M.append("\n## 2. Reparto por anio de cierre\n\n" + md_tabla(reparto))
M.append("\n## 3. Diccionario de columnas\n\n" + md_tabla(dic))
M.append(
    "\n## 4. Regla anti-leakage\n"
    "\nLas cuatro features marcadas como HISTORICA se calculan recorriendo el dataset "
    "en orden de `fecha_creacion` y acumulando solo negociaciones con "
    "`fecha_cierre < fecha_creacion` de la fila en construccion (ventana expansiva, "
    "comparacion estricta). Las filas sin historial reciben NaN; no se rellenan con la "
    "media global, porque rellenar con un estadistico calculado sobre todo el conjunto "
    "es leakage encubierto. Los modelos de arboles gestionan NaN de forma nativa.\n"
    f"\nFilas sin historial de cliente: "
    f"{int(dataset.mediana_min_cliente_hist.isna().sum()):,} "
    f"({100 * dataset.mediana_min_cliente_hist.isna().mean():.1f} %). "
    f"Sin historial de proceso: {int(dataset.mediana_min_proceso_hist.isna().sum()):,} "
    f"({100 * dataset.mediana_min_proceso_hist.isna().mean():.1f} %).\n"
)
M.append(
    "\n## 5. Features prohibidas\n"
    "\nNo entran en el dataset por conocerse solo despues de ejecutar el proceso: "
    + ", ".join(f"`{c}`" for c in PROHIBIDAS)
    + ". La unica excepcion es `n_empleados`, que se asigna expresamente al modelo "
    "de control y que no se usa en el modelo de planificacion.\n"
)
M.append(
    f"\n## 6. Validacion de la regla de `trimestre_fiscal`\n"
    f"\nSobre las {len(val):,} filas en las que el campo `periodo` del CRM toma un valor "
    f"trimestral (1T-4T), la regla derivada coincide con el valor declarado en el "
    f"{acuerdo:.2f} % de los casos.\n"
)
M.append("\n## 7. Test de leakage: asociacion de cada feature con el target en train\n\n" + md_tabla(fugas))
M.append("\n## 8. Gate 3\n\n" + md_tabla(gate))

(OUT / "03_diccionario_datos.md").write_text("".join(M), encoding="utf-8")

print(f"dataset_modelo.parquet: {len(dataset):,} filas x {dataset.shape[1]} columnas")
print(f"acuerdo trimestre_fiscal vs periodo declarado: {acuerdo:.2f} % sobre {len(val):,} filas")
print("--- GATE 3 ---")
print(gate.to_string(index=False))
print(f"\nEscrito {OUT / '03_diccionario_datos.md'}")
