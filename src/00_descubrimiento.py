"""
FASE 1 (paso previo) - Descubrimiento del esquema real.

Ejecuta las consultas de `sql/A_00_descubrimiento.sql` y escribe el resultado en
`output/00_descubrimiento.md`. Solo SELECT. Sin nombres de cliente ni de empleado.

Uso:  py src/00_descubrimiento.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comun import OUT, asegurar_dirs, cargar_entorno, consulta, md_tabla, motor  # noqa: E402

DESDE, HASTA = cargar_entorno()
ENG = motor()
asegurar_dirs()

partes: list[str] = ["# Fase 1 - Descubrimiento del esquema\n"]
partes.append(f"Ventana de analisis: {DESDE} a {HASTA}\n")


def bloque(titulo: str, sql: str, **params) -> None:
    df = consulta(ENG, sql, **params)
    partes.append(f"\n## {titulo}\n\n" + md_tabla(df))
    print(f"[ok] {titulo}: {len(df)} filas")
    return df


# A0 - tablas esperadas
bloque(
    "A0. Tablas esperadas",
    """
    SELECT TABLE_NAME, TABLE_ROWS
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME IN ('b_crm_deal','b_crm_deal_category','b_crm_status',
                         'b_tasks','b_tasks_elapsed_time','b_utm_tasks_task',
                         'b_user_field','b_user_field_enum','b_user_field_lang',
                         'b_uts_crm_deal','b_crm_company')
    ORDER BY TABLE_NAME
    """,
)

# A1 - pipelines
bloque(
    "A1. Pipelines",
    "SELECT ID AS category_id, NAME AS pipeline, SORT FROM b_crm_deal_category ORDER BY SORT, ID",
)

# A2 - volumen por pipeline y anio
bloque(
    "A2. Negociaciones por pipeline y anio de creacion",
    """
    SELECT d.CATEGORY_ID,
           COALESCE(c.NAME, CONCAT('(cat ', d.CATEGORY_ID, ')')) AS pipeline,
           YEAR(d.DATE_CREATE) AS anio,
           COUNT(*) AS n_deals,
           SUM(d.CLOSED = 'Y') AS n_cerradas
    FROM b_crm_deal d
    LEFT JOIN b_crm_deal_category c ON c.ID = d.CATEGORY_ID
    WHERE d.DATE_CREATE >= :desde
    GROUP BY d.CATEGORY_ID, pipeline, anio
    ORDER BY d.CATEGORY_ID, anio
    """,
    desde=DESDE,
)

# A3 - campos personalizados de deal
bloque(
    "A3. Campos personalizados de CRM_DEAL",
    """
    SELECT f.ID AS field_id, f.FIELD_NAME, f.USER_TYPE_ID AS tipo, f.MULTIPLE,
           l.EDIT_FORM_LABEL AS etiqueta,
           (SELECT COUNT(*) FROM b_user_field_enum e WHERE e.USER_FIELD_ID = f.ID) AS n_valores
    FROM b_user_field f
    LEFT JOIN b_user_field_lang l ON l.USER_FIELD_ID = f.ID AND l.LANGUAGE_ID = 'es'
    WHERE f.ENTITY_ID = 'CRM_DEAL'
    ORDER BY f.ID
    """,
)

# A5 - etapas
bloque(
    "A5. Etapas de negociacion",
    """
    SELECT s.ENTITY_ID, s.STATUS_ID, s.NAME AS etapa, s.SORT, s.SEMANTICS AS semantica
    FROM b_crm_status s
    WHERE s.ENTITY_ID LIKE 'DEAL_STAGE%'
    ORDER BY s.ENTITY_ID, s.SORT
    """,
)

# A6 - puente tarea -> CRM
bloque(
    "A6a. Campos UF_CRM de TASKS_TASK",
    "SELECT f.ID AS field_id, f.FIELD_NAME, f.ENTITY_ID FROM b_user_field f "
    "WHERE f.ENTITY_ID = 'TASKS_TASK' AND f.FIELD_NAME LIKE 'UF_CRM%'",
)

bloque(
    "A6b. Prefijos de enlace en b_utm_tasks_task",
    "SELECT SUBSTRING_INDEX(u.VALUE, '_', 1) AS prefijo, COUNT(*) AS n "
    "FROM b_utm_tasks_task u GROUP BY prefijo ORDER BY n DESC",
)

# A7 - cadena tiempo -> tarea -> deal
bloque(
    "A7. Horas imputadas por pipeline (cadena completa)",
    """
    SELECT d.CATEGORY_ID,
           COALESCE(c.NAME, CONCAT('(cat ', d.CATEGORY_ID, ')')) AS pipeline,
           COUNT(DISTINCT d.ID) AS deals_con_tiempo,
           COUNT(DISTINCT e.TASK_ID) AS tareas,
           COUNT(*) AS imputaciones,
           COUNT(DISTINCT e.USER_ID) AS empleados,
           ROUND(SUM(e.SECONDS)/3600, 1) AS horas
    FROM b_tasks_elapsed_time e
    JOIN b_utm_tasks_task u ON u.VALUE_ID = e.TASK_ID AND u.VALUE LIKE 'D\\_%'
    JOIN b_crm_deal d ON d.ID = CAST(SUBSTRING(u.VALUE, 3) AS UNSIGNED)
    LEFT JOIN b_crm_deal_category c ON c.ID = d.CATEGORY_ID
    WHERE e.SECONDS > 0 AND e.CREATED_DATE >= :desde
    GROUP BY d.CATEGORY_ID, pipeline
    ORDER BY horas DESC
    """,
    desde=DESDE,
)

# A8 - cobertura
bloque(
    "A8. Tiempo con y sin negociacion",
    """
    SELECT CASE WHEN u.VALUE_ID IS NULL THEN 'sin negociacion' ELSE 'con negociacion' END AS enlace,
           COUNT(*) AS imputaciones,
           ROUND(SUM(e.SECONDS)/3600, 1) AS horas
    FROM b_tasks_elapsed_time e
    LEFT JOIN b_utm_tasks_task u ON u.VALUE_ID = e.TASK_ID AND u.VALUE LIKE 'D\\_%'
    WHERE e.SECONDS > 0 AND e.CREATED_DATE >= :desde
    GROUP BY enlace
    """,
    desde=DESDE,
)

# A9 - sesgo de redondeo
bloque(
    "A9. Sesgo de redondeo de las imputaciones",
    """
    SELECT CASE
             WHEN MOD(e.SECONDS, 3600) = 0 THEN '1. multiplo de 60 min'
             WHEN MOD(e.SECONDS, 1800) = 0 THEN '2. multiplo de 30 min'
             WHEN MOD(e.SECONDS, 900)  = 0 THEN '3. multiplo de 15 min'
             WHEN MOD(e.SECONDS, 300)  = 0 THEN '4. multiplo de 5 min'
             ELSE '5. valor no redondo' END AS granularidad,
           COUNT(*) AS n
    FROM b_tasks_elapsed_time e
    WHERE e.SECONDS > 0 AND e.CREATED_DATE >= :desde
    GROUP BY granularidad ORDER BY granularidad
    """,
    desde=DESDE,
)

# A10 - tareas con mas de un deal enlazado
bloque(
    "A10. Tareas con enlace a mas de una negociacion",
    """
    SELECT n_deals_por_tarea, COUNT(*) AS n_tareas
    FROM (
      SELECT u.VALUE_ID, COUNT(DISTINCT u.VALUE) AS n_deals_por_tarea
      FROM b_utm_tasks_task u WHERE u.VALUE LIKE 'D\\_%' GROUP BY u.VALUE_ID
    ) t
    GROUP BY n_deals_por_tarea ORDER BY n_deals_por_tarea
    """,
)

destino = OUT / "00_descubrimiento.md"
destino.write_text("\n".join(partes), encoding="utf-8")
print(f"\nEscrito {destino}")
