# Uploads multipart en Litestar (1..N archivos) — Consideraciones y patrones

Este documento resume lo aprendido/decidido para soportar carga de **1 a N archivos** vía `multipart/form-data` usando **Litestar 2.x**, y cómo reflejarlo en la UX (Svelte/Astro).

> Contexto del repo: el flujo actual de conciliación usa `/api/uploads/v2/ingest?role=extracto|contable` y emite un `INGEST_PREVIEW` por SSE.

---

## 1) Lo importante (TL;DR)

- Para “multi upload” el frontend debe enviar **repetido el mismo campo** `file` en el `FormData` (`append`, no `set`).
- En Litestar, `await request.form()` devuelve un `FormMultiDict`, pero **si el parser detecta múltiples archivos**, internamente primero arma un `dict` donde:
  - si hay 1 valor para una key: guarda `value`
  - si hay >1 valores para una key: guarda `list[value]`
- Si en backend usás `form.get("file")`, muchas veces **solo vas a ver 1** (dependiendo de cómo lo transformes/iteres).
- Para leer todos los `file` repetidos, usar una función robusta que pruebe:
  - `form.getall("file")`
  - `form.multi_items()` filtrando por key
  - y otros fallbacks, quedándose con la **lista más larga**
- No confiar en “contar archivos” usando el input (UI) únicamente: siempre confirmarlo con lo que el backend detecta y devuelve (`uploads_count`, `uploads[]`).

---

## 2) Frontend: enviar N archivos en multipart

### 2.1 HTML input

- Para permitir multi-selección: `<input type="file" multiple />`
- En el diálogo de archivos, el usuario debe seleccionar varios (Ctrl/Shift).

### 2.2 FormData correcto

El error típico es usar `fd.set("file", file)` (pisás el anterior). Para multi-file hay que usar `append`:

```ts
const fd = new FormData();
for (const file of Array.from(input.files || [])) {
  fd.append("file", file, file.name);
}
```

Recomendación: al momento de subir, leer `input.files` directo (ref al input) para evitar desfasajes con estado UI.

---

## 3) Backend Litestar: parsear multipart con múltiples `file`

### 3.1 Cómo Litestar parsea multipart

En Litestar 2.x, `Request.form()`:
- Detecta `multipart/form-data` por `Content-Type`
- Llama al parser multipart (`parse_multipart_form`)
- Crea un `FormMultiDict` a partir del resultado

Detalle clave del parser multipart: **colapsa** a `value` cuando hay 1 elemento, o deja `list[value]` si hay >1.

Esto implica que el tipo “subyacente” puede variar, y por eso conviene extraer con APIs de multi-dict (no con `get`).

### 3.2 Obtener todos los archivos del campo `file`

Patrón recomendado: una helper que pruebe diferentes APIs y se quede con la lista más larga.

En este repo quedó implementado en:
- `routes/v1/uploads_v2_concilia.py` (helper `_get_files_from_form`)

Puntos a validar al tocar esto:
- `FormMultiDict` en Litestar tiene `getall()` y `multi_items()`
- En algunos entornos, `items(multi=True)` existe (depende del objeto proxy)

### 3.3 Guardado a disco: streaming

Usar lectura por chunks para no cargar todo en memoria:

- Loop con `await file.read(1024 * 1024)` hasta EOF
- Guardar primero en `/tmp/...`
- Mover luego a `storage/incoming` (o donde corresponda)

**Sugerencia**: sanitizar el nombre original (`Path(name).name`) para evitar path traversal.

---

## 4) Multi-extracto: mantener compatibilidad con pipeline existente

En este repo el pipeline de conciliación espera **un solo URI** de extracto (`uri_extracto`).

Para soportar “N extractos” sin reescribir el pipeline:

1. Aceptar N `file` en `/api/uploads/v2/ingest?role=extracto`
2. Guardar todos en incoming
3. Generar un **consolidado** (ej: `*_extracto_merged.xlsx`)
4. Emitir `INGEST_PREVIEW` usando ese consolidado como `original_uri`

El consolidado actual en este repo:
- Reusa el header del 1er archivo
- Appendea filas de datos (post-header) de cada archivo
- Hoja destino: `principal`

Limitaciones conocidas:
- Solo se consolida a XLSX (no CSV) para evitar casos ambiguos
- Duplicados entre extractos todavía no se deduplican automáticamente (ver “Mejoras”)

---

## 5) Metadata para UX y debugging

Para que la UI muestre claramente qué ocurrió (y para depurar):

En `INGEST_PREVIEW.payload.meta` se recomienda incluir:
- `uploads_count`
- `uploads[]`: por archivo original
  - `filename`
  - `original_uri`
  - `bytes_written`
  - `period_from`, `period_to` (si se detecta por sniff)
  - `bank`, `account_full` (si se detecta)
- `path` (etiqueta del endpoint/handler, ej: `v2`)

La card de Extracto debería mostrar:
- Banco / Cuenta
- Rango consolidado
- Cantidad de archivos (`uploads_count`)
- Lista plegable con archivos y rangos individuales (si hay >1)

Esto evita el escenario “seleccioné 3 pero se procesó 1” sin visibilidad.

---

## 6) Configuración de entorno: “localhost” vs “producción”

Problema recurrente: el frontend puede quedar apuntando a prod por un `URL_REST` hardcodeado, y entonces “parece” que el backend no soporta multi-upload.

Recomendación:
- En dev / localhost: `URL_REST` debe apuntar a `http://localhost:<puerto-backend>`
- En prod: `URL_REST` al dominio real

En este repo se corrigió el selector para que use:
- `import.meta.env.DEV` (estático; no usar `import.meta?.env?.DEV` porque el module runner puede romper)
- o fallback por hostname `localhost/127.0.0.1`

---

## 7) Errores típicos y cómo diagnosticarlos

### “El input muestra 3 archivos, pero el backend recibe 1”

Checklist:
1. Confirmar en DevTools → Network que el POST va al backend correcto (`localhost` vs prod).
2. Confirmar en payload SSE / respuesta JSON que exista `uploads_count`.
3. Revisar backend: ¿se usa `form.get("file")` (mal para multi)?
4. Revisar frontend: ¿se usa `fd.set("file", ...)` en vez de `append`?

### “Se cae el front con import.meta.env”

No usar acceso dinámico u opcional:
- ✅ `import.meta.env.DEV`
- ❌ `import.meta?.env?.DEV`

### “python-multipart faltante”

Si `request.form()` falla, típicamente falta `python-multipart`.
Ver dependencias en `pyproject.toml`.

---

## 8) Mejoras recomendadas (pendientes)

- Detección y advertencia de duplicados por superposición de períodos (ej. “Octubre duplicado”).
- Mostrar “cobertura/gaps” de fechas tras ingestión.
- Consolidación también para CSV (si se decide soportarlo) con un parser unificado.
- Persistir estado de ingestión en DB (en vez de memoria) si el flujo pasa a multi-usuario.

