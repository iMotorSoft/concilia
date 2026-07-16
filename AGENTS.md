# Concilia - Instrucciones para agentes

Este archivo es la fuente operativa canonica para agentes que trabajen en Concilia. Las politicas extensas se consultan solo cuando la tarea las necesita.

## Inicio obligatorio

1. Trabajar desde `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia`.
2. Ejecutar `git branch --show-current` y `git status --short`.
3. Leer `SrvRestAstroLS_v1/docs/status_actual.md`.
4. Para cambios de arquitectura, leer `lat.md/lat.md`, `lat.md/status_actual.md` y el documento canonico relevante.
5. No cambiar de rama ni pisar cambios existentes.
6. Un solo agente puede escribir sobre un worktree.

No hacer commit, push, merge, rebase, reset, clean, stash, checkout forzado ni borrar ramas salvo pedido explicito del usuario.

## Identidad y stack

- marca visible: `Concilia FCE`;
- identificador tecnico: `concilia`;
- variables de entorno: prefijo `CONCILIA_`;
- backend: Litestar en `127.0.0.1:7058`;
- entrypoint: `SrvRestAstroLS_v1/backend/ls_iMotorSoft_Srv01.py`;
- objeto ASGI: `app`;
- frontend: Astro 7 + Svelte 5 en `127.0.0.1:3058`;
- PostgreSQL: verdad persistente (uploads, canonical, runs, reconciliation);
- Sin Milvus (no integrado);
- Sin LiteLLM (no integrado);
- Playwright + Chromium: browser gate.

No crear `SrvRestAstroLS_v1/backend/app.py` sin un ADR que apruebe la excepcion.

## Servidores de desarrollo

Los launchers canonicos para desarrollo local viven en `SrvRestAstroLS_v1/`.

- backend: `./SrvRestAstroLS_v1/backend-dev.sh`;
- frontend: `./SrvRestAstroLS_v1/astro-dev.sh`;
- acciones soportadas: `start`, `stop`, `restart`, `status`; sin accion equivale a `start`;
- `backend-dev.sh` ejecuta `uvicorn ls_iMotorSoft_Srv01:app` sobre `127.0.0.1:7058` por defecto;
- `astro-dev.sh` ejecuta `astro dev` sobre `127.0.0.1:3058` por defecto;
- overrides permitidos solo para conflictos locales intencionales: `CONCILIA_BACKEND_HOST`, `CONCILIA_BACKEND_PORT`, `CONCILIA_ASTRO_HOST`, `CONCILIA_ASTRO_PORT`;
- `backend-dev.sh` puede cargar `SrvRestAstroLS_v1/.env.backend-dev.local` como overrides locales no versionados.

Estos scripts guardan PID files en `SrvRestAstroLS_v1/.dev-pids/` y logs en `SrvRestAstroLS_v1/.dev-logs/`. `stop` solo envia señales a un PID file validado por comando esperado; si el puerto esta ocupado por un proceso desconocido, lo reportan y no lo matan. No deben usarse para gestionar PostgreSQL.

## Ramas

| Rama | Responsabilidad |
| --- | --- |
| `main` | Snapshot estable; no desarrollar directamente salvo hotfix explicito. |
| `feature/reconciliation-core` | Backend, frontend, wizard, SICOM, multi-banco. |
| `feature/sicom-integration` | Ingesta SICOM, agrupación, regla Nro Pago + OP, auditoría. |
| `docs/architecture-foundation` | Estándares, LAT, ADRs, documentación de conocimiento. |

`desarrollo`, `dev` y `backend` corresponden a `feature/reconciliation-core`.

La rama heredada `ux/team360-console-design-handoff` tiene un nombre ajeno a Concilia y no es canonica. No usarla ni replicar nombres `team360_*` en nuevas ramas.

## Contexto por tarea

| Tarea | Referencia obligatoria |
| --- | --- |
| Arquitectura general | `lat.md/lat.md` y `lat.md/concilia-knowledge-map.md` |
| Configuracion, secretos o variables | `lat.md/global-configuration-facade-policy.md` |
| PostgreSQL | `lat.md/postgres-driver-policy.md` |
| Auth, tokens o roles | `lat.md/authentication-security-policy.md` |
| Conciliación, scopes, matching | `lat.md/reconciliation-scope-contract.md` |
| SICOM ingesta/reglas | `lat.md/sicom-integration-policy.md` |
| Wizard runtime / fallback | `lat.md/wizard-runtime-policy.md` |
| PDF/Excel extraction | `lat.md/pdf-excel-extraction-policy.md` |
| Servicios reales o benchmarks | `lat.md/service-preflight-methodology.md` |
| Browser QA o E2E | `lat.md/browser-mcp-validation-policy.md` |
| Bugs no triviales | `lat.md/root-cause-debugging-policy.md` |
| Diagramas | `lat.md/mermaid-diagram-policy.md` |

## Limites de implementacion

- Hacer cambios pequenos y limitados al objetivo.
- PostgreSQL es la fuente de verdad; parquets canonical son derivados.
- No iniciar, detener, reiniciar, migrar ni reconfigurar PostgreSQL sin instruccion explicita.
- Usar `psycopg 3 async`; mantener SQL en repositories.
- No introducir ORM sin ADR.
- Solo `core/config.py` puede leer variables de entorno del backend.
- `globalVar.py` (raiz) es una fachada sin conexiones ni efectos secundarios; migración pendiente a `backend/core/config.py`.
- Toda configuracion PostgreSQL se resuelve via `backend/core/config.py` desde `DB_PG_*` + base `concilia` (o `workflow_ai_v1` legacy). Los scripts no deben leer variables PostgreSQL de forma dispersa.
- `global.js` contiene solo configuracion publica y nunca secretos.
- No hardcodear credenciales, tokens, passwords, API keys ni credenciales E2E.
- No introducir logica bancaria especifica en modulos genericos cuando pueda expresarse como datos, colecciones o configuracion.

## Validacion

Ejecutar siempre:

- `git diff --check`;
- tests focalizados del modulo afectado;
- revision del diff final;
- `lat check` si cambia `lat.md/` o una referencia `@lat`.

Segun el cambio:

- backend: `cd SrvRestAstroLS_v1/backend && uv run pytest <paths>`;
- frontend: `cd SrvRestAstroLS_v1/clientA && pnpm check`;
- build o paginas: agregar `pnpm build`;
- E2E autenticado: proporcionar `CONCILIA_E2E_ADMIN_EMAIL` y `CONCILIA_E2E_ADMIN_PASSWORD` desde el entorno;
- servicios reales: ejecutar preflight y comprobar que no exista fallback silencioso.

Playwright + Chromium es el gate E2E. Browser MCP es exploratorio y no reemplaza una regresion reproducible.

## Documentacion

- `SrvRestAstroLS_v1/docs/status_actual.md`: estado tecnico vigente y compacto.
- `SrvRestAstroLS_v1/docs/status_historico_hasta_2026-07-15.md`: historia tecnica congelada.
- `lat.md/`: invariantes, contratos y decisiones estables.
- `docs/adr/`: decisiones arquitectonicas con contexto y consecuencias.
- `data/reports/`: evidencia y resultados generados.

No duplicar decisiones largas en status. Enlazar a la fuente canonica.

## Cierre

Reportar rama, archivos modificados, validaciones, impacto, riesgos y proximo paso.