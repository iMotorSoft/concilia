# Resumen pipeline de conciliación (UI + backend)

## Secuencia única
1. **Conciliados 1→1**: monto redondeado a 2 decimales, |fecha_b - fecha_p| <= `days_window` (default 30). Resultado: pares exactos.
2. **Agrupados (≤ $1)**: combina sobrantes en PILAGA para igualar movimiento de banco dentro de tolerancia $1 (misma ventana y signo). No reutiliza movimientos ya usados.
3. **Sugeridos (>$1 hasta $5)**: mismas reglas que agrupados pero con tolerancia $5, excluyendo cualquier caso que ya entre en ≤$1. No reutiliza movimientos ya usados.
4. **Sobrantes**: lo que queda en banco (`no-contable`) y en PILAGA (`no-banco`) después de los pasos anteriores.

Todas las categorías son disjuntas y sus totales suman al total banco/contable del dataset.

## Parámetros clave
- `days_window` default: **30** (form/envía la UI).
- Tolerancias: `N1_TOL_APPROVED = 1.0`, `N1_TOL_SUGGESTED = 5.0`.
- Máx. componentes por grupo N→1: 6; candidatos: 20; misma ventana de fechas.

## Endpoints (backend)
- `/api/reconcile/details/pares` → Conciliados 1→1.
- `/api/reconcile/details/n1/grupos` → Agrupados (≤ $1).
- `/api/reconcile/details/n1/sugeridos` → Sugeridos (>$1 y ≤ $5, excluyendo aprobados).
- `/api/reconcile/details/no-contable` → Sobrantes banco.
- `/api/reconcile/details/no-banco` → Sobrantes PILAGA.
- `/api/reconcile/details` → Devuelve los sobrantes de ambos (mismo pipeline).

## Cards (UI)
- Conciliados 1→1.
- Agrupados (≤ $1).
- Sugeridos (N→1).
- PILAGA no reflejado en banco.
- Banco no reflejado en PILAGA.

Cada card consulta su endpoint y muestra contador + total que, en conjunto, cuadran con el total del extracto/contable cargado.
