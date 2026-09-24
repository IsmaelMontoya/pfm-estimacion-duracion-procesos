# Panel de Anomalías

Panel interactivo que muestra el modelo aplicado a las 6.192 negociaciones reales
del conjunto de test (2026), usado como apoyo visual en la defensa del proyecto.
No forma parte del pipeline de análisis: es una capa de presentación sobre los
resultados ya calculados en `output/06_anomalias.md` y `output/05_modelado.md`.

## Cómo abrirlo

Es HTML/JS estático, sin build ni servidor. Basta con abrir `panel_anomalias.html`
en un navegador (doble clic, o "Open with Live Server" en el editor).

## Contenido

- `panel_anomalias.html` — la aplicación (dos vistas: presentación y panel de gerente).
- `casos_reales.js` — las 6.192 negociaciones de test, anonimizadas por código de
  cliente (`empresa`, entero) y de responsable (`empleado`, entero); sin nombres,
  NIF ni ningún dato identificativo.
- `empleados_reales.js` — recuento de negociaciones y casos marcados por responsable
  (26 responsables, solo por id numérico).

## Datos

Todos los números son reales, exportados de `dataset_modelo.parquet` (partición de
test) y `output/06_anomalias.md` §3 (sigma por proceso). Ninguna cifra es ilustrativa.
