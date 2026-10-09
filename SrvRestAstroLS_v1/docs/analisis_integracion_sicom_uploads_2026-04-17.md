# Analisis de integracion de SICOM en flujo de uploads

Fecha: 2026-04-17
Proyecto: `SrvRestAstroLS_v1`

## 1. Objetivo

Revisar el estado actual del flujo de uploads y conciliacion para determinar como incorporar `SICOM` como tercer insumo, manteniendo el criterio funcional:

- la conciliacion principal sigue siendo `contable (PILAGA) vs extracto bancario`;
- `SICOM` actua como apoyo funcional;
- el caso de uso esperado para `SICOM` es un archivo mensual con multiples solapas internas, normalmente una por dia.

## 2. Estado actual del sistema

### 2.1 Roles soportados hoy

El sistema esta cerrado actualmente a dos roles:

- `extracto`
- `contable`

Esto aparece en varios puntos:

- `routes/v1/chat_concilia.py`
- `routes/v1/uploads_v2_concilia.py`
- `routes/v1/ingest_confirm.py`
- `clientA/src/components/agui/ReconciliarApp.svelte`
- `routes/v1/reconcile_start.py`
- `routes/v1/reconcile_summary.py`
- `routes/v1/reconcile_details.py`

### 2.2 Contrato actual de conciliacion

El contrato backend actual de conciliacion recibe solo:

- `uri_extracto`
- `uri_contable`
- `days_window`

No existe hoy `uri_sicom`.

Esto significa que el pipeline de conciliacion esta modelado estrictamente para dos fuentes.

## 3. Estado real del multi-upload

### 3.1 Capacidad tecnica general

El frontend ya envia multiples archivos porque:

- el input usa `multiple`;
- se hace `fd.append("file", file, file.name)` para cada archivo.

El backend tambien puede leer multiples ocurrencias del campo `file` porque:

- `_get_files_from_form()` contempla `getlist`, `getall`, `multi_items` y otros fallbacks.

### 3.2 Extracto: soporte 1..N real

Para `extracto`, el soporte `1..N` esta implementado de punta a punta:

- se hace sniff por archivo individual;
- se calculan rangos, cobertura y solapamientos;
- si hay varios archivos, se fusionan en un XLSX consolidado;
- el preview muestra `uploads_count`, detalle por archivo y cobertura;
- en `ingest_confirm`, `extracto` se guarda como lista de `items`;
- si hay varios canónicos, se genera `manifest_uri`.

Conclusión:

- `extracto` si tiene hoy un flujo `1..N` real y usable.

### 3.3 Contable: soporte 1..N parcial

Aunque el input permite seleccionar varios archivos para cualquier rol, `contable` no tiene hoy un tratamiento `1..N` equivalente al de `extracto`.

En la práctica:

- puede subirse mas de un archivo;
- pero el flujo de preview y confirmacion termina trabajando como si el contable fuera una sola unidad;
- en `uploads_v2_concilia.py`, fuera del caso especial de `extracto`, se usa el primer archivo efectivo como `original_uri` de compatibilidad;
- en `ingest_confirm.py`, `contable` se guarda como un unico objeto, no como lista de items.

Conclusión:

- el sistema hoy no resuelve realmente `contable 1..N` end-to-end, aunque tecnicamente permita subir varios archivos.

## 4. Donde SICOM no entra hoy

`SICOM` no esta contemplado en ningun punto funcional del flujo actual:

- no hay intent en chat para `subir sicom`;
- no hay `role=sicom`;
- no hay sniff de tipo SICOM;
- no hay preview especifico;
- no hay confirmacion ni canonicalizacion de SICOM;
- no hay `uri_sicom` en los endpoints de conciliacion;
- no hay estado UI para una tercera fuente.

## 5. Diferencia conceptual entre Extracto y SICOM

No conviene modelar `SICOM` igual que `extracto`.

### 5.1 Extracto

El problema del extracto es:

- multiples archivos fisicos;
- misma estructura general;
- necesidad de fusionarlos en un unico dataset.

### 5.2 SICOM

El problema de SICOM, segun el caso actual, es distinto:

- normalmente llega como un archivo mensual unico;
- internamente contiene multiples solapas;
- cada solapa representa un subconjunto temporal, tipicamente diario;
- la logica de consolidacion vive dentro del workbook, no entre varios archivos separados.

Conclusión:

- `SICOM` debe modelarse como `1 archivo mensual -> N solapas internas -> 1 dataset canónico`.
- su complejidad principal debe vivir en el parser/canonicalizador, no en la fusion de multiples archivos subidos.

## 6. Impacto tecnico por capa

### 6.1 Chat / disparador de upload

Hoy el chat solo entiende:

- `subir extracto`
- `subir contable`

Para SICOM haria falta agregar:

- nuevo intent `subir sicom`
- nuevo formulario apuntando a `/api/uploads/v2/ingest?role=sicom`

### 6.2 Upload backend

Hoy `uploads_v2_concilia.py` valida:

- `extracto`
- `contable`

Para SICOM haria falta:

- ampliar `role` permitido a `sicom`;
- definir sniff o detector propio;
- leer workbook mensual y detectar hojas utiles;
- construir preview con metadatos funcionales.

Preview recomendado para `sicom`:

- `sheet_count`
- `sheet_names`
- `period_from`
- `period_to`
- `banks`
- `rows`
- `required_columns_ok`
- posiblemente totales de `importe` e `imp_neto`

### 6.3 Canonicalizacion

Hoy `_build_canonical_parquet()` solo sabe convertir:

- `extracto` usando `_load_extracto`
- `contable` usando `_load_pilaga`

Para `sicom` haria falta:

- nuevo loader normalizador;
- salida canónica unica, idealmente parquet;
- columnas recomendadas:
  - `fecha_pago`
  - `order_de_p`
  - `nro_pago`
  - `banco`
  - `importe`
  - `imp_neto`
  - `organismo`
  - `convenio`
  - `sheet_name`

### 6.4 Confirmacion / estado

Hoy `_CONFIRMS` solo contempla:

- `extracto`
- `contable`

Para SICOM haria falta:

- ampliar el estado a `sicom`;
- permitir `INGEST_CANONICAL_READY` para `sicom`;
- extender `READY_TO_RECONCILE` para incluir `files.sicom`.

### 6.5 Frontend

Hoy la UI mantiene solo:

- `previewExtracto`
- `previewContable`

Para SICOM haria falta:

- tercer estado `previewSicom`;
- soporte de `role === "sicom"` en `INGEST_PREVIEW`;
- soporte de `role === "sicom"` en `INGEST_CANONICAL_READY`;
- tercera card de preview / confirmacion;
- boton `Subir SICOM`.

### 6.6 Contrato de conciliacion

Los endpoints hoy estan cerrados a:

- `uri_extracto`
- `uri_contable`

Para integrar SICOM sin romper compatibilidad, la extension correcta seria:

- agregar `uri_sicom` opcional

Esto aplica a:

- `reconcile_start`
- `reconcile_summary`
- `reconcile_details`
- wizard y cualquier otro flujo derivado

## 7. Recomendacion funcional

La integracion correcta de SICOM no debe reemplazar el modelo actual de conciliacion.

El diseño recomendado es:

1. Mantener `extracto` y `contable` como fuentes principales.
2. Incorporar `sicom` como fuente auxiliar opcional.
3. Canonicalizar `sicom` como dataset mensual consolidado internamente por solapas.
4. Consumir `uri_sicom` como soporte para:
   - reconstruccion de lotes;
   - trazabilidad por `Nº Pago`;
   - trazabilidad por `Order de P.`;
   - explicacion de match `N a 1` o mixtos.

## 8. Conclusiones

1. El proyecto hoy esta pensado funcionalmente para dos fuentes, no tres.
2. El multi-upload real y completo existe hoy solo para `extracto`.
3. `contable` no tiene aun un soporte `1..N` equivalente end-to-end.
4. `SICOM` no deberia copiar el patron de extracto, porque su problema principal no es multiarchivo sino multisolapa interna.
5. La forma correcta de incorporar `SICOM` es como un nuevo rol con parser/canonicalizador propio y `uri_sicom` opcional en el contrato de conciliacion.
6. Si se implementa, conviene resolver explicitamente si tambien se va a robustecer `contable 1..N` en la misma pasada o si se deja como limitacion conocida.

## 9. Proximo paso recomendado

Antes de tocar codigo de negocio, conviene definir una especificacion tecnica corta con:

- archivos a modificar;
- nuevo contrato SSE/preview para `sicom`;
- formato canónico de SICOM;
- cambios minimos de UI;
- y como `uri_sicom` entra en el pipeline sin romper compatibilidad.
