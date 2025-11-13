# Matching N→1 (Propuesta)

## 1. Objetivo

Extender el flujo de conciliación para cubrir movimientos bancarios que representan la suma de varios asientos PILAGA (N movimientos contables contra 1 del banco), manteniendo una trazabilidad clara de los componentes antes de marcarlos como conciliados.

## 2. Casos de prueba usados

| Dataset | Extracto | PILAGA | Rango fechas | Resultados 1→1 | Sobrantes Banco | Sobrantes PILAGA |
| --- | --- | --- | --- | --- | --- | --- |
| Santander Septiembre | `09 - EXTRACTO.xlsx` | `09 - PILAGA.xlsx` | 2025-09 | 25 pares | 2 | 1 |
| Patagonia Ago-Sep | `EXTRACTO PATAGONIA AGOST-SEPT.xlsx` | `PILAGA PATAGONIA AGOST-SEPT.xlsx` | 2025-08/09 | 106 pares | 284 | 1.660 |

En Santander, los dos sobrantes del banco son egresos pequeños que no combinan con otros movimientos; en Patagonia predominan las transferencias masivas que agrupan 2–5 pagos PILAGA.

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

| Dataset | N→1 detectados | 2→1 | 3→1 | 4→1 | 5→1 | 6→1 |
| --- | --- | --- | --- | --- | --- | --- |
| Santander Sept | 0 | 0 | 0 | 0 | 0 | 0 |
| Patagonia Ago-Sep | 24 | 11 | 7 | 4 | 2 | 0 |

Ejemplos confirmados en Patagonia:

- `Banco 04/08, -$10.000.000` = OP:4717/2025 (-6M) + OP:4822/2025 (-4M).
- `Banco 04/08, -$75.000.000` = OP:4667/2025 (-25.45M) + OP:4666/2025 (-25.25M) + OP:4662/2025 (-24.30M).
- `Banco 02/09, -$40.320.000` = OP:6792/2025 (-22.04M) + OP:6423/2025 (-7.58M) + OP:6370/2025 (-4M) + OP:6409/2025 (-4M) + OP:6321/2025 (-2.7M).

## 5. Parámetros recomendados (iniciales)

| Parámetro | Valor sugerido | Notas |
| --- | --- | --- |
| `days_window` | 5 | Igual que el matcher actual; se puede escalar a 7 si negocio lo pide. |
| `max_combo` | 5 (hasta 6) | Evita combinaciones con más de 5-6 PILAGA para mantener tiempos de cómputo razonables. |
| `cand_limit` | 20 | Cantidad máxima de candidatos PILAGA por búsqueda. |
| `tol_amount` | $1 | Diferencia tolerada al comparar la suma con el monto del extracto. |

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
