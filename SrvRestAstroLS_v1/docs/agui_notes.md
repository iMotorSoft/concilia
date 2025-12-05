## AG-UI alignment notes (draft)

- Current UI (`ConciliaApp.svelte`, `ReconciliarApp.svelte`) uses raw `EventSource` and custom event types (`TEXT_MESSAGE_REQUEST_UPLOAD`, `INGEST_PREVIEW`, `RUN_START/RESULTS_READY`, `TOAST`). No usage of `@ag-ui/client`/`@ag-ui/core` event schemas or `HttpAgent`.
- Backend emits ad-hoc payloads via `/api/ag-ui/notify/stream`; messages do not match AG-UI `EventType` requirements (no `RUN_STARTED/FINISHED`, no `messageId` per text event, custom event names not wrapped as `CUSTOM`).
- `ag-ui-protocol` dependency is unused server-side; no `/agent` endpoint that accepts `RunAgentInput` and streams schema-valid events.
- Migration idea: add compatibility layer that can emit both existing custom events and AG-UI-compatible `CUSTOM { name, value }` events; later expose proper run endpoint and switch Svelte to `HttpAgent` + subscribers.
- Suggested near-term stance: keep current flow (works today), add light compatibility to reduce future refactor cost; plan a short sprint once AG-UI stabilizes.
