# Matching N→1 (Propuesta)

## 1. Objetivo

Extender el flujo de conciliación para cubrir movimientos bancarios que representan la suma de varios asientos PILAGA (N movimientos contables contra 1 del banco), manteniendo una trazabilidad clara de los componentes antes de marcarlos como conciliados.

## 2. Casos de prueba usados

| Dataset | Extracto | PILAGA | Rango fechas | Resultados 1→1 | Sobrantes Banco | Sobrantes PILAGA |
| --- | --- | --- | --- | --- | --- | --- |
| Santander Septiembre | `09 - EXTRACTO.xlsx` | `09 - PILAGA.xlsx` | 2025-09 | 25 pares | 2 | 1 |
| Santander Ago-Sep (ventana 10d) | `EXTRACTO SANTANDER AGOST-SEPT.xlsx` | `PILAGA SANTANDER AGOST -SEPT.xlsx` | 2025-08/09 | 449 pares | 671 | 922 |
| Santander Ago-Sep (ventana 30d) | `EXTRACTO SANTANDER AGOST-SEPT.xlsx` | `PILAGA SANTANDER AGOST -SEPT.xlsx` | 2025-08/09 | 470 pares | 650 | 901 |
| Patagonia Ago-Sep | `EXTRACTO PATAGONIA AGOST-SEPT.xlsx` | `PILAGA PATAGONIA AGOST-SEPT.xlsx` | 2025-08/09 | 106 pares | 284 | 1.660 |

En el set “Santander Septiembre” los dos sobrantes del banco son egresos pequeños que no combinan con otros movimientos; en “Santander Ago-Sep” aparece un volumen mayor con débitos/créditos agrupados que motivan el análisis N→1 (la ventana de días tiene impacto directo en la cantidad de matches sugeridos); en Patagonia predominan las transferencias masivas que agrupan 2–5 pagos PILAGA.

## 3. Heurística explorada

1. Ejecutar el matcher actual (1→1 por monto y ventana de días).
2. Tomar los movimientos bancarios que siguen sin conciliar.
3. Para cada uno, construir el conjunto de candidatos PILAGA:
   - Igual signo (ambos débitos o créditos).
   - `|fecha_p - fecha_b| <= ventana` (default 5 días).
   - `|monto_p| <= |monto_b| + tolerancia`.
4. Ordenar candidatos por monto absoluto descendente (prioriza los más “grandes”) y limitar la lista a `cand_limit` (18–24) para evitar explosión combinatoria.
5. Ejecutar una búsqueda combinatoria controlada (DFS greedy) que arma combinaciones de 2 hasta `max_combo` elementos (probamos hasta 6) acumulando la suma absoluta y cortando cuando supera el monto objetivo.
6. Aceptar la combinación si `|sum(componentes) - monto_b| <= tol` (tol probada: $1).
7. Registrar el match como “N→1 sugerido” sin remover todavía las filas de los sobrantes; la confirmación debería ser manual o en una segunda pasada.

## 4. Resultados obtenidos con la heurística

| Dataset | Ventana | N→1 detectados | 2→1 | 3→1 | 4→1 | 5→1 | 6→1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Santander Sept | 5 días | 0 | 0 | 0 | 0 | 0 | 0 |
| Santander Ago-Sep | 10 días | 39 | 17 | 5 | 7 | 9 | 1 |
| Santander Ago-Sep | 30 días | 33 | 10 | 7 | 5 | 2 | 9 |
| Patagonia Ago-Sep | 5 días | 24 | 11 | 7 | 4 | 2 | 0 |

Ejemplos confirmados en Patagonia:

- `Banco 04/08, -$10.000.000` = OP:4717/2025 (-6M) + OP:4822/2025 (-4M).
- `Banco 04/08, -$75.000.000` = OP:4667/2025 (-25.45M) + OP:4666/2025 (-25.25M) + OP:4662/2025 (-24.30M).
- `Banco 02/09, -$40.320.000` = OP:6792/2025 (-22.04M) + OP:6423/2025 (-7.58M) + OP:6370/2025 (-4M) + OP:6409/2025 (-4M) + OP:6321/2025 (-2.7M).

Ejemplos adicionales de Santander Ago-Sep con ventana de 10 días:

- `Banco 01/09, doc 4149405, -$47.688.524,27` = `OPNP: 204/2025` (-$46.286.377,77) + un asiento agrupado con 11 OPs (`6156/2025`, `6245/2025`, ..., `6804/2025`) que suman -$1.402.146,50.
- `Banco 05/08, doc 50000, -$6.112.516,95` = OP:5597/2025 (-1.260.000) + OP:5594/2025 (-1.260.000) + OP:5595/2025 (-1.240.516,95) + OP:5596/2025 (-1.232.000) + OP:5605/2025 (-1.120.000).

Con ventana de 30 días aparecen combinaciones más extensas (hasta 6 PILAGA) que siguen sumando de forma exacta, por ejemplo:

- `Banco 29/09, doc 66542719, -$23.900.000` = OP:7265/2025 (-8.000.000) + OP:7266/2025 (-7.000.000) + OP:7268/2025 (-5.000.000) + OP:7584/2025 (-3.900.000).

## 5. Parámetros recomendados (iniciales)

| Parámetro | Valor sugerido | Notas |
| --- | --- | --- |
| `days_window` | 5–30 | 5 días como base (coincide con el matcher actual); se puede ampliar a 10 o 30 para cuentas con transferencias agrupadas (Santander Ago-Sep), siempre acompañando con reglas de confianza para evitar falsos positivos. |
| `max_combo` | 5 (hasta 6) | Evita combinaciones con más de 5-6 PILAGA para mantener tiempos de cómputo razonables. |
| `cand_limit` | 20 | Cantidad máxima de candidatos PILAGA por búsqueda. |
| `tol_amount` | $1 | Diferencia tolerada al comparar la suma con el monto del extracto. |

## 5.1 Clasificación propuesta de resultados

Para aplicar ventanas amplias sin perder control se propone separar cuatro conjuntos:

1. **Exactos 1→1**: matches tradicionales mono-movimiento; se consideran conciliados automáticos.
2. **Agrupados aprobados (N→1)**: combinaciones multi-movimiento con reglas fuertes (suma exacta, ventana dentro de lo permitido, referencias coincidentes). También se marcan como conciliados automáticos.
3. **Sugeridos (N→1 por revisar)**: coincidencias numéricas válidas pero con menor confianza (fechas alejadas, N grande, documentos heterogéneos). Se devuelven aparte para que el usuario los apruebe o rechace antes de restarlos de los “sobrantes”.
4. **No conciliados**: movimientos que no entran en ninguna de las categorías anteriores (siguen apareciendo como “No en Banco / No en PILAGA” hasta que exista un match o se cierre manualmente).

### Presentación sugerida en el header (UI)

Para reemplazar los contadores genéricos “No en Banco / No en PILAGA” se sugiere mostrar los cuatro totales principales:

- `Exactos 1→1: <cantidad>`
- `Agrupados aprobados: <cantidad>`
- `Sugeridos N→1: <cantidad>`
- `No conciliados: PILAGA <cantidad> • Banco <cantidad>`

De esta forma el usuario obtiene un panorama completo de la conciliación y puede navegar a cada grupo desde el encabezado.

## 6. Plan para incorporar al backend

1. **Refactor matcher actual** para que retorne tanto los pares 1→1 como los sobrantes con identificadores `_row_id_*`.
2. **Agregar módulo `n_to_1_matcher.py`** con la heurística: recibe los sobrantes, parámetros y devuelve una lista de coincidencias + los índices usados.
3. **Actualizar `reconcile_start`** para ejecutar esa segunda pasada (condicionada por un flag o configuración) y agregar la salida a la respuesta JSON (`suggested_combinations`).
4. **Persistencia opcional**: guardar cada match compuesto en BD con estructura `match_group_id`, `bank_row_id`, `pilaga_row_ids[]`, métricas y estado (`suggested`, `approved`).
5. **Tests**: añadir casos sintéticos para 2→1, 3→1 y 5→1 asegurando que:
   - La suma respeta la tolerancia.
   - Se respeta la ventana de días.
   - No se reusan movimientos PILAGA en dos combos distintos (bloqueo via `used_row_ids`).

## 7. Pendientes / preguntas

- ¿El usuario confirmará manualmente cada combinación antes de quitarla de “sobrantes”? (definir UI y API de confirmación).
- ¿Se necesita detectar también 1→N (un PILAGA cubre varias entradas del banco)?
- ¿Se debe generar un Excel/pdf de auditoría con el detalle de combos sugeridos?
- ¿Los parámetros (`max_combo`, `tol_amount`, `cand_limit`) deben ser configurables por cuenta/cliente o basta con valores globales?

Este documento sirve como punto de partida para implementar la lógica y coordinar los cambios necesarios en el backend, tests y UI.

## 8. Estado de implementación (abril 2025)

- **Ventana estándar 5 días**: la UI (Astro/Svelte) ya usa un store compartido (`DEFAULT_DAYS_WINDOW = 5`) que sincroniza el valor enviado a `/api/reconcile/start`, `/api/reconcile/summary` y todos los endpoints de detalles.
- **Cards por área (fase 1)**: `NoBancoCard.svelte` muestra el total de PILAGA no reflejado en banco (`n op` + monto acumulado) y solo al expandirse descarga el detalle tabular. Usa un endpoint propio (`POST /api/reconcile/details/no-banco`) que retorna `{ total, total_amount, rows[] }`.
- **Card y endpoint “Banco No reflejado en PILAGA”**: `NoContableCard.svelte` consume `POST /api/reconcile/details/no-contable`, que devuelve los sobrantes bancarios con `{ total, total_amount, rows[] }`, reutilizando el matcher actual.
- **Card y endpoint “Agrupados aprobados (N→1)”**: `AprobadosN1Card.svelte` consume `POST /api/reconcile/details/n1/grupos`, que arma combinaciones exactas 2..6→1 sin validación manual (usa la heurística: misma ventana, mismo signo, cand_limit 20, tol $1). Se muestra como aprobados de forma automática.
- **Backend**: `routes/v1/reconcile_details.py` expone el endpoint legacy `/api/reconcile/details` y los específicos `/api/reconcile/details/no-banco`, `/api/reconcile/details/no-contable` y `/api/reconcile/details/n1/grupos`, reportando la suma de importes (`total_amount`) para alimentar los badges de la UI.
- **Registro en el server**: `ls_iMotorSoft_Srv01.py` monta los handlers en `route_handlers`, por lo que la API ya responde en los entornos locales y remotos.
- **Próximos pasos**: replicar el patrón card+endpoint para “Grupo N→1 confirmados”, “Sugeridos N→1” y “Conciliados 1→1”, manteniendo la misma UX de cards colapsables y contadores visibles sin abrir cada detalle.

### 8.1 Endpoints pendientes (detalle inicial)

1. **`POST /api/reconcile/details/n1/sugeridos`**  
   - Usa el matcher heurístico para proponer combinaciones pendientes de aprobación.  
   - Payload: igual estructura que “grupos” pero con `estado = suggested` y métricas de confianza.  
   - UI: card con badges y CTA para aceptar/rechazar (cuando esté disponible el flujo).

2. **`POST /api/reconcile/details/pares`**  
   - Devuelve los pares exactos 1→1 conciliados (idéntico monto dentro de la ventana).  
   - Payload: `{ ok, total, rows: [{fecha_banco, fecha_pilaga, monto, documento_banco, documento_pilaga}], meta }`.  
   - UI: card “Conciliados 1→1” con tabla básica para auditoría rápida.
