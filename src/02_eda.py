"""
FASE 2 - Calidad y EDA.

Entrada:  output/deals.csv, output/imputaciones.csv, output/no_asignado.csv
Salida:   output/02_informe_calidad.md  +  output/figuras/*.png

Mide, no opina. Cada tabla del informe procede de un calculo de este script.

Uso:  py src/02_eda.py
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

from _comun import FIGURAS, OUT, asegurar_dirs, md_tabla  # noqa: E402

PIPELINE_OBJETIVO = "Modelos de impuestos"
asegurar_dirs()

deals = pd.read_csv(OUT / "deals.csv", parse_dates=["fecha_creacion", "fecha_cierre",
                                                    "fecha_primera_imputacion",
                                                    "fecha_ultima_imputacion"])
imput = pd.read_csv(OUT / "imputaciones.csv", parse_dates=["fecha"])
no_asig = pd.read_csv(OUT / "no_asignado.csv")

obj = deals[deals.pipeline == PIPELINE_OBJETIVO].copy()
obj_ct = obj[(obj.cerrada == "Y") & (obj.minutos_total > 0)].copy()

P = []  # partes del informe
P.append("# Fase 2 - Informe de calidad y analisis exploratorio\n")
P.append(
    f"\nGenerado por `src/02_eda.py`. Pipeline objetivo: {PIPELINE_OBJETIVO}. "
    f"Todas las cifras salen de `output/deals.csv` ({len(deals):,} filas) y "
    f"`output/imputaciones.csv` ({len(imput):,} filas).\n"
)

# ---------------------------------------------------------------------------
# 1. Cobertura
# ---------------------------------------------------------------------------
deals["anio_creacion"] = deals.fecha_creacion.dt.year
deals["con_tiempo"] = deals.minutos_total > 0

cob_pipeline = (
    deals.groupby("pipeline", as_index=False)
    .agg(n_deals=("deal_id", "count"),
         n_cerradas=("cerrada", lambda s: int((s == "Y").sum())),
         n_con_tiempo=("con_tiempo", "sum"),
         horas=("minutos_total", lambda s: s.sum() / 60))
    .assign(pct_con_tiempo=lambda d: (100 * d.n_con_tiempo / d.n_deals).round(1),
            horas=lambda d: d.horas.round(1))
    .sort_values("horas", ascending=False)
)

cob_anio = (
    deals[deals.pipeline == PIPELINE_OBJETIVO]
    .groupby("anio_creacion", as_index=False)
    .agg(n_deals=("deal_id", "count"),
         n_cerradas=("cerrada", lambda s: int((s == "Y").sum())),
         n_con_tiempo=("con_tiempo", "sum"))
    .assign(pct_con_tiempo=lambda d: (100 * d.n_con_tiempo / d.n_deals).round(1))
)

P.append("\n## 1. Cobertura: negociaciones con y sin tiempo imputado\n")
P.append("\n### 1.1 Por pipeline\n\n" + md_tabla(cob_pipeline))
P.append(f"\n### 1.2 Pipeline objetivo, por anio de creacion\n\n" + md_tabla(cob_anio))

horas_con = deals.minutos_total.sum() / 60
horas_sin = no_asig.horas.sum()
pct_sin_neg = 100 * horas_sin / (horas_con + horas_sin)
P.append(
    f"\nHoras imputadas que cuelgan de una negociacion: {horas_con:,.1f}. "
    f"Horas sin negociacion: {horas_sin:,.1f} ({pct_sin_neg:.2f} % del total).\n"
)

# ---------------------------------------------------------------------------
# 2. Sesgo de redondeo del target
# ---------------------------------------------------------------------------
def granularidad(seg: int) -> str:
    if seg % 3600 == 0:
        return "1. multiplo de 60 min"
    if seg % 1800 == 0:
        return "2. multiplo de 30 min"
    if seg % 900 == 0:
        return "3. multiplo de 15 min"
    if seg % 300 == 0:
        return "4. multiplo de 5 min"
    return "5. valor no redondo"


imput["granularidad"] = imput.segundos.map(granularidad)
red = (
    imput.groupby("granularidad", as_index=False)
    .agg(n=("imputacion_id", "count"))
    .assign(pct=lambda d: (100 * d.n / d.n.sum()).round(2))
    .sort_values("granularidad")
)
pct_no_redondo = float(red.loc[red.granularidad == "5. valor no redondo", "pct"].sum())

P.append("\n## 2. Sesgo de redondeo del target\n")
P.append(
    "\nReparto de las imputaciones individuales segun si su duracion en segundos es "
    "multiplo exacto de 60, 30, 15 o 5 minutos. Marca el suelo del error alcanzable: "
    "si la mayoria de las imputaciones fueran redondas, el target seria casi ordinal.\n\n"
)
P.append(md_tabla(red))
P.append(f"\nImputaciones con valor no redondo: {pct_no_redondo:.2f} %.\n")

# ---------------------------------------------------------------------------
# 3. Distribucion de minutos_total por proceso
# ---------------------------------------------------------------------------
def resumen_dist(g: pd.Series) -> pd.Series:
    return pd.Series(
        {
            "n": int(g.size),
            "mediana": round(float(g.median()), 1),
            "p25": round(float(g.quantile(0.25)), 1),
            "p75": round(float(g.quantile(0.75)), 1),
            "p90": round(float(g.quantile(0.90)), 1),
            "p99": round(float(g.quantile(0.99)), 1),
            "max": round(float(g.max()), 1),
        }
    )


dist = (
    obj_ct.groupby("proceso")["minutos_total"]
    .apply(resumen_dist)
    .unstack()
    .reset_index()
    .sort_values("n", ascending=False)
)
dist["ratio_p99_mediana"] = (dist.p99 / dist.mediana).round(1)
dist_global = resumen_dist(obj_ct.minutos_total)
ratio_global = round(float(dist_global.p99 / dist_global.mediana), 1)

P.append("\n## 3. Distribucion de `minutos_total` por proceso\n")
P.append(
    "\nSolo negociaciones del pipeline objetivo cerradas y con tiempo imputado "
    f"({len(obj_ct):,} filas).\n\n"
)
P.append(md_tabla(dist))
P.append(
    f"\nAgregado del pipeline: n = {int(dist_global['n']):,}, mediana = "
    f"{dist_global['mediana']} min, P99 = {dist_global['p99']} min, "
    f"maximo = {dist_global['max']} min, ratio P99/mediana = {ratio_global}.\n"
)

# ---------------------------------------------------------------------------
# 4. Censura
# ---------------------------------------------------------------------------
cens = (
    obj.assign(semantica=obj.semantica.fillna("(en curso)"))
    .groupby(["cerrada", "semantica"], as_index=False)
    .agg(n=("deal_id", "count"),
         n_con_tiempo=("minutos_total", lambda s: int((s > 0).sum())))
    .assign(pct=lambda d: (100 * d.n / d.n.sum()).round(2))
)
P.append("\n## 4. Censura: reparto por estado de la negociacion\n\n" + md_tabla(cens))

n_ganadas_ct = int(((obj.cerrada == "Y") & (obj.semantica == "S") & (obj.minutos_total > 0)).sum())
n_perdidas = int((obj.semantica == "F").sum())
P.append(
    f"\nNegociaciones que sobreviven a los filtros de la Fase 3 (cerrada, ganada, "
    f"con tiempo): {n_ganadas_ct:,} de {len(obj):,} ({100 * n_ganadas_ct / len(obj):.1f} %). "
    f"Perdidas excluidas: {n_perdidas:,}.\n"
)

# ---------------------------------------------------------------------------
# 5. Estacionalidad
# ---------------------------------------------------------------------------
cerr = obj[obj.fecha_cierre.notna() & (obj.cerrada == "Y")].copy()
cerr["trimestre"] = cerr.fecha_cierre.dt.to_period("Q").astype(str)
est = cerr.pivot_table(index="trimestre", columns="proceso", values="deal_id",
                       aggfunc="count", fill_value=0)
top_proc = obj_ct.proceso.value_counts().head(8).index.tolist()
est_top = est.reindex(columns=[c for c in top_proc if c in est.columns]).reset_index()
P.append("\n## 5. Estacionalidad: negociaciones cerradas por trimestre natural\n")
P.append("\nOcho procesos mas frecuentes.\n\n" + md_tabla(est_top))

# ---------------------------------------------------------------------------
# 6. Concentracion por empleado
# ---------------------------------------------------------------------------
imp_obj = imput.merge(obj_ct[["deal_id"]], on="deal_id", how="inner")
emp = (
    imp_obj.groupby("user_id", as_index=False)
    .agg(n_negociaciones=("deal_id", "nunique"),
         horas=("segundos", lambda s: round(s.sum() / 3600, 1)))
    .sort_values("n_negociaciones", ascending=False)
)
emp["pct_negociaciones"] = (100 * emp.n_negociaciones / len(obj_ct)).round(2)
n_emp_pocos = int((emp.n_negociaciones < 30).sum())
P.append("\n## 6. Concentracion por empleado\n")
P.append(
    f"\nEmpleados que han imputado en el pipeline objetivo: {len(emp)}. "
    f"Con menos de 30 negociaciones: {n_emp_pocos}.\n\n"
)
P.append(md_tabla(emp))

# ---------------------------------------------------------------------------
# 7. Multi-empleado
# ---------------------------------------------------------------------------
pct_multi = 100 * (obj_ct.n_empleados > 1).mean()
rep_emp = (
    obj_ct.n_empleados.value_counts().sort_index().rename("n_negociaciones").reset_index()
    .rename(columns={"index": "n_empleados"})
)
P.append("\n## 7. Negociaciones con mas de un empleado imputando\n\n" + md_tabla(rep_emp))
P.append(f"\nPorcentaje con mas de un empleado: {pct_multi:.2f} %.\n")

# ---------------------------------------------------------------------------
# 8. Desfase temporal
# ---------------------------------------------------------------------------
obj_ct["dias_vida"] = (obj_ct.fecha_cierre - obj_ct.fecha_creacion).dt.days
obj_ct["dias_imputacion"] = (obj_ct.fecha_ultima_imputacion - obj_ct.fecha_primera_imputacion).dt.days
desf = pd.DataFrame(
    [
        {"medida": "dias entre creacion y cierre", **resumen_dist(obj_ct.dias_vida.dropna()).to_dict()},
        {"medida": "dias entre primera y ultima imputacion", **resumen_dist(obj_ct.dias_imputacion.dropna()).to_dict()},
    ]
)
P.append("\n## 8. Desfase temporal (dias)\n\n" + md_tabla(desf))

# ---------------------------------------------------------------------------
# 9. Coherencia
# ---------------------------------------------------------------------------
imp_ventana = imput.merge(
    obj[["deal_id", "fecha_creacion", "fecha_cierre"]], on="deal_id", how="inner"
)
fuera = imp_ventana[
    (imp_ventana.fecha < imp_ventana.fecha_creacion)
    | (imp_ventana.fecha_cierre.notna() & (imp_ventana.fecha > imp_ventana.fecha_cierre))
]
coher = pd.DataFrame(
    [
        {"comprobacion": "cerradas con minutos_total = 0",
         "n": int(((obj.cerrada == "Y") & (obj.minutos_total == 0)).sum()),
         "sobre": len(obj)},
        {"comprobacion": "duracion superior a 8 h (480 min)",
         "n": int((obj_ct.minutos_total > 480).sum()), "sobre": len(obj_ct)},
        {"comprobacion": "duracion inferior a 1 min",
         "n": int((obj_ct.minutos_total < 1).sum()), "sobre": len(obj_ct)},
        {"comprobacion": "imputaciones fuera de la ventana [creacion, cierre] del deal",
         "n": len(fuera), "sobre": len(imp_ventana)},
        {"comprobacion": "negociaciones sin cliente asignado",
         "n": int(obj.cliente_id.isna().sum()), "sobre": len(obj)},
    ]
)
coher["pct"] = (100 * coher.n / coher.sobre).round(2)
P.append("\n## 9. Coherencia\n\n" + md_tabla(coher))

# ---------------------------------------------------------------------------
# 10. Nulos
# ---------------------------------------------------------------------------
nul = (
    pd.DataFrame({
        "columna": deals.columns,
        "pct_nulos_deals": deals.isna().mean().mul(100).round(2).values,
    })
)
nul_obj = obj_ct.isna().mean().mul(100).round(2)
nul["pct_nulos_pipeline_objetivo"] = nul.columna.map(nul_obj).values
P.append("\n## 10. Nulos por columna (%)\n\n" + md_tabla(nul))

# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
plt.rcParams.update({"figure.dpi": 120, "font.size": 9})

fig, ax = plt.subplots(figsize=(7, 4))
ax.hist(np.log1p(obj_ct.minutos_total), bins=60, color="#4c72b0")
ax.set_xlabel("log1p(minutos_total)")
ax.set_ylabel("negociaciones")
ax.set_title("Distribucion del target transformado")
fig.tight_layout()
fig.savefig(FIGURAS / "01_hist_log1p_minutos.png")
plt.close(fig)

top12 = obj_ct.proceso.value_counts().head(12).index.tolist()
sub = obj_ct[obj_ct.proceso.isin(top12)]
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.boxplot([sub.loc[sub.proceso == p, "minutos_total"].values for p in top12],
           tick_labels=top12, showfliers=False)
ax.set_ylabel("minutos_total")
ax.set_title("Duracion por proceso (12 mas frecuentes, sin outliers dibujados)")
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
fig.tight_layout()
fig.savefig(FIGURAS / "02_boxplot_por_proceso.png")
plt.close(fig)

serie = cerr.groupby(cerr.fecha_cierre.dt.to_period("M")).size()
fig, ax = plt.subplots(figsize=(8, 3.5))
ax.plot(serie.index.astype(str), serie.values, marker="o", color="#4c72b0")
ax.set_ylabel("negociaciones cerradas")
ax.set_title("Negociaciones cerradas por mes (pipeline objetivo)")
plt.setp(ax.get_xticklabels(), rotation=90)
fig.tight_layout()
fig.savefig(FIGURAS / "03_serie_cerradas_mes.png")
plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 3.5))
ax.bar(red.granularidad, red.pct, color="#4c72b0")
ax.set_ylabel("% de imputaciones")
ax.set_title("Sesgo de redondeo de las imputaciones")
plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
fig.tight_layout()
fig.savefig(FIGURAS / "04_sesgo_redondeo.png")
plt.close(fig)

# ---------------------------------------------------------------------------
# Gate 2
# ---------------------------------------------------------------------------
max_n_proceso = int(dist.n.max())
gate = pd.DataFrame(
    [
        {"criterio": "Imputaciones no redondas", "umbral": "> 10 %",
         "valor": round(pct_no_redondo, 2),
         "resultado": "cumple" if pct_no_redondo > 10 else "NO cumple"},
        {"criterio": "Ratio P99 / mediana (agregado del pipeline)", "umbral": "se reporta",
         "valor": ratio_global,
         "resultado": "reportado; > 10 confirma log1p + MAE" if ratio_global > 10 else "reportado"},
        {"criterio": "Al menos un proceso con >= 100 casos cerrados con tiempo",
         "umbral": ">= 100", "valor": max_n_proceso,
         "resultado": "cumple" if max_n_proceso >= 100 else "NO cumple"},
    ]
)
P.append("\n## 11. Gate 2\n\n" + md_tabla(gate))
P.append(
    "\n## 12. Figuras\n\n"
    "- `figuras/01_hist_log1p_minutos.png`\n"
    "- `figuras/02_boxplot_por_proceso.png`\n"
    "- `figuras/03_serie_cerradas_mes.png`\n"
    "- `figuras/04_sesgo_redondeo.png`\n"
)

(OUT / "02_informe_calidad.md").write_text("".join(P), encoding="utf-8")

print("--- GATE 2 ---")
print(gate.to_string(index=False))
print(f"\nEscrito {OUT / '02_informe_calidad.md'}")
