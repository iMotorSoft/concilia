# Estado de avance - Wizard UX

## Contexto
- El modal del Asistente se abre inmediatamente al click en "Reconciliar".
- El POST a `/api/reconcile_wizard/start` funciona con `status: "started"`.
- Se conecta SSE de wizard y se renderiza Step 1 con preview y alertas.

## Estado actual (OK)
- Step 1 muestra "Ventana maxima detectada", meses faltantes/parciales y outliers.
- Warning visible: "Hay meses parciales u outliers detectados. Revisar antes de continuar."
- Se completan los pasos 1/2/3 y el wizard dispara la conciliación tras confirmar.

## Resultado verificado (2025-12-25)
- Extracto: `file:///media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/storage/incoming/6c8459c0-d1d2-4aab-b794-f61f4e5e4539_EXTRACTO SANTANDER AGOST-SEPT.xlsx`
- Contable: `file:///media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/storage/incoming/cf83f416-72d8-4749-9e7f-b1e703840b67_PILAGA SANTANDER AGOST -SEPT.xlsx`
- Movimientos: PILAGA 1371, Banco 1120.
- Conciliados (pares): 418. No en Banco: 787. No en PILAGA: 651. Ventana: 5 días.
- Banco: Debe $1.145.509.747,73 | Haber $995.630.868,07 | Neto -$149.878.879,66.
- PILAGA: Ingresos $980.539.821,97 | Egresos $1.208.767.077,51 | Neto -$228.227.255,54.
- Descomposición ok (1→1, agrupados, sugeridos, no reflejado). Diferencia neto Banco - PILAGA: $78.348.375,88.

## Pendiente
- Revisar detalle en UI (cards de no conciliados / N→1) si falta render o expansión.
- Verificar que `account` no llegue vacío en el POST start en todos los escenarios.

## Commit recientes
- `b5ada0a` Open wizard modal on reconcile
- `b2decbb` Accept wizard start status
- `9cc01c9` Parse wizard payloads and map scope
