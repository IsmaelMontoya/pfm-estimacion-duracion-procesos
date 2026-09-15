"""
FASE 1 - Extraccion.

Ejecuta las consultas de `sql/B_extraccion.sql` y escribe:
    output/deals.csv
    output/imputaciones.csv
    output/no_asignado.csv
    output/RESUMEN_extraccion.md   (incluye la evaluacion del Gate 1)

Solo SELECT. Ninguna columna con nombre de empresa, NIF, nombre de persona,
titulo de tarea ni COMMENT_TEXT.

Uso:  py src/01_extraccion.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comun import OUT, ROOT, asegurar_dirs, cargar_entorno, consulta, md_tabla, motor  # noqa: E402

PIPELINE_OBJETIVO = "Modelos de impuestos"

DESDE, HASTA = cargar_entorno()
ENG = motor()
asegurar_dirs()


def cargar_consultas(ruta: Path) -> dict[str, str]:
    """Trocea el .sql por los marcadores `-- @@ <nombre>`."""
    texto = ruta.read_text(encoding="utf-8")
    trozos = re.split(r"^--\s*@@\s*(\w+)\s*$", texto, flags=re.MULTILINE)
    # trozos = [cabecera, nombre1, sql1, nombre2, sql2, ...]
    return {trozos[i]: trozos[i + 1].strip().rstrip(";") for i in range(1, len(trozos), 2)}


Q = cargar_consultas(ROOT / "sql" / "B_extraccion.sql")

print("Extrayendo deals...")
deals = consulta(ENG, Q["deals"], desde=DESDE)
print(f"  {len(deals):,} negociaciones")

print("Extrayendo imputaciones...")
imput = consulta(ENG, Q["imputaciones"], desde=DESDE)
print(f"  {len(imput):,} imputaciones")

print("Extrayendo tiempo no asignado...")
no_asig = consulta(ENG, Q["no_asignado"], desde=DESDE)

cobertura = consulta(ENG, Q["cobertura_horas"], desde=DESDE)
multideal = consulta(ENG, Q["tareas_multideal"])
multideal_h = consulta(ENG, Q["imputaciones_descartadas_multideal"], desde=DESDE)

# --- comprobacion defensiva: ninguna columna prohibida ---------------------
PROHIBIDAS = re.compile(
    r"(nombre|name|titulo|title|comment|nif|cif|email|telefono|phone|direccion|address)",
    re.IGNORECASE,
)
for nombre, df in [("deals", deals), ("imputaciones", imput), ("no_asignado", no_asig)]:
    malas = [c for c in df.columns if PROHIBIDAS.search(c)]
    if malas:
        sys.exit(f"Columna prohibida en {nombre}: {malas}")

deals.to_csv(OUT / "deals.csv", index=False, encoding="utf-8")
imput.to_csv(OUT / "imputaciones.csv", index=False, encoding="utf-8")
no_asig.to_csv(OUT / "no_asignado.csv", index=False, encoding="utf-8")

# ---------------------------------------------------------------------------
# Resumen + Gate 1
# ---------------------------------------------------------------------------
deals["minutos_total"] = pd.to_numeric(deals["minutos_total"], errors="coerce").fillna(0)
deals["cerrada"] = deals["cerrada"].fillna("N")

por_pipeline = (
    deals.assign(
        con_tiempo=(deals.minutos_total > 0).astype(int),
        es_cerrada=(deals.cerrada == "Y").astype(int),
        horas=deals.minutos_total / 60,
    )
    .groupby(["pipeline_id", "pipeline"], as_index=False)
    .agg(
        n_deals=("deal_id", "count"),
        n_cerradas=("es_cerrada", "sum"),
        n_con_tiempo=("con_tiempo", "sum"),
        horas=("horas", "sum"),
    )
    .sort_values("horas", ascending=False)
)
por_pipeline["horas"] = por_pipeline["horas"].round(1)

obj = deals[(deals.pipeline == PIPELINE_OBJETIVO)].copy()
obj_ct = obj[(obj.cerrada == "Y") & (obj.minutos_total > 0)]

por_proceso = (
    obj_ct.groupby("proceso", as_index=False)
    .agg(n=("deal_id", "count"), mediana_min=("minutos_total", "median"))
    .sort_values("n", ascending=False)
)
por_proceso["mediana_min"] = por_proceso["mediana_min"].round(1)

h_con = float(cobertura.loc[cobertura.enlace == "con negociacion", "horas"].sum())
h_sin = float(cobertura.loc[cobertura.enlace == "sin negociacion", "horas"].sum())
pct_sin = 100 * h_sin / (h_con + h_sin) if (h_con + h_sin) else 0.0

n_obj_ct = len(obj_ct)
n_procesos_30 = int((por_proceso.n >= 30).sum())

gate = pd.DataFrame(
    [
        {
            "criterio": f"Filas del pipeline '{PIPELINE_OBJETIVO}' en deals.csv",
            "umbral": "> 0",
            "valor": len(obj),
            "resultado": "cumple" if len(obj) > 0 else "NO cumple",
        },
        {
            "criterio": "Negociaciones cerradas con minutos_total > 0 en el pipeline objetivo",
            "umbral": ">= 500",
            "valor": n_obj_ct,
            "resultado": "cumple" if n_obj_ct >= 500 else ("parcial" if n_obj_ct >= 200 else "NO cumple"),
        },
        {
            "criterio": "Valores distintos de 'proceso' con >= 30 casos",
            "umbral": ">= 3",
            "valor": n_procesos_30,
            "resultado": "cumple" if n_procesos_30 >= 3 else "NO cumple",
        },
        {
            "criterio": "Horas que no cuelgan de ninguna negociacion",
            "umbral": "< 40 %",
            "valor": round(pct_sin, 2),
            "resultado": "cumple" if pct_sin < 40 else "NO cumple",
        },
    ]
)

nulos = (
    deals.isna().mean().mul(100).round(2).rename("pct_nulos").reset_index().rename(columns={"index": "columna"})
)

md = [
    "# Fase 1 - Resumen de extraccion\n",
    f"Ventana de extraccion: desde {DESDE}. Generado por `src/01_extraccion.py`.\n",
    "\n## 1. Campos personalizados localizados\n",
    "\nLocalizados en `b_user_field` (`ENTITY_ID = 'CRM_DEAL'`); los valores de lista se",
    " resuelven contra `b_user_field_enum` y se exporta el texto legible, no el id de enum.\n\n",
    md_tabla(
        pd.DataFrame(
            [
                {"concepto": "proceso (modelo presentado)", "field_id": 158, "nombre_tecnico": "UF_CRM_1715872169", "tipo": "enumeration", "n_valores": 52},
                {"concepto": "ejercicio", "field_id": 526, "nombre_tecnico": "UF_CRM_1741263970530", "tipo": "enumeration", "n_valores": 17},
                {"concepto": "periodo", "field_id": 225, "nombre_tecnico": "UF_CRM_1725611727666", "tipo": "enumeration", "n_valores": 20},
                {"concepto": "tipo_renta (Individual/Conjunta)", "field_id": 586, "nombre_tecnico": "UF_CRM_1743753493010", "tipo": "enumeration", "n_valores": 3},
            ]
        )
    ),
    "\nLos valores UF de negociacion residen en `b_uts_crm_deal`. El puente tarea -> CRM es",
    " `b_utm_tasks_task` con `FIELD_ID = 6` (`UF_CRM_TASK`); la tabla `b_utm_task` que se asumia",
    " inicialmente no existe en este esquema (ver B-001).\n",
    "\n## 2. Filas exportadas\n\n",
    md_tabla(
        pd.DataFrame(
            [
                {"archivo": "deals.csv", "filas": len(deals), "columnas": deals.shape[1]},
                {"archivo": "imputaciones.csv", "filas": len(imput), "columnas": imput.shape[1]},
                {"archivo": "no_asignado.csv", "filas": len(no_asig), "columnas": no_asig.shape[1]},
            ]
        )
    ),
    "\n## 3. Volumen por pipeline\n\n",
    md_tabla(por_pipeline),
    f"\n## 4. Pipeline objetivo: {PIPELINE_OBJETIVO}\n",
    f"\nNegociaciones del pipeline: {len(obj):,}. Cerradas con tiempo imputado: {n_obj_ct:,}.\n\n",
    md_tabla(por_proceso),
    "\n## 5. Cobertura del tiempo\n\n",
    md_tabla(cobertura),
    f"\nHoras sin negociacion asociada: {pct_sin:.2f} % del total imputado desde {DESDE}.\n",
    f"\nTareas enlazadas a mas de una negociacion: {int(multideal.n_tareas_multideal.iloc[0])}. ",
    f"Imputaciones descartadas por esa regla: {int(multideal_h.n_imputaciones.iloc[0])} ",
    f"({float(multideal_h.horas.iloc[0]):.2f} h).\n",
    "\n## 6. Nulos en deals.csv (%)\n\n",
    md_tabla(nulos),
    "\n## 7. Gate 1\n\n",
    md_tabla(gate),
    "\n## 8. Avisos\n\n",
]

avisos = []
if int(deals.etapa.isna().sum()):
    avisos.append(f"- Negociaciones sin nombre de etapa resuelto: {int(deals.etapa.isna().sum()):,}.")
sin_proceso = int((obj_ct.proceso.isna() | (obj_ct.proceso == "")).sum())
avisos.append(f"- Negociaciones cerradas con tiempo del pipeline objetivo sin valor de 'proceso': {sin_proceso:,}.")
sin_ejercicio = int(obj_ct.ejercicio.isna().sum())
avisos.append(f"- Idem sin valor de 'ejercicio': {sin_ejercicio:,}.")
altos = int((obj_ct.minutos_total > 480).sum())
avisos.append(f"- Negociaciones del pipeline objetivo con mas de 480 min (8 h) imputados: {altos:,}.")
cerradas_sin_tiempo = int(((obj.cerrada == "Y") & (obj.minutos_total == 0)).sum())
avisos.append(f"- Negociaciones cerradas del pipeline objetivo con 0 min imputados: {cerradas_sin_tiempo:,}.")
md.append("\n".join(avisos) + "\n")

(OUT / "RESUMEN_extraccion.md").write_text("".join(md), encoding="utf-8")

print("\n--- GATE 1 ---")
print(gate.to_string(index=False))
print(f"\nEscrito {OUT / 'RESUMEN_extraccion.md'}")
