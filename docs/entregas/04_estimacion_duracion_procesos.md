---
title: "Estimación de la duración de procesos en una asesoría"
subtitle: "Entrega 4 — Diseño del análisis y estrategia de modelado"
lang: es
---

# Respuesta al feedback de las entregas 2 y 3

| Observación del tutor | Qué se ha cambiado | Dónde verlo |
|---|---|---|
| Abarcaba predicción, anomalías y segmentación a la vez | Una sola línea: estimación de duración. La anomalía es el residuo del mismo modelo, no un modelo aparte | § 1 Problema; § 8 Riesgos |
| 19 meses no permiten predecir 2027 | Se abandona la extrapolación temporal. Regresión transversal: una negociación ejecutada es una observación | § 1 Problema; § 6 Estrategia de selección |
| Muy pocos meses por cliente | La unidad pasa de cliente × mes a negociación. 13.013 observaciones sobre 1.036 clientes | § 4 Datos de entrada |
| Afirmar acceso garantizado y calidad excelente sin explorar | Fase de calidad ejecutada antes de escribir la memoria, con cifras. El 21,74 % de las negociaciones cerradas del pipeline tiene 0 minutos imputados y el 11,71 % de las horas no cuelga de ninguna negociación | § 2 Análisis de datos |
| No demostraba mejorar un análisis sencillo | Cuatro baselines calculados antes que el modelo. B1 (mediana por proceso) fijado como referencia: MAE 16,37 min. El modelo mejora un 5,31 %, por debajo del 10 % que se había fijado como umbral, y así se reporta | § 3 Tipos de modelo; § 7 Validación |
| Sin plan contra el leakage temporal | Split temporal por campaña (cierres de 2025 frente a cierres de 2026) y GroupKFold(4) por cliente. Features históricas con ventana expansiva estricta | § 7 Validación |
| `pct_rentabilidad` rellenado con 0 e imputación de costes por medias | Métrica eliminada del alcance. No se usa facturación ni costes en ninguna parte del proyecto | § 1 Problema |
| IPs y nombres de base de datos en el repositorio | Todas las conexiones por `.env`, que no se versiona. Comprobación automática antes de cada commit (`src/_check_seguridad.py`). Además, las versiones anteriores de las Entregas 2 y 3 ya se corrigieron (host/BD reales sustituidos por marcadores genéricos) y el fix está subido a GitHub | § 10.2 Seguridad |
| Trabajo mezclado con carpetas ajenas | Repositorio independiente creado (`pfm-estimacion-duracion-procesos`), con las cinco entregas y sin historial heredado. Pendiente solo conectarlo a un remoto de GitHub y purgar el historial del repositorio de curso, con los pasos exactos anotados | `BLOQUEOS.md`, B-003 |

---

# 1. Problema que se busca resolver

## 1.1 Qué ocurre hoy y por qué es un problema

En la asesoría, cada proceso (presentar un modelo tributario, cerrar una contabilidad) se
ejecuta sin ninguna estimación previa de cuánto tiempo llevará, y al cerrar una campaña
nadie revisa sistemáticamente qué negociaciones se han disparado en tiempo respecto a lo
habitual. El trabajo atípico —una incidencia, un cliente más complejo de lo esperado, un
registro de tiempo mal hecho— pasa desapercibido salvo que alguien tropiece con él.

## 1.2 Quién usa el resultado y para qué decisión

Un gestor o responsable de equipo, en dos momentos distintos:

| Uso | Momento | Decisión que apoya |
|---|---|---|
| Planificación | Antes de ejecutar el proceso | Estimar la carga de trabajo de una campaña |
| Control | Al cerrar la campaña | Decidir qué negociaciones merece revisar, de entre miles |

La detección de anomalías **no es un segundo modelo**: es el residuo del modelo de
planificación. Si el modelo estima 24 min para un proceso y se han imputado 1.004, ese
residuo es la señal. Entrenar un detector de anomalías aparte (p. ej. un Isolation
Forest) sería redundante y contradice el alcance decidido tras el feedback recibido.

## 1.3 Qué resultado se considera útil

Dos condiciones, medidas y no supuestas: (a) que el modelo mejore de forma clara un
cálculo de referencia muy simple (la mediana histórica por tipo de proceso), y (b) que el
volumen de negociaciones señaladas como anómalas sea lo bastante pequeño como para que una
persona pueda revisarlo de verdad (se fija el 5 % como límite de lo manejable). Ambas
condiciones se miden en las secciones 6 y 7, y el resultado —incluso cuando la primera no
se alcanza del todo— se reporta tal cual, no se ajusta a posteriori.

## 1.4 Alcance: una sola línea, un solo pipeline

Las versiones anteriores del proyecto abarcaban predicción de rentabilidad, detección de
anomalías y segmentación de clientes a la vez, con la unidad de observación cliente × mes
y una extrapolación a 2027 con solo 19 meses de histórico. Este planteamiento reduce el
alcance a una sola línea (duración de procesos) y a un solo pipeline: **Modelos de
impuestos**.

Por qué ese pipeline y no otro, con las cifras que lo sostienen:

| Criterio | Cifra |
|---|---|
| Etiqueta nativa del proceso, sin heurística de texto | El campo *Modelo presentado* del CRM tiene 52 valores de lista; 16.941 de las 17.223 negociaciones del pipeline lo tienen relleno (98,4 %) |
| Repeticiones suficientes por clase | 25 valores de proceso con 30 o más negociaciones cerradas con tiempo; el más frecuente tiene 3.943 |
| Permite validación temporal real | 6.821 negociaciones cerradas en 2025 y 6.192 en 2026, seis campañas trimestrales en la ventana |

Contabilidad queda como extensión (mismo método, para comprobar que se transfiere) y
Rentas queda fuera del MVP (solo dos campañas, no admite validación temporal). El código
recibe el pipeline como parámetro (`PIPELINE_OBJETIVO`); extenderlo a otro pipeline no
requiere tocar la lógica.

---

# 2. Análisis de datos planteado y utilidad esperada

Todo lo de esta sección se ejecutó **antes** de plantear ningún modelo, para no afirmar
nada sobre los datos sin haberlo medido — es la corrección directa al feedback de
"acceso garantizado" y "calidad excelente" sin explorar.

## 2.1 Preguntas que se responden con los datos

| Pregunta | Análisis | Resultado |
|---|---|---|
| ¿Cuánto del trabajo real llega a verse? | Cobertura: horas con y sin negociación asociada | 11,71 % de las horas imputadas (4.066,6 h) no cuelga de ninguna negociación |
| ¿El target es fiable o está distorsionado por el registro manual? | Sesgo de redondeo: reparto de imputaciones en múltiplos exactos de 60/30/15/5 min | 93,91 % de valores no redondos — se registra con cronómetro, no en bloques |
| ¿Qué forma tiene la variable objetivo? | Distribución de `minutos_total`: mediana, P90, P99, máximo | Cola muy larga: ratio P99/mediana = 30,8 |
| ¿Cuánto se pierde por censura? | Reparto por estado (ganada/perdida/en curso) | 13,10 % perdidas, 0,52 % en curso, quedan fuera del modelo |
| ¿Se ven las campañas trimestrales? | Estacionalidad: negociaciones cerradas por trimestre natural, por proceso | Confirmado; permite el split temporal 2025→2026 |
| ¿Hay concentración de trabajo en pocas personas? | Negociaciones por empleado | 34 empleados imputan en el pipeline; 8 con menos de 30 negociaciones |
| ¿Cuántas negociaciones tienen más de un empleado? | % de negociaciones multi-empleado | 3,84 % — relevante para decidir si el modelo de control necesita `n_empleados` |
| ¿Hay incoherencias que haya que filtrar o declarar? | Negociaciones con 0 minutos, con más de 8 h, con imputaciones fuera de ventana | 21,74 % del pipeline con 0 minutos (censura por selección, no se elimina, se declara) |

## 2.2 Cómo alimenta el modelado y el MVP

- El sesgo de redondeo (93,91 % no redondo) descarta la hipótesis de que el techo del
  error viniera de la granularidad de registro — el ruido tiene otro origen, y eso
  justifica no perseguir un MAE arbitrariamente bajo.
- La cola larga (ratio 30,8) es la razón directa de modelar `log1p(minutos_total)` y de
  evaluar con MAE/MedAE en vez de RMSE (secciones 6 y 7).
- La cobertura (11,71 % de horas huérfanas, 21,74 % de negociaciones a 0 minutos) se
  incorpora al MVP como limitación explícita, no se oculta ni se corrige artificialmente.
- Las figuras que se incorporan al informe final: histograma de `log1p(minutos_total)`,
  boxplot de minutos por proceso, serie temporal de negociaciones cerradas por mes y
  barras del sesgo de redondeo (`output/figuras/01-04_*.png`).

---

# 3. Tipo de modelos que se van a plantear

**Tipo de tarea:** regresión (estimar minutos, con `log1p` como transformación del
objetivo). La detección de anomalías se deriva del residuo de este mismo modelo de
regresión — no es un tipo de tarea aparte.

| Alternativa | Tipo | Por qué se plantea | Limitación principal |
|---|---|---|---|
| **Baseline (B1)** | Mediana por proceso, ajustada solo en train | Referencia mínima defendible: "este tipo de modelo tributario suele tardar X". Si el modelo no la bate con margen, no se justifica usarlo | No captura nada específico del cliente ni de la campaña — solo el tipo de proceso |
| **Modelo candidato 1 (M1)** | Regresión lineal sobre `log1p`, codificación one-hot | Interpretable, referencia de qué aporta la linealidad frente a la mediana | No captura relaciones no lineales ni interacciones entre features |
| **Modelo candidato 2 (M2)** | `HistGradientBoostingRegressor` | Permite comprobar si una mayor complejidad mejora el resultado; gestiona `NaN` de forma nativa (relevante porque las features históricas tienen NaN por diseño anti-leakage) | Mayor riesgo de sobreajuste y menor interpretabilidad directa que M1; requiere importancia por permutación para explicarse |
| **Variante (M3)** | M2 con pérdida cuantílica (q = 0,1 / 0,5 / 0,9) | Da un rango en vez de un punto — "entre 25 y 70 min" es más honesto para planificar que un único número, y la anchura del intervalo es en sí misma información | Los cuantiles se calibran con train (2025) y pueden no transferirse a una campaña con cola distinta (2026) |
| **Modelo de control** | M2 + `responsable_id_grp` + `n_empleados` | Comprueba si el responsable aporta señal — se reporta aparte, nunca para evaluar personas | No es el modelo de planificación (usa una variable que no se conoce hasta después de asignar el trabajo); solo para detección de anomalías de proceso |

No se plantean modelos de detección de anomalías independientes (Isolation Forest,
autoencoders): el alcance acordado tras el feedback usa el residuo del propio modelo de
regresión, no un segundo modelo.

---

# 4. Datos de entrada del análisis y los modelos

**Dataset:** `output/dataset_modelo.parquet`, generado por `src/03_dataset.py` a partir de
la capa gold (Fase 3). **Granularidad:** una fila = una negociación del pipeline objetivo,
cerrada, ganada y con tiempo imputado. **Clave:** `deal_id`. **Fecha de referencia:**
`fecha_creacion` (es el instante en que, en la práctica, se necesitaría la predicción).
**Filas finales:** 13.013, sobre 1.036 clientes distintos.

| Entrada | Descripción | Granularidad / tipo | Uso en el modelo |
|---|---|---|---|
| `proceso` | Modelo tributario presentado (303, 111, 200…) | categórica | Feature directa — la de mayor peso junto con el historial de cliente |
| `ejercicio` | Año fiscal | numérica (21,18 % nulos) | Feature directa, importancia casi nula (0,0000) |
| `trimestre_fiscal` | Trimestre natural de (`fecha_creacion` − 1 mes), derivado | categórica | Feature directa; validada al 99,63 % contra el campo declarado del CRM donde este es comparable |
| `mes_creacion` | Mes de creación de la negociación (1–12) | categórica | Feature directa, importancia baja |
| `dias_desde_alta_cliente` | Antigüedad del cliente en días | numérica (0,11 % nulos) | Feature directa |
| `n_procesos_previos_cliente` | Nº de negociaciones previas de ese cliente, ventana expansiva | numérica histórica | Resume el volumen de relación previa con el cliente |
| `mediana_min_cliente_hist` | Mediana histórica de minutos de ese cliente, ventana expansiva | numérica histórica (17,23 % nulos) | La feature de mayor importancia por permutación (0,0869) |
| `mediana_min_proceso_hist` | Mediana histórica de minutos de ese proceso, ventana expansiva | numérica histórica (17,31 % nulos) | Resume el nivel típico del proceso, más allá de la etiqueta |
| `n_deals_misma_campana` | Nº de negociaciones de la misma campaña creadas hasta esa fecha | numérica | Proxy de carga de la campaña en curso |
| `es_primera_vez_cliente_proceso` | El cliente no tiene historial previo en ese proceso | binaria | Marca los casos sin historial, que reciben `NaN` en las features históricas |

**Variables que no se utilizan, y por qué:** `minutos_max_imputacion`, `n_imputaciones`,
`n_tareas`, `n_empleados`, `fecha_ultima_imputacion`, `fecha_cierre`,
`fecha_primera_imputacion`, `etapa`, `etapa_id`, `semantica`, `cerrada`. Todas se conocen
**solo después** de ejecutar el proceso — usarlas sería fuga de información directa.
`src/03_dataset.py` comprueba su ausencia y aborta si alguna aparece. La única excepción es
`n_empleados`, reservada al modelo de control (sección 3), que no es el modelo de
planificación.

**Qué información estaría realmente disponible en el momento de generar la predicción:**
exactamente las diez columnas de la tabla — nada que dependa de tareas, imputaciones o
fechas de cierre de la propia negociación que se está prediciendo.

---

# 5. Datos de salida y forma de consumo

| Campo de salida | Descripción | Tipo | Uso posterior |
|---|---|---|---|
| `deal_id` | Identificador de la negociación | integer | Trazabilidad; unión con el resto de tablas del proyecto |
| `prediccion_min` | Minutos estimados (`expm1` de la predicción en `log1p`) | float | Planificación de carga antes de ejecutar el proceso |
| `q10_min` / `q90_min` | Intervalo de predicción (solo M3) | float | Rango de planificación; anchura mediana 14,5 min |
| `residuo_min` | `minutos_reales − prediccion_min` | float | Base del cálculo de anomalía |
| `z` | Residuo estandarizado por la sigma del proceso (out-of-fold) | float | Score de anomalía |
| `tipo_anomalia` | `normal` / `exceso` / `defecto` según `\|z\| > 3` | categórica | Filtrado y priorización de casos a revisar |

**Formato:** tabla parquet (`output/predicciones_planificacion.parquet`) más los informes
en markdown de cada fase (`output/0X_*.md`), pensados para integrarse después en un panel
de revisión (ver Entrega 5).

**Cómo lo usa el gestor:** antes de ejecutar, `prediccion_min` (y el intervalo de M3) para
dimensionar la carga de la campaña; al cerrarla, la lista de negociaciones con
`tipo_anomalia = exceso` para decidir cuáles revisar, con el residuo y los factores
(sección 7 de la memoria de resultados) como contexto para juzgar cada caso.

**Qué explicación se muestra:** el multiplicador "veces lo esperado" (más legible que el
z-score en bruto), la mediana histórica del proceso como referencia, y los factores con
mayor peso en la predicción de ese caso — nunca la predicción sola, sin contexto.

---

# 6. Estrategia para diseñar y seleccionar el modelo

1. **Preparación del dataset**: filtros de inclusión aplicados en orden, documentando
   cuántas filas caen en cada uno (pipeline → cerrada → ganada → minutos > 0 → proceso no
   vacío), de 30.836 negociaciones de partida a 13.013 finales.
2. **Definición del target**: `log1p(minutos_total)`; todas las métricas se deshacen a
   minutos con `expm1` antes de reportarse — un MAE en escala logarítmica no significa
   nada para un gestor.
3. **Baseline**: los cuatro baselines de la sección 3 se calculan **antes** que cualquier
   modelo, ajustados solo con train. B1 (mediana por proceso) se fija como referencia:
   MAE = 16,37 min en el test temporal.
4. **Modelos candidatos**: M1 y M2 de la sección 3, más la variante M3 y el modelo de
   control, entrenados en ese orden.
5. **Preprocesamiento**: sin escalado (no lo necesita `HistGradientBoostingRegressor`);
   categorías no vistas en train se convierten a `NaN` en vez de asignarse a la más
   frecuente (decisión conservadora, no inventa pertenencia); procesos con menos de 100
   casos en train se agrupan en `OTROS` en una de las variantes del bucle de mejora.
6. **Criterios de comparación**: MAE en minutos sobre la validación interna
   (`GroupKFold(4)` por cliente dentro de train) como criterio de decisión; estabilidad
   (mejora sostenida en los 4 folds); interpretabilidad (importancia por permutación);
   coste computacional (no es un factor limitante con este volumen de datos).
7. **Regla de decisión final — bucle de mejora con criterio de parada declarado antes de
   abrirlo**:

   | Elemento | Valor |
   |---|---|
   | Métrica de decisión | MAE en minutos sobre `GroupKFold(4)` por cliente, dentro de train |
   | Umbral de aceptación | Mejora ≥ 10 % sobre el MAE de B1 en esa misma validación (11,53 min) |
   | Intentos máximos | 5, en un orden fijado de antemano |
   | Papel del test temporal | Ninguno en la decisión de parada — aparece en la tabla solo como trayectoria observada |

   Resultado real del bucle: se agotaron los 5 intentos (agrupar procesos poco
   frecuentes, features de carga de campaña, ajuste de hiperparámetros, target encoding
   por cliente dentro de cada fold, recorte de la cola al P99 solo en train) sin alcanzar
   el 10 %. La variante elegida (ajuste de hiperparámetros, intento 3) es la mejor en
   validación interna, **no** la mejor en test — eso confirma que la selección no miró el
   conjunto de evaluación para decidir (detalle completo en la Entrega de resultados,
   `output/05_modelos.md`).

La selección no se basó en la métrica más alta a secas: el intento 4 (target encoding)
obtuvo peor MAE de validación que el intento 3 y se descartó por eso, no por su MAE de
test.

---

# 7. Estrategia de validación y evaluación

| Elemento | Decisión prevista | Justificación |
|---|---|---|
| Separación de datos | Split temporal (train: cerradas 2025, 6.821 filas · test: cerradas 2026, 6.192 filas) + `GroupKFold(4)` por cliente dentro de train | Reproduce el uso real (se entrena con el pasado, se aplica al futuro) y evita que el mismo cliente aparezca en ambos lados de la validación interna |
| Métrica principal | MAE en minutos, deshecho de `log1p` | Refleja el error tal como lo entendería un gestor; MedAE se reporta como complemento robusto a la cola |
| Baseline | B1 — mediana de train por tipo de proceso | Es el mínimo defendible: si el modelo no lo mejora con margen, no se justifica la complejidad añadida |
| Criterio de aceptación | Mejora ≥ 10 % sobre B1 en la validación interna, máximo 5 intentos | Fijado antes de entrenar nada, para no mover el listón según conviniera al resultado |

**Cómo se evita la fuga de información:** toda feature histórica se calcula únicamente
con negociaciones cuya `fecha_cierre` es estrictamente anterior a la `fecha_creacion` de
la fila (ventana expansiva, nunca el conjunto completo); las filas sin historial reciben
`NaN`, no la media global. Verificación cuantitativa: ninguna feature supera 0,95 de
asociación con el target dentro de train — la más alta es `proceso`, con 0,441.

**Resultado frente al baseline** (test temporal, todas las métricas en minutos):

| Modelo | MAE | Mejora sobre B1 | MedAE | % ±5 min | % ±15 min |
|---|---|---|---|---|---|
| B1 (referencia) | 16,37 | 0,00 % | 4,88 | 50,95 | 72,37 |
| M1 regresión lineal | 16,40 | −0,18 % | 5,91 | 44,62 | 74,63 |
| M2 gradient boosting | 15,50 | 5,31 % | 4,65 | 52,05 | 80,17 |
| M3 cuantil 0,5 | 15,37 | 6,11 % | 4,42 | 53,42 | 80,02 |
| Modelo de control | 14,94 | 8,74 % | 5,18 | 49,03 | 78,81 |

**Estabilidad** (`GroupKFold(4)` por cliente, dentro de train): M2 mejora a B1 en los 4 de
4 folds, con ganancias de entre el 1,66 % y el 2,77 %.

**Análisis de errores y casos extremos:** los dos mayores errores de test son
negociaciones del mismo proceso (347), con 1.003,7 y 795,4 minutos reales frente a una
mediana histórica de ese proceso de 22,8 min — ninguna feature disponible antes de
ejecutar el proceso anticipa esa diferencia. Hay además deriva entre campañas: el P99 de
`minutos_total` pasa de 143,7 min en train a 189,9 min en test.

**Qué resultado mínimo se consideraría aceptable, y qué se hizo al no alcanzarlo:** el
umbral fijado (10 % de mejora) no se alcanzó (5,31 % real). Conforme a lo decidido antes
de empezar, esto se documenta como resultado negativo — no se tocó el test, no se
recortaron casos difíciles ni se reajustó el baseline a la baja. El proyecto continúa
usando M2, porque aunque su ganancia de planificación es modesta, su residuo es la base
útil de la sección de anomalías (ver Entrega de resultados, § 8).

---

# 8. Riesgos y alternativas

**¿La variable objetivo está disponible y representa el fenómeno que se quiere predecir?**
Disponible sí; representa el fenómeno de forma parcial. Es tiempo *imputado*, no medido: el
93,91 % de los valores no son redondos (se cronometra, no se estima en bloques), pero el
21,74 % de las negociaciones cerradas del pipeline tiene 0 minutos y el 11,71 % de las
horas imputadas no cuelga de ninguna negociación. El modelo aprende del trabajo que llegó
a registrarse, no de todo el trabajo real.

**¿Existe riesgo de leakage?** Se mitigó con la regla de ventana expansiva estricta
(sección 7) y se verificó cuantitativamente (máxima asociación 0,441, muy lejos del
umbral de 0,95 fijado como alarma).

**¿Volumen, histórico y calidad suficientes?** Volumen sí (13.013 filas). Histórico
limitado: la validación temporal se apoya en dos campañas (2025 y 2026); con solo dos
años, la deriva medida entre ellas no puede separarse de la variación año a año normal.

**¿Hay desbalanceo, cambios temporales o segmentos con pocos datos?** Los tres a la vez:
la distribución del target tiene una cola muy larga (ratio P99/mediana = 30,8); hay deriva
temporal medible entre campañas (P99 pasa de 143,7 a 189,9 min); y varios procesos tienen
menos de 20 casos en train, lo que obliga a usar la sigma global del pipeline en vez de la
propia del proceso para el cálculo de anomalías.

**¿Qué parte de la estrategia genera más incertidumbre?** Los intervalos de M3: cubren el
real en el 54,80 % de los casos de test frente al 80 % nominal — están mal calibrados por
la misma deriva entre campañas, y no son utilizables como garantía de cobertura sin
recalibrarlos por campaña.

**¿Qué alternativa se aplicó al no superar el baseline con margen?** No se abrió un sexto
intento fuera de lo planeado, ni se tocó el test: se documentó la mejora real (5,31 %)
como resultado por debajo del umbral, con las tres causas medidas que lo explican (cola
larga, deriva temporal, censura del target — detalle en la Entrega de resultados). El
modelo se mantiene en producción para la tarea de planificación, con esa mejora modesta
declarada, y su residuo se reutiliza íntegramente para la detección de anomalías, que es
donde aporta el valor más claro (3,86 % de tasa de marcado, dentro del límite de
manejabilidad del 5 %).

---

# 9. Limitaciones declaradas

1. **El target es tiempo imputado manualmente, no medido.** El modelo aprende tanto el
   esfuerzo real como el hábito de imputación. El registro es cronometrado —el 93,91 % de
   las imputaciones tiene un valor no redondo—, lo que descarta el redondeo en bloques
   como fuente principal de ruido, pero no garantiza que el cronómetro se arranque y se
   pare cuando empieza y acaba el trabajo.
2. **Solo se observan negociaciones cerradas y ganadas.** Las 2.257 perdidas (13,10 %) y
   las 90 en curso (0,52 %) del pipeline quedan censuradas y fuera del modelo.
3. **El trabajo que no cuelga de ninguna negociación es invisible al modelo.** Son
   4.066,6 h, el 11,71 % de las horas imputadas en la ventana. A esto se suma que el
   21,74 % de las negociaciones cerradas del pipeline no tiene ningún minuto imputado.
4. **El histórico cubre un número limitado de campañas.** La validación temporal se apoya
   en los cierres de 2026 (6.192 negociaciones) frente a los de 2025 (6.821). Con dos
   años, la deriva medida entre campañas —el P99 pasa de 143,7 a 189,9 min— no puede
   separarse de la variación año a año.
5. **Los resultados son específicos de esta asesoría.** Dependen de su cartera de
   clientes, de su reparto de modelos tributarios y de sus hábitos de imputación. No hay
   base para extrapolarlos a otra asesoría.
6. **El modelo de control incluye al responsable como variable.** Su finalidad es
   detectar anomalías de proceso, no evaluar el desempeño de personas. Se reporta por
   separado del modelo de planificación, que no lo incluye, y su uso queda restringido a
   la revisión de casos.

---

# 10. Trabajo futuro y estado de la entrega

## 10.1 Qué desbloquearía cada línea

| Línea | Qué falta para abordarla |
|---|---|
| Extensión a contabilidad | Ejecutar los mismos scripts cambiando `PIPELINE_OBJETIVO`. Volumen disponible: 10.347,6 h entre Contabilidad Interna, Contabilidad Externa y Cierres. No requiere código nuevo |
| Extensión a rentas | Requiere una tercera campaña. Con dos (2025 y 2026) la validación temporal se reduce a un único corte |
| Recalibrar los intervalos de M3 | Estimar los cuantiles por campaña en lugar de sobre train completo, y medir de nuevo la cobertura frente al 80 % nominal |
| Reducir la censura del 21,74 % de negociaciones sin tiempo | Es un cambio de proceso en la asesoría, no de modelo: imputar tiempo a toda negociación cerrada |
| Integrar el panel de revisión (Entrega 5) | Conectar la maqueta a los `.parquet` reales de esta entrega; hoy es solo visual |

## 10.2 Seguridad y reproducibilidad

Las conexiones se configuran mediante un archivo `.env` que no se versiona. Antes de cada
commit se ejecuta `src/_check_seguridad.py`, que busca en todo lo que se va a versionar
patrones de dirección IP, cadenas de credencial y nombres de base de datos, y aborta si
encuentra alguno. Los datos (`*.csv`, `*.parquet`, `*.pkl`) están excluidos del control de
versiones; solo se versionan el código, los informes en markdown y las figuras.

Las versiones anteriores de las Entregas 2 y 3, que contenían un host y un nombre de base
de datos reales, ya se corrigieron (sustituidos por marcadores genéricos) y el fix está
publicado en el repositorio de curso. Las credenciales de acceso a la base de datos se han
rotado.

Cada script de `src/` se ejecuta de cero sin pasos manuales:

```
py -m pip install -r requirements.txt
py src/00_descubrimiento.py
py src/01_extraccion.py
py src/02_eda.py
py src/03_dataset.py
py src/04_baselines.py
py src/05_modelos.py
py src/06_anomalias.py
```

## 10.3 Lo que queda pendiente

| Pendiente | Estado |
|---|---|
| Conectar `pfm-estimacion-duracion-procesos` a un remoto de GitHub | El repositorio existe en local, completo (Entregas 1-5), sin historial heredado. Falta solo el push |
| Purgar del historial del repositorio de curso los commits antiguos con IP/BD | Riesgo activo ya cerrado (versión visible corregida y credenciales rotadas); la purga de commits antiguos queda registrada en `BLOQUEOS.md` (B-003) sin urgencia |
| Validación ciega con experto | **Resuelta.** Acuerdo del 52,6 % sobre 38 casos usables; detalle y las dos causas de desacuerdo medidas en `output/06_anomalias.md`, § 5.1 |

## 10.4 Trazabilidad de las cifras

Toda cifra de este documento procede de un script de `src/` y está en un informe de
`output/`:

| Sección | Script | Informe |
|---|---|---|
| 1 Problema, 2 Análisis de datos | `01_extraccion.py`, `02_eda.py` | `RESUMEN_extraccion.md`, `02_informe_calidad.md` |
| 4 Datos de entrada | `03_dataset.py` | `03_diccionario_datos.md` |
| 3, 6, 7 Modelos, estrategia y validación | `04_baselines.py`, `05_modelos.py` | `04_baselines.md`, `05_modelos.md` |
| 5, 8 Datos de salida y riesgos (anomalías) | `06_anomalias.py` | `06_anomalias.md` |

Las decisiones tomadas durante la ejecución, con su alternativa descartada, están en
`DECISIONES.md` (D-001 a D-014). Los puntos en los que la realidad contradijo lo previsto,
en `BLOQUEOS.md` (B-001 a B-006).
