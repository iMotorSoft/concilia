# Especificacion tecnica corta para integrar SICOM con bank/account scope

Fecha: 2026-04-19
Proyecto: `SrvRestAstroLS_v1`
Base funcional:

- [analisis_integracion_sicom_uploads_2026-04-17.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/analisis_integracion_sicom_uploads_2026-04-17.md)
- [analisis_sicom_noviembre_bank_scope_2026-04-19.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/analisis_sicom_noviembre_bank_scope_2026-04-19.md)

## 1. Objetivo

Incorporar `SICOM` al flujo de uploads y conciliacion sin romper compatibilidad con el modelo actual `extracto vs contable`, agregando dos conceptos que pasan a ser obligatorios en el diseño:

- `bank_scope/account_scope`
- relacion operativa `OP <-> Nro Pago`

## 2. Regla funcional que debe respetar el codigo

1. La conciliacion principal sigue siendo `contable (PILAGA) vs extracto bancario`.
2. `SICOM` es una fuente auxiliar opcional.
3. `SICOM` mensual puede mezclar bancos.
4. El `extracto` define el `account_scope` efectivo del caso.
5. Antes de usar `SICOM`, hay que filtrarlo al banco compatible con ese `account_scope`.
6. La validacion manual debe poder navegar por `OP`, porque ese es el identificador que usan las personas.
7. `Nro Pago` se usa para explicar el lote bancario, no para reemplazar `OP`.

## 3. Modelo de datos minimo

### 3.1 Campos nuevos por fuente

`extracto`

- `bank_name`
- `account_number_raw`
- `account_scope`
- `period_from_detected`
- `period_to_detected`

`contable`

- `bank_name_hint`
- `account_scope`
- `period_from_detected`
- `period_to_detected`

`sicom`

- `bank_names_available`
- `bank_count`
- `period_from_detected`
- `period_to_detected`
- `sheet_count`
- `sheet_names`

### 3.2 Definicion de `account_scope`

`account_scope` debe ser un identificador normalizado y comparable entre fuentes.

Regla inicial recomendada:

- conservar `account_number_raw` tal como vino en el archivo;
- derivar `account_scope` por normalizacion liviana;
- no confiar en string literal del archivo para comparar.

Normalizacion minima:

- uppercase
- trim
- remover prefijos cosmeticos como `CC $`
- conservar solo digitos y separadores relevantes
- derivar un `account_scope_digits` con solo digitos

Ejemplo:

- `CC $ 100-393300535-000` -> `account_scope_digits=100393300535000`
- `393300/5-CTA.CTE PAT` no coincide literal, pero debe poder mapearse a la misma familia funcional de cuenta mediante regla o tabla de equivalencias.

### 3.3 Mapeo banco/cuenta para SICOM

`SICOM` no trae numero de cuenta. Solo trae `Banco`.

Por lo tanto hace falta una capa de resolucion:

- `extracto/account_scope` -> `bank_scope`
- `contable/account_scope` -> `bank_scope`
- `SICOM.banco` -> `bank_scope`

Regla inicial minima:

- `Banco Patagonia` -> `bank_scope=patagonia`
- `Banco Pat.Otros` -> `bank_scope=patagonia_otros`
- `Banco Santander` -> `bank_scope=santander`
- `Banco Sant.Otros` -> `bank_scope=santander_otros`
- `Banco Ciudad` o equivalentes -> `bank_scope=ciudad`

Importante:

- regla superada por decision del `2026-04-30`: para el caso funcional `patagonia`, `Banco Pat.Otros` debe considerarse dentro del universo Patagonia;
- el filtro SICOM implementado debe resolver `patagonia -> {banco_patagonia, banco_pat_otros}`;
- el cierre efectivo no debe inflarse por scope: aunque `Pat.Otros` entre al universo Patagonia, solo se considera cerrado contra extracto si matchea por `fecha + importe`;
- la validacion de Base 03/11, noviembre mensual y marzo 2026 mostro que sumar `Pat.Otros` mejora `PILAGA -> SICOM`, pero no cambia `SICOM -> extracto` ni `final_reconciliation`.

## 4. Formato canonico recomendado para SICOM

El dataset canonico de `SICOM` debe incluir, como minimo:

- `fecha_pago`
- `order_de_p`
- `nro_pago`
- `banco_raw`
- `bank_scope`
- `importe`
- `imp_neto`
- `organismo`
- `convenio`
- `medio_pago`
- `sheet_name`
- `source_file_name`

Campos derivados recomendados:

- `op_key`
- `lote_key = fecha_pago + bank_scope + nro_pago`
- `op_lote_key = fecha_pago + order_de_p + bank_scope + nro_pago`

## 5. Contrato de preview / ingest

### 5.1 Nuevo role

Agregar `role=sicom` en:

- [chat_concilia.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/chat_concilia.py)
- [uploads_v2_concilia.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/uploads_v2_concilia.py)
- [ingest_confirm.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/ingest_confirm.py)
- [ReconciliarApp.svelte](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/clientA/src/components/agui/ReconciliarApp.svelte)

### 5.2 Preview SSE recomendado para `sicom`

Evento `INGEST_PREVIEW` para `role=sicom`:

```json
{
  "role": "sicom",
  "preview": {
    "rows": 507,
    "sheet_count": 17,
    "sheet_names": ["Hoja2", "Hoja3"],
    "period_from": "2025-11-03",
    "period_to": "2025-11-28",
    "required_columns_ok": true,
    "banks": [
      {"bank_raw": "Banco Patagonia", "rows": 404, "imp_neto_total": 1926640400.48},
      {"bank_raw": "Banco Pat.Otros", "rows": 80, "imp_neto_total": 93928093.00}
    ],
    "op_count": 287,
    "nro_pago_count": 79,
    "relation_summary": {
      "op_multi_nro_pago_count": 4,
      "nro_pago_multi_op_count": 8
    }
  }
}
```

Notas:

- los valores numericos del ejemplo son ilustrativos del caso analizado y no forman parte fija del contrato;
- `op_count`, `nro_pago_count` y resumen de cardinalidad ayudan a explicar el comportamiento operacional desde el preview.
- Si el calculo de cardinalidad encarece demasiado el preview, puede dejarse para confirmacion.

### 5.3 Confirmacion

En `INGEST_CANONICAL_READY` para `sicom` devolver:

- `canonical_uri`
- `bank_names_available`
- `bank_count`
- `period_from_detected`
- `period_to_detected`
- `sheet_count`

Persistencia minima en estado:

```json
{
  "files": {
    "sicom": {
      "original_uri": "...",
      "canonical_uri": "...",
      "bank_names_available": ["Banco Patagonia", "Banco Pat.Otros", "Banco Santander"],
      "sheet_count": 17,
      "period_from_detected": "2025-11-03",
      "period_to_detected": "2025-11-28"
    }
  }
}
```

## 6. Contrato de conciliacion

Extender sin romper compatibilidad:

- `uri_extracto`
- `uri_contable`
- `uri_sicom` opcional
- `bank_scope` opcional pero recomendado
- `account_scope` opcional pero recomendado
- `days_window`

Aplica a:

- [reconcile_start.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_start.py)
- [reconcile_summary.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_summary.py)
- [reconcile_details.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_details.py)
- [reconcile_wizard_start.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_wizard_start.py)

Regla de resolucion:

1. Si viene `account_scope`, usarlo como fuente de verdad.
2. Si no viene, inferirlo desde `extracto`.
3. Derivar `bank_scope`.
4. Filtrar `SICOM` al `bank_scope` objetivo antes de cualquier analisis de lotes.

## 7. Logica de matching recomendada

### 7.1 `SICOM -> extracto`

Nivel de lote:

- `fecha_pago`
- `bank_scope`
- `nro_pago`
- `imp_neto`

Comparar contra lineas del extracto relevantes para debitos de sueldos/acreditaciones.

### 7.2 `PILAGA -> SICOM`

Nivel operativo:

- `OP / order_de_p`
- `importe`
- tolerancia de desfase de fecha

Regla minima:

- usar `Doc. Principal` normalizado a `OP`
- no usar `Doc. Cobro / Id Pago` como equivalente de `nro_pago`

### 7.3 `PILAGA -> extracto`

Solo para matches univocos:

- misma fecha o ventana corta
- mismo importe
- y sin contradiccion con la explicacion por lote

## 8. UI minima

En [ReconciliarApp.svelte](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/clientA/src/components/agui/ReconciliarApp.svelte):

- agregar `previewSicom`
- soportar `role === "sicom"` en preview y confirmacion
- agregar boton `Subir SICOM`
- mostrar chips o lista de bancos detectados
- mostrar rango detectado real

En resumen/detalle:

- exponer `bank_scope` del caso
- permitir ver si `SICOM` fue usado o no
- permitir navegacion por `OP`
- mostrar para cada `OP`:
  - `uno o varios nro_pago`
  - banco
  - importe / imp_neto
  - fecha de pago

## 9. Cambios minimos por archivo

Backend:

- [routes/v1/chat_concilia.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/chat_concilia.py)
- [routes/v1/uploads_v2_concilia.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/uploads_v2_concilia.py)
- [routes/v1/ingest_confirm.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/ingest_confirm.py)
- [routes/v1/reconcile_start.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_start.py)
- [routes/v1/reconcile_summary.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_summary.py)
- [routes/v1/reconcile_details.py](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/routes/v1/reconcile_details.py)

Frontend:

- [clientA/src/components/agui/ReconciliarApp.svelte](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/clientA/src/components/agui/ReconciliarApp.svelte)
- [clientA/src/components/agui/reconcileConfig.ts](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/clientA/src/components/agui/reconcileConfig.ts)
- opcionalmente resumen/detalle si se muestra soporte SICOM

## 10. Orden recomendado de implementacion

Fase 1:

- aceptar `role=sicom`
- generar preview
- canonicalizar `SICOM`
- persistir `files.sicom`

Fase 2:

- introducir `bank_scope/account_scope`
- filtrar `SICOM` por banco objetivo
- extender contrato de conciliacion con `uri_sicom`

Fase 3:

- agregar explicaciones por `OP <-> nro_pago`
- exponer trazabilidad en summary/details

## 11. Decision explicita pendiente

Antes de implementar conviene fijar una decision de producto:

- si `Banco Pat.Otros` debe tratarse como banco excluido del flujo Patagonia
- o como subcanal del mismo circuito con reglas separadas

Con la evidencia actual, la opcion segura para MVP es:

- usar solo `Banco Patagonia` para el extracto Patagonia analizado
- y dejar `Pat.Otros` como universo visible pero no conciliado automaticamente
