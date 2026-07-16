# Status actual - Concilia lat.md

Este tablero resume la arquitectura viva de Concilia y evita repetir la historia técnica del runtime.

Objetivo: `arquitectura-viva`

Ultima actualizacion: 2026-07-16 (inicial)

## Estado general

LAT documenta configuración, persistencia, autenticación, conciliación, wizard runtime y límites operativos con un índice único y referencias desde código.

- PostgreSQL es fuente de verdad (uploads, canonical parquets, runs, events, reconciliation state).
- No hay índice vectorial (Milvus no integrado).
- No hay gateway LLM (LiteLLM no integrado).
- El wizard de conciliación corre con fallback en memoria (`services/wizard_runtime.py`) cuando la DB `workflow_ai_v1` no está disponible.
- SICOM es una fuente de datos auxiliar (no fuente de verdad); se agrupa por `Fecha de Pago + Banco + Nro Pago` y manda `Nro Pago` + `OP`.
- `SrvRestAstroLS_v1/backend-dev.sh` y `SrvRestAstroLS_v1/astro-dev.sh` son los entrypoints operativos locales para servidores dev (puertos 7058/3058).

## Decisiones vigentes

Las decisiones estables se mantienen en documentos canónicos enlazados desde [[lat]].

- [[global-configuration-facade-policy]] concentra configuración y secretos.
- [[postgres-driver-policy]] fija `psycopg 3 async` y repositories SQL.
- [[authentication-security-policy]] define passwords, tokens, roles y sesión web.
- [[reconciliation-scope-contract]] separa scope bancario, contable y SICOM.
- [[sicom-integration-policy]] define ingesta, agrupación, regla mandatoria `Nro Pago + OP` y auditoría.
- [[wizard-runtime-policy]] gobierna fallback en memoria, SSE y ciclo de vida del wizard.
- [[service-preflight-methodology]] gobierna pruebas con servicios reales.
- [[concilia-knowledge-map]] ofrece el árbol de navegación.

## Consolidación 2026-07-16

Estructura inicial de arquitectura viva creada para alinear con patrón TebaAI.

- `AGENTS.md` creado como fuente operativa canónica.
- `lat.md/` creado con políticas canónicas y referencias `@lat`.
- `docs/adr/` creado para decisiones arquitectónicas.
- Status runtime compactado: `status_actual.md` (vigente) + `status_historico_hasta_2026-07-15.md` (congelado).
- Configuración y PostgreSQL centralizados en `backend/core/config.py` (pendiente migración desde `globalVar.py` raíz).
- Credenciales E2E sin fallback versionado.

## Validación

La documentación debe aprobar validación estructural y mantener referencias resolubles.

- `lat check`: gate obligatorio y objetivo de cero errores.
- `git diff --check`: obligatorio.
- tests focalizados: obligatorios cuando cambian referencias dentro de código.
- `lat search`: opcional mientras no exista clave LAT; usar `lat locate` como alternativa.

## Pendientes

La deuda arquitectónica restante requiere decisiones explícitas y no debe mezclarse con tareas ya cerradas.

1. ADR para migración `globalVar.py` raíz → `backend/core/config.py` + `globalVar.py` como façade.
2. ADR para cookies `httpOnly`, CSRF y refresh automático.
3. ADR para límite plataforma Concilia / verticales bancarias (Patagonia, Santander, etc).
4. ADR previo a cualquier integración LLM/RAG.
5. Reconciliar conteos PostgreSQL/parquet canonical antes de reindexar.
6. Definir política multi-tenancy real vs single-tenant actual.

## Mapping lógico SICOM — 2026-07-16

El scope bancario resuelve alias entre el banco del extracto y el scope SICOM:

```text
bank_scope_code = "patagonia"
  → SICOM bancos = {banco_patagonia, banco_pat_otros}
  → SQL: banco IN ('banco_patagonia', 'banco_pat_otros')
```

Este mapping se resuelve en `routes/v1/reconcile_start.py` via `BANK_SCOPE_MAP`.
Cualquier ruta nueva que filtre SICOM por banco objetivo debe replicar este mapping.
Si no está resuelto, la expresión de filtro puede excluir lotes válidos.

## Wizard Runtime Fallback — 2026-04-20

El wizard implementa fallback en memoria cuando `workflow_ai_v1` no existe:

- `services/wizard_runtime.py`: store en memoria para runs, events, snapshots.
- `routes/v1/reconcile_wizard_start.py`: try DB → except → memoria.
- `routes/v1/run_action.py`: lee/escribe estado y eventos en memoria para runs fallback.
- SSE del wizard sirve eventos desde memoria para runs fallback.

Objetivo: no bloquear pruebas funcionales de conciliación por la DB del core.
No reemplaza la persistencia real; es escape hatch temporal.

## Seguridad

Los documentos y ejemplos no deben contener credenciales funcionales ni fallbacks compartidos.

Las pruebas autenticadas reciben email y password mediante variables de entorno y se omiten de forma explícita cuando faltan.