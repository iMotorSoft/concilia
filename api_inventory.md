# API Inventory (2025-12-22)

This document provides a comprehensive list of all active API endpoints in the `SrvRestAstroLS_v1` project.

## Core Infrastructure & SSE

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/ag-ui/notify/stream` | **SSE stream** for AG-UI notifications. Used for real-time progress updates. |
| `POST` | `/api/chat/turn` | Message handler for the chat interface. Triggers file upload requests. |

## Ingestion & Uploads

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/uploads/v2/ingest` | **v2 Upload**: Supports multiple files, consolidate extractos, and sniffing. |
| `POST` | `/api/ingest/confirm` | Confirms an ingestion preview and triggers canonicalization (Parquet). |
| `POST` | `/api/uploads/bank-movements` | **v1 Upload**: Legacy endpoint for bank movement uploads. |

## Reconciliation (Core)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/reconcile/start` | **Main execution**: Starts a core-only reconciliation run. |
| `POST` | `/api/reconcile/summary` | Full summary of a reconciliation result. |
| `POST` | `/api/reconcile/summary/head` | Summary restricted to totals and main metrics. |
| `POST` | `/api/reconcile/summary/descomposicion` | Summary restricted to the decomposition of matched groups. |

## Reconciliation Details (UI Components)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/reconcile/details` | General details for unmatched rows in both banks and contabilidad. |
| `POST` | `/api/reconcile/details/no-banco` | List of items present in PILAGA but missing in Bank. |
| `POST` | `/api/reconcile/details/no-contable` | List of items present in Bank but missing in PILAGA. |
| `POST` | `/api/reconcile/details/pares` | List of 1-to-1 exact matches (by amount and date window). |
| `POST` | `/api/reconcile/details/n1/grupos` | List of grouped matches (N contable rows to 1 bank row). |
| `POST` | `/api/reconcile/details/n1/sugeridos` | List of suggested matches (wider tolerance). |

## Reconciliation Wizard (Step-by-Step)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/v1/reconcile_wizard/start` | Starts a interactive wizard run. |
| `GET` | `/v1/runs/{run_id}/events` | **SSE stream** specific for events within a `run_id`. |
| `POST` | `/v1/runs/{run_id}/action` | Submits user actions/decisions to the wizard engine. |

> [!NOTE]
> All endpoints expect `multipart/form-data` or `x-www-form-urlencoded` unless otherwise specified.
