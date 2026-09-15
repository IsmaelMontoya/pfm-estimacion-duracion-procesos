# PFM — Estimación de la duración de procesos en una asesoría

> Versión corregida tras el feedback de las entregas 2 y 3.
> Este directorio está pensado para extraerse a un **repositorio independiente**
> dedicado exclusivamente al PFM, como pidió la corrección.

## Qué cambia respecto a la propuesta anterior

| Antes | Ahora |
|---|---|
| Tres líneas a la vez: predicción de rentabilidad + anomalías + segmentación | **Una**: estimar la duración de un proceso |
| Problema temporal (extrapolar a 2027 con 19 meses) | Problema **transversal**: 1 negociación cerrada = 1 observación |
| Unidad: cliente × mes (~17.000 filas débiles) | Unidad: **negociación** (proceso ejecutado), etiquetada por el propio CRM |
| Dependía del CRM **y** de un segundo sistema de facturación | Solo el CRM. Sin facturación, sin rectificativas, sin desfases |
| Anomalías como modelo aparte (Isolation Forest) | Anomalía = **residuo estandarizado** del mismo modelo |
| "Acceso 100 % garantizado", "calidad excelente" | Fase 0 que **mide** la calidad antes de afirmar nada |

La detección de anomalías deja de ser un segundo proyecto: si el modelo estima
42 min para un proceso y se han imputado 190, el residuo es la señal. Un modelo,
dos usos — planificación (antes) y control (al cerrar cada campaña).

## Unidad de observación

El trabajo de la asesoría está organizado en **negociaciones** de Bitrix, agrupadas
en pipelines. Cada negociación es una ejecución concreta de un proceso para un
cliente. El tiempo se imputa en las tareas que cuelgan de ella; la duración del
proceso es la suma de esas imputaciones.

```
b_tasks_elapsed_time  →  tarea  →  (UF_CRM_TASK = 'D_<id>')  →  negociación  →  pipeline
```

La clasificación del proceso **no se deduce del título**: viene del pipeline y de
campos de lista del propio CRM (p. ej. *modelo presentado* en fiscal). Eso elimina
la heurística de texto que habría habido que justificar.

### Pipelines existentes

| Área | Pipelines |
|---|---|
| Administración | Facturación interna · Onboarding clientes · Gestión interna |
| Contable | Contable interno · Contabilidad externa · Cierres |
| Fiscal | **Modelos de impuestos** · Rentas |
| Fiscal · expedientes | Cuentas anuales · Libros oficiales · Libro de socios |

## Decisión de alcance

**MVP = pipeline "Modelos de impuestos".** Único objetivo de la primera entrega.

Por qué ese y no otro:

- **Etiqueta nativa y limpia**: el campo *modelo presentado* (303, 111, 115, 200…)
  es la variable explicativa principal. No hay que inventar una taxonomía.
- **Seis campañas en 19 meses** (4 trimestres de 2025 + 2 de 2026). Permite el
  split temporal honesto: entreno 2025 / test 2026. Es el argumento anti-leakage
  que exigió la corrección.
- **Muchas repeticiones por clase**: la mediana por modelo es un baseline sólido
  y la comparación contra él tiene sentido estadístico.

Qué queda fuera y por qué:

- **Rentas** → extensión, no MVP. Solo dos campañas (2025, 2026), y una campaña es
  un único bloque temporal: no admite validación en el tiempo, solo por cliente.
  Interesante por su varianza (individual / conjunta / compleja), pero como línea
  principal no es defendible.
- **Contabilidad** → segundo pipeline. Sirve para demostrar que el método **se
  transfiere**, que es lo que convierte esto en un proyecto y no en un análisis
  puntual.
- **Resto de pipelines** → fuera del PFM.

**Principio de diseño**: el código no sabe con qué pipeline trabaja. Recibe un
pipeline y una columna de tipo de proceso. Ejecutarlo luego sobre contabilidad
son horas, no semanas.

## Estado

Numeración de fases según el plan de trabajo de este proyecto (ver metodología más
abajo), que sustituye a la numeración del borrador anterior de este README.

| Fase | Script | Gate | Estado |
|---|---|---|---|
| 1 · Extracción | `src/00_descubrimiento.py`, `src/01_extraccion.py` | 4 de 4 criterios cumplidos | completada |
| 2 · Calidad y EDA | `src/02_eda.py` | 93,91 % de imputaciones no redondas; ratio P99/mediana = 30,8 | completada |
| 3 · Dataset modelable | `src/03_dataset.py` | 13.013 filas; 0 features prohibidas; 0 features con asociación > 0,95 | completada |
| 4 · Baselines | `src/04_baselines.py` | B1 fijado como referencia: MAE = 16,37 min en test | completada |
| 5 · Modelado | `src/05_modelos.py` | M2 mejora a B1 un 5,31 % en test (umbral 10 %): resultado negativo documentado; 4 de 4 folds a favor | completada |
| 6 · Anomalías | `src/06_anomalias.py` | tasa de marcado 3,86 % en test; 40 casos generados para validación ciega | completada |
| 7 · Memoria y entrega | `docs/entregas/04_estimacion_duracion_procesos.md` | checklist de entrega: 19 casillas cumplidas, 1 parcial, 3 no cumplidas (B-003 y B-005) | markdown terminado; PDF pendiente |

## Cómo reproducirlo de cero

```
py -m pip install -r requirements.txt
cp .env.example .env      # y rellenar
py src/00_descubrimiento.py
py src/01_extraccion.py
py src/02_eda.py
py src/03_dataset.py
py src/04_baselines.py
py src/05_modelos.py
py src/06_anomalias.py
```

Cada script escribe en `output/`, que no se versiona. `sql/A_00_descubrimiento.sql`
documenta las consultas de descubrimiento y `sql/B_extraccion.sql` es la fuente
única de las consultas de extracción: `src/01_extraccion.py` lee de ese archivo.

## Metodología aplicada

- **Target**: `log1p(minutos_imputados)` por negociación cerrada y ganada. Ratio
  P99/mediana medido = 30,8.
- **Métrica**: MAE y MedAE en minutos, deshaciendo la transformación con `expm1`.
  RMSE y MAPE solo informativos, por la cola y por las negociaciones de menos de
  un minuto (7,31 % del dataset).
- **Baseline de referencia**: B1, mediana por tipo de proceso ajustada solo con
  train. MAE = 16,37 min en test. El modelo lo bate un 5,31 %, por debajo del
  10 % que se fijó como umbral; se reporta como resultado negativo.
- **Anti-leakage**: split temporal por campaña (cierres de 2025 frente a cierres
  de 2026) **y** `GroupKFold(4)` por cliente. Features históricas con ventana
  expansiva estricta (`fecha_cierre < fecha_creacion` de la fila).
- **Dos variantes**:
  - *Planificación*: sin la variable empleado (no se conoce al asignar).
    MAE 15,50 min.
  - *Control*: con empleado. MAE 14,94 min, con el responsable en la posición 2
    de 12 en importancia por permutación. Se reporta aparte por sus implicaciones
    éticas.

## Limitaciones declaradas

Las seis limitaciones completas, con sus cifras, están en la sección 9 de
`docs/entregas/04_estimacion_duracion_procesos.md`. Las tres que más condicionan
el alcance:

1. El target es tiempo **imputado**, no medido. El registro es cronometrado (el
   93,91 % de las imputaciones tiene valor no redondo), lo que descarta el
   redondeo en bloques como ruido principal, pero no garantiza que el contador se
   arranque y se pare cuando empieza y acaba el trabajo.
2. Solo se observan negociaciones **cerradas y ganadas**. Quedan fuera 2.257
   perdidas (13,10 %) y 90 en curso (0,52 %) del pipeline.
3. El trabajo que no cuelga de ninguna negociación es invisible al modelo:
   4.066,6 h, el 11,71 % de las horas imputadas en la ventana. A eso se suma que
   el 21,74 % de las negociaciones cerradas del pipeline tiene 0 minutos
   imputados.

## Seguridad

- Sin IPs, hostnames, nombres de base de datos ni credenciales en el repositorio.
- Las conexiones se configuran por `.env`, ignorado por Git.
- Las salidas son agregadas: sin nombres de empresa, NIF ni nombres de empleado.
