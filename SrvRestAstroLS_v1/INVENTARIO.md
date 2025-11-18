# Inventario del Proyecto `SrvRestAstroLS_v1`

Última actualización: _(generado automáticamente por Codex)_.

---

## 1. Visión general

- **Stack backend:** Python 3 / [Litestar](https://litestar.dev) (ver `pyproject.toml`).
- **Stack frontend:** Astro + Svelte (carpeta `clientA`).
- **Dominio funcional:** Conciliación bancaria vs. PILAGA (ERP). Se trabaja principalmente con archivos Excel alojados en `storage/incoming`.
- **Estructura macro (nivel 1):** `adapters/`, `clientA/`, `db/`, `routes/`, `services/`, `tests/`, scripts raíz (`ls_iMotorSoft_Srv01.py`, `globalVar.py`, etc.) y utilitarios de import/export.

---

## 2. Backend (Litestar API)

### 2.1 Rutas (`routes/v1`)

| Archivo | Endpoints principales | Descripción |
| --- | --- | --- |
| `reconcile_start.py` | `POST /api/reconcile/start` | Carga extracto y PILAGA desde URIs locales (`file://`), normaliza columnas, ejecuta matching (± ventana de días) y emite resumen + SSE. Expone helpers compartidos (`_load_pilaga`, `_get_extracto_saldos`, etc.). |
| `reconcile_summary.py` | `POST /api/reconcile/summary` | Reutiliza los loaders del flujo principal para devolver métricas completas: movimientos, pares, pendientes, totales Debe/Haber & Ingresos/Egresos, saldos iniciales y finales, diferencia de neto. |
| `reconcile_details.py` | `POST /api/reconcile/details` | Devuelve la lista tabular de “No en Banco / No en PILAGA” (hasta 500 filas) reutilizando el mismo match. |
| `reconcile_quick.py` | `POST /api/reconcile/quick` | Acepta archivos subidos (`bank_file`, `gl_file`), los mueve a `storage/incoming` y usa `services/reconcile/quick_match.py` para responder con matches/sobrantes. |
| `uploads_*` (3 variantes) | `/api/uploads/...` | Manejadores de subida de archivos desde UI legacy y nueva (`uploads_concilia`, `uploads_v2_concilia`, `uploads_ingest`). |
| `ingest_confirm.py` | `/api/ingest/confirm` | Cierre de importaciones para el pipeline. |
| `chat_concilia.py` | `/api/chat/concilia` | Gateway a un flujo conversacional (probable integración IA). |
| `agui_notify.py` | Función `emit()` | Abstracción para enviar eventos SSE/WebSocket a la UI (usado por los reconciliadores). |

### 2.2 Servicios (`services/`)

- `services/reconcile/quick_match.py`: normaliza DataFrames de extractos y PILAGA con heurísticas genéricas y ejecuta una conciliación rápida (monto exacto ± días). Usado por `reconcile_quick`.
- Directorios “vacíos” o con lógica específica pendiente de revisión (`ai/`, `export/`, `normalize/`, `postprocess/`, `reports/`) listos para ampliar el pipeline.
- `services/ingest/sniff_bank.py`: detección de tipo de extracto para ingestas automatizadas.

### 2.3 Adaptadores y base de datos

- `adapters/bank`, `adapters/erp`: conectores de entrada (no se inspeccionó en detalle, presumiblemente drivers para bancos específicos y PILAGA).
- `db/`: modelos SQLAlchemy, repositorios y scripts de inicialización (`db/schema`, `db/models`, `db/repos`). `alembic/` contiene las migraciones.

### 2.4 Scripts raíz

- `ls_iMotorSoft_Srv01.py`: entrypoint principal (monta la app Litestar y configura rutas).
- `globalVar.py`: helper centralizado de rutas de storage (`resolve_storage_uri`, etc.).
- `extract_dates*.py`, `debug_headers.py`, `test_upload*.py`: utilitarios y pruebas manuales de subida/parseo.

---

## 3. Frontend (`clientA/`)

- Proyecto Astro (`astro.config.mjs`) con Svelte para la UI.
- Componentes relevantes (en `clientA/src/components/agui/`):
  - `ReconciliarApp.svelte`: vista principal de conciliación.
  - `ReconciliarResumen.svelte`: muestra el sumario (movimientos, pares, saldos inicial/final, diferencia neta).
  - `ReconciliarDetalle.svelte`: tabla con “no conciliados”.
  - `ConciliaApp.svelte`: shell de navegación.
- Estado global y utilitarios en `clientA/src/components/agui/global.*`.
- Builds empaquetadas mediante `pnpm` (`pnpm-workspace.yaml`, `node_modules/`, etc.).

---

## 4. Pipelines auxiliares

- `services/ingest` + `uploads_*`: flujo de ingesta de archivos (manual o automatizado), escritura en `_uploads/` y `storage/incoming/`.
- `services/ai`, `services/postprocess`, `services/reports`: placeholders para etapas posteriores (ej. enriquecimiento con IA, generación de reportes).

---

## 5. Testing

- `tests/adapters`, `tests/api`, `tests/e2e`, `tests/golden`, `tests/reconcile`: suites separadas por capa.
- Scripts individuales (`test_date.py`, `test_upload.py`, `test_upload_starlette.py`) usados para pruebas específicas de parsing o endpoints.

---

## 6. Recursos y datos

- `_uploads/`: staging de archivos cargados vía API/UI (`Extracto_Ciudad_julio.xlsx`, etc.).
- `storage/incoming/`: carpeta externa (referenciada por URIs `file://`) donde se ubican los Excel originales de cada conciliación.
- `graph/`, `temp1.txt`, `ziwVCTVP/`: carpetas auxiliares (probablemente artefactos temporales o pruebas).

---

## 7. Estado actual de conciliaciones

- Se han probado y documentado dos pares de archivos:
  1. **Santander Ago-Sep 2025** (`EXTRACTO SANTANDER AGOST-SEPT.xlsx` vs. `PILAGA SANTANDER AGOST -SEPT.xlsx`).
  2. **Banco Ciudad Julio 2025** (`Extracto Ciudad julio.xlsx` vs. `PILAGA CIUDAD JULIO.xlsx`).
- El backend actual expone:
  - Movimientos totales, pares conciliados y pendientes.
  - Totales Debe/Haber e Ingresos/Egresos alineados con los Excel.
  - Saldos iniciales y finales por origen.
  - Diferencia de neto (Banco − PILAGA).
- La UI muestra además los saldos inicial/final y permite descargar el detalle de no conciliados.

---

## 8. Próximos pasos sugeridos

1. Automatizar validaciones de saldos finales en los tests (comparar `saldo_inicial + neto` contra `saldo_final` cuando exista en el Excel).
2. Extender los servicios “vacíos” (`ai`, `reports`, etc.) con documentación o ejemplos mínimos para saber su propósito.
3. Agregar snapshots de ejemplo a `tests/golden` para cada tipo de extracto soportado (Santander, Ciudad, Patagonia, etc.).

---

> **Nota:** Este inventario se basa en la estructura actual del repositorio (`tree -L 2`) y en la lectura de los archivos clave modificados durante esta sesión. Actualizar cuando se sumen nuevos módulos o pipelines.

---

## 9. Análisis guardado (persistencia & coincidencias)

- **Pruebas actuales:** Santander y Patagonia con más de 60 días de ventana y ~1300 filas cada uno; sin fallas en loaders ni matching.
- **Requerimiento del cliente:** además del resumen, debe poder verse la lista completa de registros coincidentes (no sólo los no conciliados).
- **Estado backend:** `services/reconcile/quick_match.py` ya genera `matched`, pero recorta a 200 filas antes de enviar por `/api/reconcile/quick`; no hay persistencia en BD todavía.
- **Qué falta para el próximo paso:**
  - Quitar o parametrizar el límite de 200 filas y/o crear endpoint paginado para coincidencias.
  - Actualizar la UI (`clientA`) para renderizar la tabla de pares conciliados consumiendo `result.matched`.
  - Diseñar las tablas `reconciliation_run` + `reconciliation_match` (y opcionalmente `reconciliation_item`) para guardar run summaries, coincidencias y pendientes en Postgres.
  - Registrar metadatos clave al persistir: usuario, cuenta/periodo, `bank_uri`, `gl_uri`, tolerancia de días, totales por fuente, saldos inicial/final y trazabilidad de archivos.

---

## 10. Cambios recientes (Concilia $5.040.000)

- `routes/v1/reconcile_start.py`: el matcher `_match_one_to_one_by_amount_and_date_window` dejó de usar `drop_duplicates` sobre `_row_id_*` y ahora aplica un recorrido greedy que asegura la relación 1:1 incluso con montos duplicados (evita que dos PILAGA apunten al mismo banco cuando las fechas están dentro de la ventana).
- `tests/reconcile/test_matcher.py`: nuevo test de regresión que arma un escenario mínimo con dos movimientos de $5.040.000 por lado y verifica que retorna dos pares y cero sobrantes, cubriendo el bug detectado en los extractos reales.

---

## 11. Cambios UI recientes (chat + conciliación)

- `clientA/src/components/agui/ReconciliarApp.svelte`: accesos rápidos “Subir extracto / Subir contable” junto al chat, botón de upload con spinner mientras sube y cierre automático del modal; descomposición muestra spinner hasta que hay datos.
- `clientA/src/components/agui/ReconciliarResumen.svelte`: separó el sumario en dos fetch (head y descomposición) con timers visibles en botón “Actualizar” y en la sección de descomposición.
- `clientA/src/components/agui/cards/*`: todas las cards de detalle ahora sólo calculan al presionar “Calcular” y muestran cronómetro mientras cargan (NoBanco, NoContable, Conciliados 1→1, Agrupados, Sugeridos).
