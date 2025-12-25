# Estado de avance - Wizard UX

## Contexto
- El modal del Asistente se abre inmediatamente al click en "Reconciliar".
- El POST a `/api/reconcile_wizard/start` funciona con `status: "started"`.
- Se conecta SSE de wizard y se renderiza Step 1 con preview y alertas.

## Estado actual (OK)
- Step 1 muestra "Ventana maxima detectada", meses faltantes/parciales y outliers.
- Warning visible: "Hay meses parciales u outliers detectados. Revisar antes de continuar."
- Último evento visto: `FORM_SNAPSHOT`.

## Pendiente
- Continuar validando avance de pasos (Step 2/3) y envío de acciones.
- Verificar que `account` no llegue vacío en el POST start en todos los escenarios.
- Confirmar que no se llama `/api/reconcile/start` hasta confirmar en el wizard.

## Commit recientes
- `b5ada0a` Open wizard modal on reconcile
- `b2decbb` Accept wizard start status
- `9cc01c9` Parse wizard payloads and map scope
