# Status — subida de extractos (múltiples) y validaciones

Fecha: 2025-12-18  
Rama: `multiples-extractos`

Este documento resume el estado actual del desarrollo relacionado a la **subida de extractos bancarios (1..N archivos)**, su **vista previa**, validaciones y señales para UX.

---

## Objetivo alcanzado

- Permitir en UX cargar **1..N archivos de extracto** sin cambiar el layout general.
- Mantener el backend **compatible** con el mismo endpoint.
- Consolidar multi-extracto para no romper el pipeline actual (que consume 1 `uri_extracto`).
- Mejorar visibilidad en la card: cantidad de archivos, rangos por archivo, días con movimientos, cobertura (meses faltantes/gaps/meses parciales), y solapamientos.

---

## UX (Reconciliar)

Archivo: `clientA/src/components/agui/ReconciliarApp.svelte`

- Input de archivo:
  - `multiple` habilitado.
  - El submit arma `FormData` repitiendo el campo `file` con `append` (multi-file real).
  - Para evitar desfasajes, se toma `input.files` directo al submit.

- Card “Vista previa — Extracto”:
  - Muestra: `Banco`, `Cuenta`, `Archivos`, `Rango`, `Header`.
  - Muestra “Archivo subido” cuando `uploads_count == 1`.
  - Muestra “Ver archivos (N)” cuando `uploads_count > 1`, ordenado por `period_from` (cronológico).
  - Por archivo: `nombre (from a to, días: X)` donde `días` = días distintos con movimientos (fechas distintas en `FECHA`).
  - Warnings “Cobertura incompleta” (warn-only):
    - `Solapamiento de fechas entre archivos: X día(s)` (por días con movimientos, no por rango).
    - `Meses faltantes` (por meses).
    - `Gaps detectados (por meses)` (por meses faltantes consecutivos).
    - `Meses parciales (por días con movimientos)` (faltantes internos del mes, con rangos faltantes acotados).

- Integración canónico Parquet:
  - Escucha SSE `INGEST_CANONICAL_READY` y guarda `canonical_uri`.
  - Al iniciar reconcile usa `canonical_uri` si existe, fallback a `original_uri`.

---

## Backend: Upload multi-extracto

Archivo: `routes/v1/uploads_v2_concilia.py`

- Endpoint: `/api/uploads/v2/ingest?role=extracto|contable`

### Parsing de multipart (múltiples `file`)
- Se robusteció la lectura de múltiples archivos del form, probando APIs típicas de `FormMultiDict` (Litestar).
- Resultado: el backend ya no “pierde” archivos por leer solo `form.get("file")`.

### Guardado y preview
- Guarda cada archivo en storage/incoming.
- Para extracto:
  - Ejecuta `sniff_file()` por archivo (para rango/banco/cuenta/header por archivo).
  - Calcula `days_present` por archivo (días con movimientos).
- Para `uploads_count > 1`:
  - Genera un XLSX consolidado `*_extracto_merged.xlsx` para mantener el pipeline intacto.
  - Completa `detected`/`suggest` por consenso usando los uploads individuales (banco/cuenta/header/rango).
  - Agrega `meta.uploads[]` con `filename`, `original_uri`, `period_from/to`, `days_present`, etc.

### Cobertura / gaps / parciales (warn-only)
- `missing_months` y `gaps` se calculan “por meses”.
- `partial_months` se calcula por “días presentes” en filas (no por rango min/max), reportando rangos faltantes internos.
- Para reducir ruido:
  - `partial_months` solo se reporta cuando faltan al menos 2 días (`partial_min_missing_days = 2`).
  - Se usa un umbral para considerar un mes “presente” por días (para evitar que un solo día arrastrado cree un “mes parcial” confuso).

### Solapamiento (warn-only, preciso)
- Solapamiento se calcula por **días con movimientos** (intersección de fechas presentes entre archivos), no por rangos `period_from/to`.
- Esto evita falsos positivos donde un archivo trae 1 fila de otro mes y el rango parece solaparse completo.

---

## Backend: canónico Parquet (Opción A)

Archivos:
- `routes/v1/ingest_confirm.py`
- `routes/v1/reconcile_start.py`

- Al confirmar (extracto/contable), se dispara en background:
  - generación de un `.parquet` canónico en `storage/canonical`.
  - emisión SSE: `INGEST_CANONICAL_READY { role, canonical_uri }`.
- El reconcile puede cargar `.parquet` en `_load_extracto()` y `_load_pilaga()`.

Notas:
- El canónico busca mejorar performance (evitar reparsear XLSX cada corrida).
- El XLSX merge se mantiene como compatibilidad/preview.

---

## Decisiones tomadas

- Duplicados/operaciones pisadas (overlap) se manejan como **warning-only** (sin deduplicar/alterar data).
- Cobertura por días: se asume “día faltante” = “no hay movimientos ese día” (esto es intencional para detectar “mes con 15 días cargados”).

---

## Pendientes / próximos pasos sugeridos

- (Opcional) Exponer ejemplos de días solapados (lista corta) si el usuario lo pide.
- (Opcional) Ajustar umbrales (`min_days_present`, `partial_min_missing_days`) a valores configurables por UI o perfil.
- (Opcional) Reglas para detectar “archivos duplicados” (mismo mes subido dos veces) y avisar.
- (Opcional) Persistir reportes de ingest/cobertura en storage o DB para auditoría.

