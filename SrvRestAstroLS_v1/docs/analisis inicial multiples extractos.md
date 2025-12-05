# Análisis inicial – múltiples extractos (ene–nov 2025)

## Fuentes procesadas
- Extractos banco: 01 a 11 (`01- Enero al 31.xlsx` … `11-Noviembre completo.xlsx`), consolidados en `tmp/extracto_2025_01_11.xlsx` para las pruebas.
- Contable: `PILAGA SANTANDER RIO.xlsx` (hoja “Resumen cuenta bancaria”).
- Ventana usada: ±5 días (por defecto de endpoints `/api/reconcile/details*`).

## Cobertura temporal
- Banco: 2025-01-01 a 2025-11-28.
- Contable: 2025-01-01 a 2025-11-28.
- Tramo continuo más largo en extractos (sin cortes de fechas con movimiento): 2025-03-24 a 2025-05-16 (54 días).

## Resultado de conciliación (endpoints actuales)
- No en banco (PILAGA sin banco): 3,447 operaciones — total $3,130,989,499.19.
- No en contable (Banco sin PILAGA): 3,114 operaciones — total $2,634,823,211.34.
- Pares 1→1: 2,243 — total $‑2,244,757,361.35.
- Agrupados aprobados N→1: 216 grupos — total $‑655,402,527.92.
- Sugeridos N→1: 24 grupos — total $‑11,400,803.67.
- Performance pipeline end-to-end (±5 días, datos completos): ~81 s en entorno local.

## Observaciones UX
- Necesario flujo de carga múltiple (11 archivos) y consolidación anual; mostrar cobertura (rangos y gaps) tras ingestión.
- Cards separadas ya existen: No banco, No contable, Pares, N→1 aprobados, N→1 sugeridos. Útil agregar badges con totales y montos (los endpoints ya devuelven `total_amount`).
- Mostrar progreso y validación de tipo (extracto vs contable) al subir; `uploads_v2` ya emite SSE `INGEST_PREVIEW`.
- Para usuario final, sería valioso: filtro por mes/fuente, export de sobrantes/sugeridos y vista de grupos N→1 (lista plegable con totales y diff).
- Considerar aviso de tiempos: carga completa puede tardar ~1–2 minutos; ofrecer feedback (spinner + ETA).

## Consideraciones Backend
- Endpoints disponibles: `/api/reconcile/start`, `/api/reconcile/summary`, `/api/reconcile/details`, `/api/reconcile/details/no-banco`, `/api/reconcile/details/no-contable`, `/api/reconcile/details/pares`, `/api/reconcile/details/n1/grupos`, `/api/reconcile/details/n1/sugeridos`.
- Tolerancias actuales: ventana días configurable (default 5), N→1 aprobados tol estricto = `N1_TOL_APPROVED`, sugeridos tol laxo = `N1_TOL_SUGGESTED`, `max_combo`=6.
- Extracción:
  - Extracto: detecta header con “Fecha”, normaliza montos; ignora filas sin fecha o monto 0.
  - PILAGA: busca fila con “Fecha” + Ingresos/Egresos/Acumulado; monto = ingreso ‑ egreso; descarta 0 y fechas vacías.
- Pipeline marca usados tras pares y grupos N→1 para no duplicar.
- Performance: concatenar 11 meses y contable completo → ~80 s; considerar cacheo de dataframes o preproceso incremental si se hará en producción.
- Duplicados: octubre aparece doble (10 y 10-EXTRACTO completo); hoy se suman ambos. Podría filtrarse por período detectado para evitar doble conteo.

## Riesgos y mejoras recomendadas
- Validar superposición de meses y advertir duplicados antes de conciliar.
- Incluir chequeo de huecos de fechas (gaps) y mostrarlos en UI.
- Optimizar tiempos: usar `pyarrow` si está disponible, o particionar por mes (pipeline por lote) y sumar resultados.
- Añadir logging de métricas (filas, totales, duración) para monitoreo en prod.
- Permitir ventana de días configurable desde UI (ya soportado en backend).
