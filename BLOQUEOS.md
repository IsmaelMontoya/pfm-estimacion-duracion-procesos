# Registro de bloqueos

Diario personal de bloqueos: una entrada por cada punto en el que el dato no
existe, el gate no se cumple o la realidad contradice lo previsto en la
planificación.

Regla aplicada en todo el proyecto: no se inventa el dato, no se aproxima sin
decirlo, no se pasa de fase fingiendo que el gate se cumplió.

Numeracion correlativa B-001, B-002...

---

## B-000 · Plantilla (no borrar)

**Esperado:**
**Encontrado:**
**Probado:**
**Accion tomada:**
**Fase:**
**Estado:** abierto / resuelto / asumido como limitacion

---

## B-001 · La tabla puente `b_utm_task` no existe

**Esperado:** tabla `b_utm_task` con el enlace tarea -> CRM, según el modelo de datos
previsto inicialmente (Entrega 3).
**Encontrado:** no existe. El esquema tiene `b_utm_tasks_task` (130.134 filas), con las
mismas columnas (`ID`, `VALUE_ID`, `FIELD_ID`, `VALUE`, ...). El campo `UF_CRM_TASK` de
`TASKS_TASK` es `FIELD_ID = 6`.
**Probado:** listado de `information_schema.TABLES` con patrones `b_utm%`, `%tasks%`,
`b_uts%`. Reparto de prefijos en `b_utm_tasks_task`: D 54.479, CO 47.054, C 1.489,
L 499, resto 553.
**Accion tomada:** se usa `b_utm_tasks_task` con `FIELD_ID = 6` en todas las consultas.
Los valores UF de negociación se leen de `b_uts_crm_deal`, confirmada por
`information_schema` (32.914 filas).
**Fase:** 1
**Estado:** resuelto

## B-002 · El motor no admite CTE ni funciones de ventana

**Esperado:** MariaDB / MySQL con soporte de `WITH` y `OVER ()`.
**Encontrado:** `SELECT VERSION()` devuelve 5.7. `WITH` produce error 1064.
**Probado:** primera versión de `sql/B_extraccion.sql` escrita con CTE; falla en la
primera consulta.
**Accion tomada:** todas las consultas reescritas con tablas derivadas. Sin cambio de
semántica: los recuentos de `deals.csv` (30.836 filas) e `imputaciones.csv` (66.690
filas) coinciden con los agregados de descubrimiento.
**Fase:** 1
**Estado:** resuelto

## B-003 · Extracción a repositorio independiente

**Esperado:** el PFM vive en un repositorio propio, sin historial heredado.
**Encontrado:** el material vivía dentro de un repositorio de material de curso. La
corrección del tutor exige repositorio dedicado.
**Probado:** nada todavía en el momento de registrar este bloqueo. Es una acción de
cara al exterior (creación de repositorio remoto, purga de historial y rotación de
credenciales) que conviene planificar con cuidado antes de ejecutarla.
**Accion tomada:**

1. Repositorio nuevo creado en local: `pfm-estimacion-duracion-procesos`, commit limpio, sin
   historial heredado. Ya incluye las entregas 1-5. **Hecho.**
2. Contenido copiado sin `output/` ni `.env`. **Hecho.**
3. Las versiones actuales de las entregas 2 y 3 del repositorio de curso ya no
   contienen la IP ni el nombre de BD reales — sustituidos por marcadores genéricos,
   con nota de trazabilidad del pivote. **Hecho.**
4. Credenciales de acceso a la base de datos: **rotadas antes de retomar esta
   entrega.** Verificado que el `.env` actual conecta correctamente con las
   credenciales rotadas. **Hecho.**
5. Purga del *historial* de git del repositorio de curso (`git filter-repo` con
   reemplazo de texto, excluyendo binarios explícitamente) y eliminación de un
   archivo ajeno de 124 MB que bloqueaba el push (asignatura de Deep Learning, sin
   relación con el PFM): **ejecutada, verificada exhaustivamente y subida.**
   Verificación: las cadenas reales no aparecen en ningún commit; los archivos
   binarios afectados (PDFs antiguos, el PDF de la Entrega 4, el PNG del mockup)
   conservan el mismo hash de blob que el original — cero bytes tocados. Copia de
   seguridad completa conservada antes de la purga, por si hiciera falta
   restaurar. **Hecho.**
6. **Pendiente:** conectar `pfm-estimacion-duracion-procesos` a un remoto de GitHub
   y empujarlo. Solo local por ahora.

**Fase:** 7
**Estado:** parcialmente resuelto — el riesgo de seguridad está cerrado y la purga de
historial hecha; queda la publicación del repositorio nuevo

## B-004 · El modelo no alcanza el umbral de mejora del Gate 5

**Esperado:** MAE de M2 al menos un 10 % mejor que el de B1 en el test temporal.
**Encontrado:** M2 obtiene 15,50 min frente a los 16,37 min de B1, una mejora del
5,31 %. El criterio secundario sí se cumple: M2 mejora a B1 en 4 de 4 folds de
GroupKFold, con ganancias entre 1,66 % y 2,77 %.
**Probado:** el bucle de mejora agotó los 5 intentos previstos (agrupar procesos poco
frecuentes, features de carga de campaña, ajuste de hiperparámetros, target encoding
por cliente ajustado por fold, recorte de cola al P99 solo en train). La mejor variante
en validación interna fue el ajuste de hiperparámetros (MAE de validación 11,26 min
frente a los 11,53 min de B1, un 2,28 %). El target encoding por cliente empeoró la
validación en un 5,31 %.
**Accion tomada:** se para el bucle según el criterio declarado antes de abrirlo y se
documenta el resultado negativo en `output/05_modelos.md`, sección 9, con las tres
cifras que lo explican (ratio P99/mediana = 30,8; deriva del P99 de 143,7 a 189,9 min
entre train y test; 11,71 % de horas sin negociación y 21,74 % de negociaciones
cerradas con 0 minutos). No se ha tocado el test, ni filtrado casos difíciles, ni
reajustado el baseline. El proyecto continúa a la Fase 6 con este modelo.
**Fase:** 5
**Estado:** asumido como limitación

## B-005 · No hay cadena de generación de PDF en esta máquina

**Esperado:** generar `Entrega_4_Estimacion_De_La_Duracion_De_Procesos.pdf` desde el
markdown, según el procedimiento previsto.
**Encontrado:** no están instalados `pandoc`, `xelatex`, `pdflatex`, `wkhtmltopdf`,
`libreoffice`/`soffice` ni el módulo `weasyprint`.
**Probado:** `Get-Command` sobre los seis ejecutables e `import weasyprint`; los siete
fallan.
**Accion tomada:** no se bloquea el proyecto. El markdown queda terminado en
`docs/entregas/04_estimacion_duracion_procesos.md` y es la fuente de verdad. No se ha
sustituido `pandoc` por otro conversor improvisado, porque produciría un documento con
otro formato y la convención de nombres adoptada para las entregas pide que el PDF se
genere desde el markdown con ese procedimiento.

**Actualización:** instalados `pandoc` (winget, `JohnMacFarlane.Pandoc`) y `MiKTeX`
(winget, `MiKTeX.MiKTeX`). Al generar el PDF con las fuentes DejaVu previstas
inicialmente, `xelatex` no las encuentra instaladas en el sistema (D-014): se
sustituyen por `mainfont="Georgia"` y `monofont="Consolas"`, ambas preinstaladas en
Windows. PDF generado: `Entrega_4_Estimacion_De_La_Duracion_De_Procesos.pdf`
(15 páginas). Texto extraído y pasado por la comprobación de seguridad: 0 IPs, 0
coincidencias de credenciales.
**Fase:** 7
**Estado:** resuelto

## B-006 · Validación ciega con experto sin respuesta

**Esperado:** contraste del marcado de anomalías contra el criterio de un experto.
**Encontrado:** el archivo `output/validacion_experto.csv` está generado con los 40
casos (20 marcados y 20 normales, mezclados con `random_state=42`, sin la columna de
predicción ni la de z), pero los veredictos están vacíos.
**Probado:** nada más. Depende de una persona, no de los datos.
**Accion tomada:** el experto devolvió `output/validacion_experto_relleno.csv` con los
40 veredictos. Acuerdo del 52,6 % sobre los 38 casos usables (2 `no_se` descartados),
precisión 42,1 %, recall 53,3 %. Los 18 desacuerdos se concentran en dos causas
medidas: 11 casos donde el modelo marca exceso y el experto lo considera razonable por
complejidad del caso (sin feature disponible que la capture antes de ejecutar el
proceso), y 7 casos muy cortos donde el experto marca infraimputación y la definición
en minutos no puede marcar por defecto por construcción (confirma D-013). Detalle
completo en `output/06_anomalias.md`, sección 5.1.
**Fase:** 6
**Estado:** resuelto
