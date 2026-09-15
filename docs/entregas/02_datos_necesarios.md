# Entrega 2 - Selección de Idea y Análisis de Datos Necesarios

> **Actualización — ver Entrega 4.** El enfoque de este documento (predicción de rentabilidad,
> facturación vía Biloop, detección de anomalías y segmentación a la vez) se abandonó tras el
> feedback recibido — también las afirmaciones de "acceso garantizado" y "calidad excelente" sin
> haber explorado los datos reales. El proyecto pivotó a una sola línea — estimar la duración de los
> procesos de la asesoría, solo con datos de Bitrix, sin Biloop ni facturación — documentada en
> `docs/entregas/04_estimacion_duracion_procesos.md`, con la tabla de respuesta punto por punto al
> feedback en su sección inicial. Este documento se conserva sin reescribir como registro de la
> propuesta original; los valores de host y base de datos se han sustituido por marcadores
> genéricos por motivos de seguridad.

## 1. Idea Seleccionada

### Predicción de Rentabilidad de Clientes y Detección de Anomalías mediante Machine Learning

**Párrafo 1 - Problema que resuelve:**

En una asesoría, el análisis de rentabilidad de clientes está disperso y resulta difícil identificar cuáles generan valor real, cuáles están en riesgo, o cuáles tienen patrones anómalos. Los datos de imputación de tiempo y facturación existen pero no se relacionan sistemáticamente para cada cliente. No hay forma de predecir qué clientes tendrán anomalías o perderán rentabilidad en el futuro. Actualmente se analiza de forma reactiva (histórico), pero sin predicción proactiva ni detección automática de anomalías.

**Párrafo 2 - Solución planteada:**

Se propone desarrollar un sistema integral de machine learning que: (a) predice rentabilidad futura por cliente (entrenando con datos históricos 2025, validando contra 2026 real, prediciendo 2026-2027), (b) detecta automáticamente anomalías en patrones de tiempo/coste mediante algoritmos de outlier detection, y (c) segmenta clientes en 4-5 grupos por perfil de rentabilidad para tarifar o estrategiar diferenciado. El enfoque combinará modelos predictivos (Random Forest, XGBoost) con detección de outliers (Isolation Forest), análisis exploratorio completo, y explicabilidad (SHAP values).

**Párrafo 3 - MVP del proyecto final:**

El MVP consistirá en: (1) tabla de rentabilidad limpia y validada (914 empresas × 19 meses = ~17.366 registros), (2) modelos ML entrenados y evaluados con métricas reales (MAE, RMSE, F1), (3) predicciones para ago-dic 2026 validadas contra datos reales ene-jul 2026, (4) sistema de detección de anomalías flagging clientes sospechosos, (5) segmentación automática de clientes (cash cows, en riesgo, alto potencial, anómalos), (6) documentación completa con EDA, feature engineering, y código reproducible. Sistema potencialmente automatizable: se actualiza mensualmente sin intervención manual.

---

## 2. Datos Necesarios

### Variables y Campos Requeridos

Se construirá desde datos raw de las siguientes fuentes:

**FactTiemposBitrix** (imputaciones horarias):
- ID_Elapsed, USER_ID, TASK_ID, MINUTES, SECONDS, CREATED_DATE, DATE_START, DATE_STOP, COMMENT_TEXT

**FactFacturasBiloop** (facturación):
- NIF_Norm, Fecha, BASEIMPONIBLE, IMPORTE, CODIGO_EMPRESA, SITUACION (factura vs rectificativa)

**DimEmpresaBitrix** (información de cliente):
- ID_Bitrix, NomEmpresa_Bitrix, COMPANY_TYPE, NIF_Norm, Tipo_Empresa (PF/SL/CB), Despacho, Grupo_ID, Cliente_Activo_ID, DATE_CREATE

**DimCosteEmpleado** (costes):
- ID_Empleado, NombreEmpleado, CosteAnual, CosteHora

**Bridges y catálogos**:
- BridgeTareaDeal: Conexión tarea ↔ deal ↔ empresa
- DimActividad, DimObligacionTributaria: Features categóricas de cliente
- DimGrupoEmpresarial: Agrupación empresarial

### Nivel de Granularidad

- **Granularidad raw:** Por imputación (65.526 registros), por factura (87.679 registros)
- **Granularidad agregada:** **1 fila = 1 empresa + 1 período (mensual)**
- **Tabla final:** ~914 empresas × 19 períodos = ~17.366 registros

### Profundidad Histórica

**Disponible:** 19 meses (ene 2025 - jul 2026)

**Uso:**
- **TRAIN:** ene-ago 2025 (8 meses de aprendizaje)
- **VALIDATION:** sep-dic 2025 (4 meses de ajuste de hiperparámetros)
- **TEST:** ene-jul 2026 (7 meses - validación real ya disponible)
- **PREDICT_1:** ago-dic 2026 (6 meses futuros, corto plazo)
- **PREDICT_2:** 2027 (12 meses, largo plazo)

### Volumen Aproximado de Datos

- **Imputaciones de tiempo:** 65.526 filas (ene 2025 - jul 2026)
- **Facturas:** 87.679 filas (ene 2025 - jul 2026)
- **Empresas activas:** 914 en Bitrix
- **Empleados:** 47 con imputaciones de tiempo
- **Tabla gold final:** ~17.366 registros (914 empresas × 19 meses)
- **Tamaño:** ~10-50 MB CSV (muy manejable para Python)

### Datos Imprescindibles vs. Deseables

**Imprescindibles (para construir tabla):**
- Horas imputadas + fecha + empleado (→ Coste Directo)
- Facturación + fecha + empresa (→ Ingresos)
- ID empresa (→ Identificación única)
- Coste/hora empleado (→ Cálculo de costes)

**Deseables (enriquecimiento de features para ML):**
- Tipo empresa (PF/SL/CB) → feature categórica
- Despacho responsable → feature categórica
- Actividades principales (20 modelos) → multi-label features
- Obligaciones tributarias (52 modelos) → proxy de complejidad
- Grupo empresarial (86 grupos) → feature categórica
- Antigüedad cliente (DATE_CREATE) → feature temporal
- Provincia/Municipio → feature geográfica

---

## 3. Fuentes de Datos Previstas

### Fuentes Concretas

1. **Bitrix24 (MySQL):** `IP BITRIX` / db `name db bitrix`
   - CRM propietario: empresas, deals, tareas, imputaciones de tiempo, obligaciones tributarias, actividades
   
2. **Biloop (SQL Server):** `IP BILOOP` / db `name db biloop`
   - ERP contable/laboral: facturas, contabilidad, data de empresas

### Tipo de Acceso

- **Privada/Interna:** Datos confidenciales de empresa; acceso restringido a empleados autorizados
- **Uso académico:** Datos utilizados con fines educativos bajo acuerdo de confidencialidad
- **Acceso garantizado:** Como empleado de la asesoría desde julio 2026

### Formato de Extracción

- **SQL queries directo** desde Bitrix MySQL y Biloop SQL Server
- **Exportación a CSV** para procesamiento en Python
- **Formato de salida:** CSV (simple, estándar, reproducible)

### Histórico Disponible

**Sí, 19 meses completos:**
- FactTiemposBitrix: desde 01/01/2025
- FactFacturasBiloop: desde 01/01/2025 (histórico disponible desde 1998)
- Empresas/Clientes: histórico completo en Bitrix desde varios años

### Estabilidad y Mantenimiento

- **Bitrix24:** Sistema en producción, actualizado diariamente
- **Biloop:** ERP en operación, datos críticos para la asesoría
- **Riesgo bajo** de cambios drásticos durante el proyecto
- **Riesgo medio:** Cambios en estructura si hay migraciones de software

### Riesgos Detectados

1. **Acceso a BD:** Requiere permisos SQL; gestionar con equipo IT
2. **Calidad de imputaciones:** Algunos empleados pueden no imputar consistentemente
3. **Fechas inconsistentes:** Desfase entre imputación (mes N) y facturación (mes N+1, N+2)
4. **Duplicados potenciales:** Empresas duplicadas por NIF en Bitrix (ya se excluyen en Bitrix)
5. **Confidencialidad:** Anonimizar nombres de empresa antes de compartir análisis
6. **Algunos empleados sin coste:** IDs negativos en DimCosteEmpleado que no cruzan con FactTiempos
7. **Rectificativas:** Facturas negativas requieren tratamiento especial en margen

---

## 4. Consideraciones de Privacidad y Protección de Datos

### Datos Personales Identificables

Sí. Los datos incluyen:
- Nombres y datos identificativos de clientes (empresas y representantes)
- Información fiscal y contable sensible
- Datos de empleados/asesores

### Medidas de Anonimización Necesarias

- **Identificadores de cliente:** Reemplazar nombres con IDs numéricos o códigos (ID_Bitrix)
- **Datos contables:** No incluir cifras exactas en análisis públicos; usar rangos o anonimizar
- **Datos personales:** Eliminar nombres de contactos, emails, teléfonos de reportes finales
- **Información geográfica:** Generalizar por región si es necesario en análisis compartidos

### Uso Seguro en Proyecto Académico

- Los datos se procesarán bajo **acuerdo de confidencialidad laboral**
- Se aplicarán técnicas de **anonimización completa** antes de incluir en reportes académicos
- **Acceso limitado:** Solo el autor del proyecto manipula datos originales
- **Almacenamiento seguro:** Datos en repositorio privado con acceso restringido

### Riesgos Éticos y Legales

- **RGPD:** Los datos de clientes están sujetos a regulaciones europeas de protección de datos
- **Confidencialidad comercial:** Información de clientes es activo confidencial de la asesoría
- **Responsabilidad:** Cualquier fuga de datos podría afectar reputación de la asesoría

### Mitigaciones Implementadas

- Uso de técnicas de anonimización antes de análisis detallado
- Reportes públicos sin datos identificables
- Almacenamiento seguro de datos originales en repositorio privado
- Documentación clara de permisos de acceso

---

## 5. Viabilidad Inicial del Proyecto

### ¿Parece viable obtener los datos necesarios?

**Sí, 100% viable.** Acceso garantizado como empleado de la asesoría desde julio 2026. Ya dispone de 19 meses de datos históricos (ene 2025 - jul 2026) en sistemas internos (Bitrix, Biloop). No depende de fuentes externas.

### ¿La información disponible tiene suficiente calidad, granularidad y profundidad histórica?

**Sí, excelente.** Datos reales confirmados:
- **19 meses de histórico real** (ene 2025 - jul 2026)
- **65.526 imputaciones de tiempo** (granularidad: por empleado, por tarea, por fecha)
- **87.679 líneas de factura** (granularidad: por factura, por cliente, por fecha)
- **914 empresas** en Bitrix con metadata completa
- **Actualización diaria** (sistemas en producción)

El principal riesgo es la **calidad en imputaciones manuales** (outliers, nulls, inconsistencias en fechas), pero es manejable con limpieza y validación.

### ¿La idea puede desarrollarse de forma realista durante el curso?

**Sí.** El scope es controlable:
- No requiere recolección compleja de datos de múltiples APIs
- El MVP (tabla limpia + modelos ML + análisis + documentación) es alcanzable en el marco del curso
- Permite iteración: versión 1 básica, versión 2 con mejoras en features/modelos

### ¿Qué parte del proyecto veis más arriesgada en este momento?

1. **Acceso a datos:** Depende de permisos internos; debe gestionarse desde el primer día
2. **Calidad de datos:** Posibles inconsistencias requieren limpieza exhaustiva
3. **Confidencialidad:** Balancear análisis útil con anonimización necesaria
4. **Complejidad de features:** 914 empresas × features múltiples = espacio de features grande

### ¿Qué alternativa tendríais si la fuente principal de datos no funciona?

1. **Plan B:** Si no logra acceso a datos en la asesoría, podría:
   - Usar **datos públicos de asesorías** (datos fiscales agregados de organismos públicos)
   - Simular datos sintéticos realistas basados en patrones de asesorías

2. **Alcance reducido:** Enfocar el proyecto en un subset de datos más pequeño (ej: solo 100-200 empresas clave)

---

## Conclusión

**La idea de predicción de rentabilidad y detección de anomalías es VIABLE y RECOMENDADA** para este proyecto porque:

✅ **Acceso garantizado** a datos reales como empleado de la asesoría  
✅ **Datos de calidad media-alta** con suficiente profundidad histórica  
✅ **Problema real y relevante** con valor inmediato para la empresa  
✅ **Scope manejable** para el marco del curso (17k registros, ML estándar)  
✅ **Escalabilidad** posible en el futuro (hacia automatización mensual)  
✅ **Validación científica** posible: entrenar 2025, comprobar 2026, predecir futuro  

**Próximos pasos:**
- Confirmar acceso a sistemas Bitrix/Biloop
- Descargar datos y explorar calidad
- Comenzar construcción de capa gold
