# Registro de decisiones

Diario personal de decisiones metodológicas tomadas durante el desarrollo del
proyecto: una entrada por cada decisión no trivial.
Formato obligatorio: decisión, alternativa descartada, motivo, impacto estimado.
Numeración correlativa D-001, D-002...

Regla aplicada en todo el proyecto: si una decisión cambia materialmente el
resultado, no se elige a ciegas — se implementan y reportan ambas ramas.

---

## D-000 · Plantilla (no borrar)

**Decisión:**
**Alternativa descartada:**
**Motivo:**
**Impacto estimado:** alto / medio / bajo
**Fase:**

---

## D-001 · Qué se hace con los archivos del borrador anterior

**Decisión:** se conserva `sql/A_00_descubrimiento.sql` como documentación de las
consultas de descubrimiento y se reescribe su ejecución en `src/00_descubrimiento.py`
(con la corrección de nombre de tabla de B-001). Se elimina
`src/00_exploracion_viabilidad.py`.
**Alternativa descartada:** adaptar `src/00_exploracion_viabilidad.py` a la lógica de
negociaciones.
**Motivo:** ese script clasificaba el tipo de proceso con una lista fija de modelos
tributarios buscada en el texto de las tareas (`MODELOS_TRIBUTARIOS`, línea 190). Se
opta por la etiqueta nativa del CRM (campo *Modelo presentado*, `UF_CRM_1715872169`),
que no requiere heurística de texto. Mantener el script obligaría a justificar en la
memoria una taxonomía inventada que ya no se usa.
**Impacto estimado:** bajo (ningún resultado depende de él).
**Fase:** 1

## D-002 · Tareas enlazadas a más de una negociación

**Decisión:** se descartan por completo las tareas cuyo campo `UF_CRM_TASK` apunta a
más de un deal; su tiempo no se asigna a ninguna negociación.
**Alternativa descartada:** repartir el tiempo entre los deals enlazados, o asignarlo
al de menor `deal_id`.
**Motivo:** es la opción conservadora (no inventa una atribución que el dato no
respalda). El volumen medido es despreciable: 5 tareas sobre 54.474 con enlace a deal
(0,009 %), 3 imputaciones y 1,98 h sobre 30.656,8 h con negociación (0,006 %).
**Impacto estimado:** bajo, medido.
**Fase:** 1

## D-003 · Ventana de extracción de negociaciones

**Decisión:** `deals.csv` incluye toda negociación con `DATE_CREATE >= 2025-01-01`
**o** `CLOSEDATE >= 2025-01-01`.
**Alternativa descartada:** filtrar solo por `DATE_CREATE`.
**Motivo:** filtrar solo por fecha de creación perdería las negociaciones abiertas en
2024 y cerradas dentro de la ventana, que sí tienen tiempo imputado en el período y
son observaciones válidas para el split temporal por fecha de cierre.
**Impacto estimado:** medio (afecta al recuento de filas, no al método).
**Fase:** 1

## D-004 · Columna `dias_desde_alta_cliente` en `deals.csv`

**Decisión:** se exporta la antigüedad del cliente como entero de días
(`DATEDIFF(deal.DATE_CREATE, company.DATE_CREATE)`) en lugar de la fecha de alta.
**Alternativa descartada:** exportar la fecha de alta de la empresa.
**Motivo:** la feature `dias_desde_alta_cliente` de la Fase 3 la necesita; exportar el
entero evita sacar del sistema un atributo de la ficha de empresa. Nulos: 2,66 %.
**Impacto estimado:** bajo.
**Fase:** 1

## D-005 · Qué parte de `output/` se versiona

**Decisión:** `.gitignore` excluye todo `output/` salvo los informes `.md` y las
figuras `.png`.
**Alternativa descartada:** no versionar nada de `output/`.
**Motivo:** el criterio de higiene de trabajo de este proyecto exige un commit por
fase completada con el informe de esa fase incluido, y los informes viven dentro de
`output/`. Excluir el directorio entero haría imposible cumplirlo. Los datos
(`*.csv`, `*.parquet`, `*.pkl`) siguen fuera del control de versiones.
**Impacto estimado:** bajo.
**Fase:** 2

## D-006 · Regla de derivación de `trimestre_fiscal`

**Decisión:** `trimestre_fiscal` = trimestre natural de (`fecha_creacion` − 1 mes).
**Alternativa descartada:** usar el campo `periodo` del CRM tal cual.
**Motivo:** el campo `periodo` existe (`UF_CRM_1725611727666`) pero solo toma valor
trimestral (1T–4T) en 6.138 de las 13.013 filas del dataset (47,2 %); el resto son
valores anuales, mensuales o de pago fraccionado. La regla derivada está definida para
el 100 % de las filas. Contrastada contra el campo declarado en las 6.138 filas en que
este es trimestral, coincide en el 99,63 %.
**Impacto estimado:** bajo (la feature tiene eta = 0,077 con el target en train).
**Fase:** 3

## D-007 · Qué historial alimenta las features de ventana expansiva

**Decisión:** las features históricas (`n_procesos_previos_cliente`,
`mediana_min_cliente_hist`, `mediana_min_proceso_hist`,
`es_primera_vez_cliente_proceso`) se calculan sobre el propio dataset modelable
(pipeline objetivo, cerradas, ganadas, con tiempo).
**Alternativa descartada:** usar como historial todas las negociaciones de todos los
pipelines presentes en `deals.csv`.
**Motivo:** es la definición fijada por la regla anti-leakage del proyecto (ver
metodología) y mantiene la feature interpretable: "mediana de minutos de este cliente en procesos del
mismo tipo de trabajo". Ampliar el historial a otros pipelines mezclaría duraciones de
procesos de naturaleza distinta (contabilidad, expedientes) en la misma mediana.
**Impacto estimado:** medio. Coste medido: 2.242 filas (17,2 %) quedan sin historial de
cliente y 2.253 (17,3 %) sin historial de proceso, y reciben NaN.
**Fase:** 3

## D-008 · `n_deals_misma_campana` como recuento acumulado

**Decisión:** se define como el número de negociaciones de la misma campaña
(`proceso` × `ejercicio` × `trimestre_fiscal`) creadas en la misma fecha o antes que la
fila.
**Alternativa descartada:** el total de negociaciones de la campaña.
**Motivo:** el total de la campaña solo se conoce cuando la campaña ha terminado de
darse de alta; usarlo introduciría información posterior al momento de planificación.
El acumulado es la opción conservadora.
**Impacto estimado:** bajo (|pearson| = 0,031 con el target en train).
**Fase:** 3

## D-009 · Sobre qué partición se decide la parada del bucle de mejora

**Decisión:** el criterio de parada del bucle (mejora ≥ 10 % sobre B1, máximo 5
intentos) se evalúa sobre la validación interna GroupKFold(4) por cliente dentro de
train. El MAE de test se reporta en la tabla de intentos, pero no interviene en la
decisión de parar ni en la elección de la variante.
**Alternativa descartada:** evaluar el bucle directamente sobre el MAE de test, que
sería la lectura ingenua del criterio de parada.
**Motivo:** cinco iteraciones guiadas por el test son cinco decisiones tomadas mirando
el conjunto de evaluación, y la regla fijada de antemano prohíbe tocar el test para
conseguir el umbral. La variante final se elige por MAE de validación interna. Efecto verificable:
la variante elegida (intento 3, MAE de validación 11,26 min) no es la de mejor MAE de
test (intento 5, 15,48 min frente a 15,50 min), lo que confirma que la selección no
miró el test.
**Impacto estimado:** medio (cambia qué variante se reporta como principal).
**Fase:** 5

## D-010 · Categorías no vistas en train

**Decisión:** los valores de una feature categórica presentes en test y ausentes en
train se convierten a NaN, y el modelo los trata como valor ausente.
**Alternativa descartada:** asignarlos a la categoría más frecuente de train.
**Motivo:** asignarlos a la categoría más frecuente inventa una pertenencia que el dato
no respalda. NaN es la opción conservadora y `HistGradientBoostingRegressor` lo gestiona
de forma nativa.
**Impacto estimado:** bajo. El intento 1 del bucle agrupa además en `OTROS` los procesos
con menos de 100 casos en train, lo que reduce el problema en la feature con más
categorías.
**Fase:** 5

## D-011 · Definición de anomalía adoptada

**Decisión:** se adopta el residuo estandarizado en minutos, |z| > 3, con sigma por
proceso estimada sobre los residuos out-of-fold de train. Se reporta además la misma
regla en escala `log1p` como rama complementaria.
**Alternativa descartada:** marcar los casos fuera del intervalo [q10, q90] de M3.
**Motivo:** el criterio fijado es el volumen manejable (por debajo del 5 %). La
definición por intervalo marca el 45,20 % de las negociaciones de test, inutilizable en
la práctica, y arrastra el problema de calibración medido en la Fase 5 (cobertura
observada del 54,80 % frente al 80 % nominal). La definición en minutos marca el 3,86 %.
**Impacto estimado:** alto (define qué se revisa).
**Fase:** 6

## D-012 · Sigma estimada con residuos out-of-fold

**Decisión:** la sigma por proceso se calcula sobre los residuos out-of-fold de train
(GroupKFold por cliente), no sobre los residuos del modelo aplicado a su propio train.
Los procesos con menos de 20 casos en train usan la sigma global.
**Alternativa descartada:** usar los residuos dentro de muestra.
**Motivo:** los residuos dentro de muestra son menores que los reales, la sigma
resultante es más pequeña y la tasa de marcado sube de forma artificial. Es la opción
que menos favorece al proyecto: con una sigma mayor se marcan menos casos y la lista de
anomalías es más difícil de justificar como útil.
**Impacto estimado:** medio.
**Fase:** 6

## D-013 · Rama en escala logarítmica para la infraimputación

**Decisión:** se añade la rama (b), el mismo residuo estandarizado en escala `log1p`, y
se reporta junto a la principal.
**Alternativa descartada:** reportar solo la definición en minutos.
**Motivo:** en minutos el residuo está acotado por abajo en `-prediccion_min`; el valor
más negativo que z alcanza en todo el test es -0,043, de modo que el marcado por defecto
(z < -3) es aritméticamente imposible y la detección de infraimputación que se busca
no existiría. En escala `log1p` el residuo sí es simétrico: marca el 1,10 % de los
casos, de los cuales 1 por defecto.
**Impacto estimado:** medio.
**Fase:** 6

## D-014 · Fuente del PDF de entrega

**Decisión:** generar `Entrega_4_Estimacion_De_La_Duracion_De_Procesos.pdf` con
`mainfont="Georgia"` y `monofont="Consolas"` en lugar de las fuentes DejaVu previstas
inicialmente.
**Alternativa descartada:** instalar las fuentes DejaVu como fuentes de sistema.
**Motivo:** DejaVu Serif/Sans Mono no están instaladas en esta máquina y `xelatex` (vía
`fontspec`) no las localiza. Georgia y Consolas vienen preinstaladas en Windows y cubren
el mismo propósito (serif de lectura + monoespaciada para código y cifras), sin cambiar
el contenido del documento. Verificado con la comprobación 7.3 sobre el texto extraído
del PDF: 0 IPs, 0 coincidencias de credenciales.
**Impacto estimado:** bajo (solo tipografía).
**Fase:** 7
