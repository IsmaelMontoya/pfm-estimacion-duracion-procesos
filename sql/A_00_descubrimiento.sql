-- =============================================================================
-- PFM · FASE 0-A · DESCUBRIMIENTO
-- =============================================================================
-- Objetivo: confirmar la estructura real antes de medir nada.
-- Salidas pequeñas: se pueden pegar enteras en el chat.
-- Solo SELECT. Nada de nombres de cliente en los resultados.
--
-- Motor: MySQL/MariaDB (Bitrix).
-- Si algún nombre de tabla no existe, ejecuta A0 para localizar el equivalente.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- A0. Salvavidas: ¿existen las tablas que asumo?
-- -----------------------------------------------------------------------------
SELECT TABLE_NAME, TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'b_crm_deal', 'b_crm_deal_category', 'b_crm_status',
      'b_tasks', 'b_tasks_elapsed_time',
      'b_utm_task', 'b_user_field', 'b_user_field_enum', 'b_user_field_lang'
  )
ORDER BY TABLE_NAME;


-- -----------------------------------------------------------------------------
-- A1. Pipelines (categorías de negociación)
-- -----------------------------------------------------------------------------
-- Nota: el embudo "General" es CATEGORY_ID = 0 y NO aparece en esta tabla.
SELECT ID AS category_id, NAME AS pipeline, SORT
FROM b_crm_deal_category
ORDER BY SORT, ID;


-- -----------------------------------------------------------------------------
-- A2. Volumen de negociaciones por pipeline y año
-- -----------------------------------------------------------------------------
SELECT
    d.CATEGORY_ID,
    COALESCE(c.NAME, CONCAT('(cat ', d.CATEGORY_ID, ')')) AS pipeline,
    YEAR(d.DATE_CREATE)                    AS anio,
    COUNT(*)                               AS n_deals,
    SUM(d.CLOSED = 'Y')                    AS n_cerradas,
    ROUND(100 * SUM(d.CLOSED = 'Y') / COUNT(*), 1) AS pct_cerradas
FROM b_crm_deal d
LEFT JOIN b_crm_deal_category c ON c.ID = d.CATEGORY_ID
WHERE d.DATE_CREATE >= '2025-01-01'
GROUP BY d.CATEGORY_ID, pipeline, anio
ORDER BY d.CATEGORY_ID, anio;


-- -----------------------------------------------------------------------------
-- A3. Campos personalizados de negociación  <-- aquí debe salir "modelo presentado"
-- -----------------------------------------------------------------------------
SELECT
    f.ID                AS field_id,
    f.FIELD_NAME,
    f.USER_TYPE_ID      AS tipo,
    f.MULTIPLE          AS multiple,
    l.EDIT_FORM_LABEL   AS etiqueta,
    (SELECT COUNT(*) FROM b_user_field_enum e WHERE e.USER_FIELD_ID = f.ID) AS n_valores_lista
FROM b_user_field f
LEFT JOIN b_user_field_lang l
       ON l.USER_FIELD_ID = f.ID AND l.LANGUAGE_ID = 'es'
WHERE f.ENTITY_ID = 'CRM_DEAL'
ORDER BY f.ID;


-- -----------------------------------------------------------------------------
-- A4. Valores de las listas desplegables de esos campos
-- -----------------------------------------------------------------------------
-- Filtra por los field_id que en A3 te parezcan "modelo presentado" y "tipo de renta".
-- Si son pocos campos, déjalo sin filtro.
SELECT
    f.FIELD_NAME,
    l.EDIT_FORM_LABEL AS etiqueta,
    e.ID              AS enum_id,
    e.VALUE           AS valor
FROM b_user_field f
LEFT JOIN b_user_field_lang l
       ON l.USER_FIELD_ID = f.ID AND l.LANGUAGE_ID = 'es'
JOIN b_user_field_enum e ON e.USER_FIELD_ID = f.ID
WHERE f.ENTITY_ID = 'CRM_DEAL'
  -- AND f.ID IN ( /* rellenar con los field_id relevantes de A3 */ )
ORDER BY f.ID, e.SORT, e.ID;


-- -----------------------------------------------------------------------------
-- A5. Etapas por pipeline (para saber qué significa "terminado")
-- -----------------------------------------------------------------------------
SELECT
    s.ENTITY_ID,
    s.STATUS_ID,
    s.NAME       AS etapa,
    s.SORT,
    s.SEMANTICS  AS semantica   -- S = ganada, F = perdida, NULL = en curso
FROM b_crm_status s
WHERE s.ENTITY_ID LIKE 'DEAL_STAGE%'
ORDER BY s.ENTITY_ID, s.SORT;


-- -----------------------------------------------------------------------------
-- A6. Puente tarea -> negociación (campo UF_CRM_TASK)
-- -----------------------------------------------------------------------------
SELECT f.ID AS field_id, f.FIELD_NAME, f.ENTITY_ID
FROM b_user_field f
WHERE f.ENTITY_ID = 'TASKS_TASK'
  AND f.FIELD_NAME LIKE 'UF_CRM%';

-- Cómo se guardan los enlaces (D_ = deal, CO_ = company, C_ = contact)
SELECT
    SUBSTRING_INDEX(u.VALUE, '_', 1) AS prefijo,
    COUNT(*)                          AS n
FROM b_utm_task u
GROUP BY prefijo
ORDER BY n DESC;


-- -----------------------------------------------------------------------------
-- A7. LA CONSULTA CLAVE: ¿la cadena tiempo -> tarea -> negociación funciona?
-- -----------------------------------------------------------------------------
-- Si esto devuelve horas repartidas por pipeline, el proyecto es viable.
SELECT
    d.CATEGORY_ID,
    COALESCE(c.NAME, CONCAT('(cat ', d.CATEGORY_ID, ')')) AS pipeline,
    COUNT(DISTINCT d.ID)                  AS deals_con_tiempo,
    COUNT(DISTINCT e.TASK_ID)             AS tareas,
    COUNT(*)                              AS imputaciones,
    COUNT(DISTINCT e.USER_ID)             AS empleados,
    ROUND(SUM(e.SECONDS) / 3600, 1)       AS horas_totales,
    ROUND(SUM(e.SECONDS) / 60 / COUNT(DISTINCT d.ID), 1) AS min_medios_por_deal
FROM b_tasks_elapsed_time e
JOIN b_utm_task u
      ON u.VALUE_ID = e.TASK_ID
     AND u.VALUE LIKE 'D\_%'
JOIN b_crm_deal d
      ON d.ID = CAST(SUBSTRING(u.VALUE, 3) AS UNSIGNED)
LEFT JOIN b_crm_deal_category c ON c.ID = d.CATEGORY_ID
WHERE e.SECONDS > 0
  AND e.CREATED_DATE >= '2025-01-01'
GROUP BY d.CATEGORY_ID, pipeline
ORDER BY horas_totales DESC;


-- -----------------------------------------------------------------------------
-- A8. Cobertura: ¿cuánto tiempo NO pasa por ninguna negociación?
-- -----------------------------------------------------------------------------
SELECT
    CASE WHEN u.VALUE_ID IS NULL THEN 'sin negociacion' ELSE 'con negociacion' END AS enlace,
    COUNT(*)                        AS imputaciones,
    ROUND(SUM(e.SECONDS) / 3600, 1) AS horas,
    ROUND(100 * SUM(e.SECONDS) / SUM(SUM(e.SECONDS)) OVER (), 1) AS pct_horas
FROM b_tasks_elapsed_time e
LEFT JOIN b_utm_task u
       ON u.VALUE_ID = e.TASK_ID
      AND u.VALUE LIKE 'D\_%'
WHERE e.SECONDS > 0
  AND e.CREATED_DATE >= '2025-01-01'
GROUP BY enlace;


-- -----------------------------------------------------------------------------
-- A9. Sesgo de redondeo del target (tiempo autodeclarado)
-- -----------------------------------------------------------------------------
SELECT
    CASE
        WHEN MOD(e.SECONDS, 3600) = 0 THEN '1. multiplo de 60 min'
        WHEN MOD(e.SECONDS, 1800) = 0 THEN '2. multiplo de 30 min'
        WHEN MOD(e.SECONDS, 900)  = 0 THEN '3. multiplo de 15 min'
        WHEN MOD(e.SECONDS, 300)  = 0 THEN '4. multiplo de 5 min'
        ELSE                               '5. valor no redondo'
    END AS granularidad,
    COUNT(*) AS n,
    ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM b_tasks_elapsed_time e
WHERE e.SECONDS > 0
  AND e.CREATED_DATE >= '2025-01-01'
GROUP BY granularidad
ORDER BY granularidad;
