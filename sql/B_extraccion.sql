-- =============================================================================
-- PFM · FASE 1 · EXTRACCION
-- =============================================================================
-- Solo SELECT. Ninguna columna con nombre de empresa, NIF, nombre de persona,
-- titulo de tarea ni COMMENT_TEXT. Clientes y empleados solo por ID numerico.
--
-- Motor: MySQL 5.7. No admite CTE (`WITH`) ni funciones de ventana; todas las
-- agregaciones intermedias van como tablas derivadas (ver B-002 en BLOQUEOS.md).
--
-- Este archivo es la UNICA fuente de las consultas: `src/01_extraccion.py` lo lee
-- y ejecuta cada bloque delimitado por el marcador `-- @@ <nombre>`.
--
-- Campos personalizados localizados en la fase de descubrimiento
-- (`src/00_descubrimiento.py` -> `output/00_descubrimiento.md`):
--   Modelo presentado   -> UF_CRM_1715872169     (field_id 158, enumeration, 52 valores)
--   Ejercicio           -> UF_CRM_1741263970530  (field_id 526, enumeration, 17 valores)
--   Periodo             -> UF_CRM_1725611727666  (field_id 225, enumeration, 20 valores)
--   Individual/Conjunta -> UF_CRM_1743753493010  (field_id 586, enumeration,  3 valores)
-- Los valores UF de negociacion viven en `b_uts_crm_deal`.
-- El puente tarea -> CRM es `b_utm_tasks_task` (NO `b_utm_task`), FIELD_ID = 6.
-- =============================================================================


-- @@ deals
-- Una fila por negociacion de cualquier pipeline creada o cerrada desde :desde.
-- Incluye las negociaciones SIN tiempo imputado, con contadores a 0.
SELECT d.ID                                            AS deal_id,
       d.CATEGORY_ID                                   AS pipeline_id,
       COALESCE(cat.NAME, CONCAT('(cat ', d.CATEGORY_ID, ')')) AS pipeline,
       em.VALUE                                        AS proceso,
       ee.VALUE                                        AS ejercicio,
       ep.VALUE                                        AS periodo,
       er.VALUE                                        AS tipo_renta,
       d.COMPANY_ID                                    AS cliente_id,
       d.ASSIGNED_BY_ID                                AS responsable_id,
       d.STAGE_ID                                      AS etapa_id,
       st.NAME                                         AS etapa,
       st.SEMANTICS                                    AS semantica,
       d.CLOSED                                        AS cerrada,
       DATE(d.DATE_CREATE)                             AS fecha_creacion,
       DATE(d.CLOSEDATE)                               AS fecha_cierre,
       DATEDIFF(d.DATE_CREATE, co.DATE_CREATE)         AS dias_desde_alta_cliente,
       COALESCE(a.n_tareas, 0)                         AS n_tareas,
       COALESCE(a.n_imputaciones, 0)                   AS n_imputaciones,
       COALESCE(a.n_empleados, 0)                      AS n_empleados,
       COALESCE(a.minutos_total, 0)                    AS minutos_total,
       COALESCE(a.minutos_max_imputacion, 0)           AS minutos_max_imputacion,
       a.fecha_primera_imputacion                      AS fecha_primera_imputacion,
       a.fecha_ultima_imputacion                       AS fecha_ultima_imputacion
FROM b_crm_deal d
LEFT JOIN b_crm_deal_category cat ON cat.ID = d.CATEGORY_ID
LEFT JOIN b_crm_status st
       ON st.STATUS_ID = d.STAGE_ID
      AND st.ENTITY_ID = IF(d.CATEGORY_ID = 0, 'DEAL_STAGE',
                            CONCAT('DEAL_STAGE_', d.CATEGORY_ID))
LEFT JOIN b_uts_crm_deal uf ON uf.VALUE_ID = d.ID
LEFT JOIN b_user_field_enum em ON em.ID = uf.UF_CRM_1715872169
LEFT JOIN b_user_field_enum ee ON ee.ID = uf.UF_CRM_1741263970530
LEFT JOIN b_user_field_enum ep ON ep.ID = uf.UF_CRM_1725611727666
LEFT JOIN b_user_field_enum er ON er.ID = uf.UF_CRM_1743753493010
LEFT JOIN b_crm_company co ON co.ID = d.COMPANY_ID
LEFT JOIN (
    SELECT l.deal_id                              AS deal_id,
           COUNT(DISTINCT e.TASK_ID)              AS n_tareas,
           COUNT(*)                               AS n_imputaciones,
           COUNT(DISTINCT e.USER_ID)              AS n_empleados,
           ROUND(SUM(e.SECONDS) / 60, 2)          AS minutos_total,
           ROUND(MAX(e.SECONDS) / 60, 2)          AS minutos_max_imputacion,
           DATE(MIN(e.CREATED_DATE))              AS fecha_primera_imputacion,
           DATE(MAX(e.CREATED_DATE))              AS fecha_ultima_imputacion
    FROM b_tasks_elapsed_time e
    JOIN (
        SELECT u.VALUE_ID                              AS task_id,
               CAST(SUBSTRING(u.VALUE, 3) AS UNSIGNED) AS deal_id
        FROM b_utm_tasks_task u
        WHERE u.FIELD_ID = 6 AND u.VALUE LIKE 'D\_%'
        GROUP BY u.VALUE_ID, deal_id
    ) l ON l.task_id = e.TASK_ID
    JOIN (
        SELECT u2.VALUE_ID AS task_id
        FROM b_utm_tasks_task u2
        WHERE u2.FIELD_ID = 6 AND u2.VALUE LIKE 'D\_%'
        GROUP BY u2.VALUE_ID
        HAVING COUNT(DISTINCT u2.VALUE) = 1
    ) t ON t.task_id = e.TASK_ID
    WHERE e.SECONDS > 0 AND e.CREATED_DATE >= :desde
    GROUP BY l.deal_id
) a ON a.deal_id = d.ID
WHERE d.DATE_CREATE >= :desde OR d.CLOSEDATE >= :desde;


-- @@ imputaciones
-- Una fila por imputacion con negociacion asociada. Sin COMMENT_TEXT.
SELECT e.ID                 AS imputacion_id,
       l.deal_id            AS deal_id,
       e.TASK_ID            AS task_id,
       e.USER_ID            AS user_id,
       e.SECONDS            AS segundos,
       DATE(e.CREATED_DATE) AS fecha
FROM b_tasks_elapsed_time e
JOIN (
    SELECT u.VALUE_ID                              AS task_id,
           CAST(SUBSTRING(u.VALUE, 3) AS UNSIGNED) AS deal_id
    FROM b_utm_tasks_task u
    WHERE u.FIELD_ID = 6 AND u.VALUE LIKE 'D\_%'
    GROUP BY u.VALUE_ID, deal_id
) l ON l.task_id = e.TASK_ID
JOIN (
    SELECT u2.VALUE_ID AS task_id
    FROM b_utm_tasks_task u2
    WHERE u2.FIELD_ID = 6 AND u2.VALUE LIKE 'D\_%'
    GROUP BY u2.VALUE_ID
    HAVING COUNT(DISTINCT u2.VALUE) = 1
) t ON t.task_id = e.TASK_ID
WHERE e.SECONDS > 0 AND e.CREATED_DATE >= :desde;


-- @@ no_asignado
-- Agregado mensual del tiempo que NO cuelga de ninguna negociacion. Sin IDs.
SELECT DATE_FORMAT(e.CREATED_DATE, '%Y-%m')  AS anio_mes,
       COUNT(*)                              AS n_imputaciones,
       ROUND(SUM(e.SECONDS) / 3600, 2)       AS horas
FROM b_tasks_elapsed_time e
LEFT JOIN (
    SELECT DISTINCT u.VALUE_ID AS task_id
    FROM b_utm_tasks_task u
    WHERE u.FIELD_ID = 6 AND u.VALUE LIKE 'D\_%'
) l ON l.task_id = e.TASK_ID
WHERE e.SECONDS > 0
  AND e.CREATED_DATE >= :desde
  AND l.task_id IS NULL
GROUP BY anio_mes
ORDER BY anio_mes;


-- @@ cobertura_horas
-- Reparto global de horas con y sin negociacion (para el gate 1).
SELECT CASE WHEN l.task_id IS NULL THEN 'sin negociacion' ELSE 'con negociacion' END AS enlace,
       COUNT(*)                        AS n_imputaciones,
       ROUND(SUM(e.SECONDS) / 3600, 2) AS horas
FROM b_tasks_elapsed_time e
LEFT JOIN (
    SELECT DISTINCT u.VALUE_ID AS task_id
    FROM b_utm_tasks_task u
    WHERE u.FIELD_ID = 6 AND u.VALUE LIKE 'D\_%'
) l ON l.task_id = e.TASK_ID
WHERE e.SECONDS > 0
  AND e.CREATED_DATE >= :desde
GROUP BY enlace;


-- @@ tareas_multideal
-- Cuantas tareas enlazan con mas de una negociacion (se descartan; ver DECISIONES).
SELECT COUNT(*) AS n_tareas_multideal
FROM (
    SELECT u.VALUE_ID
    FROM b_utm_tasks_task u
    WHERE u.FIELD_ID = 6 AND u.VALUE LIKE 'D\_%'
    GROUP BY u.VALUE_ID
    HAVING COUNT(DISTINCT u.VALUE) > 1
) t;


-- @@ imputaciones_descartadas_multideal
-- Volumen de tiempo perdido por descartar las tareas multi-deal.
SELECT COUNT(*) AS n_imputaciones, ROUND(COALESCE(SUM(e.SECONDS), 0) / 3600, 2) AS horas
FROM b_tasks_elapsed_time e
JOIN (
    SELECT u.VALUE_ID AS task_id
    FROM b_utm_tasks_task u
    WHERE u.FIELD_ID = 6 AND u.VALUE LIKE 'D\_%'
    GROUP BY u.VALUE_ID
    HAVING COUNT(DISTINCT u.VALUE) > 1
) m ON m.task_id = e.TASK_ID
WHERE e.SECONDS > 0 AND e.CREATED_DATE >= :desde;
