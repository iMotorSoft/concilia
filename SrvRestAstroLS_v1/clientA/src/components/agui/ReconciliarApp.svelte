<script lang="ts">
// src/components/agui/ReconciliarApp.svelte
import { URL_REST } from '../global';
import ReconciliarResumen from "../agui/ReconciliarResumen.svelte";
import ReconciliarDetalle from '../agui/ReconciliarDetalle.svelte';
import { get } from 'svelte/store';
import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from './reconcileConfig';


// ===== Estado =====
let chatInput = $state("");
let sending   = $state(false);

let dialogOpen = $state(false);
let dialogRef: HTMLDialogElement | null = null;
let uploadBusy = $state(false);

let formSpec: any = $state(null);
let formValues: Record<string, any> = $state({});
let fileObjs: File[] = $state([]);
let fileInputRef: HTMLInputElement | null = null;

// Dos previews independientes
let previewExtracto: any = $state(null);
let previewContable: any = $state(null);

// Conciliación
let reconciling = $state(false);
let results: any = $state(null);

// Wizard
let wizardOpen = $state(false);
let wizardDialogRef: HTMLDialogElement | null = null;
let wizardRunId = $state<string | null>(null);
let wizardThreadId = $state<string | null>(null);
let wizardSseUrl = $state<string | null>(null);
let wizardSse: EventSource | null = null;
let wizardNotifySse: EventSource | null = null;
let wizardNotifyThreadId: string | null = null;
let wizardStatus = $state<"idle"|"opening"|"starting"|"ready"|"error">("idle");
let wizardError: string | null = $state(null);
let wizardEvents: any[] = $state([]);
let wizardState: any = $state(null);
let wizardStepId = $state("SCOPE");
let wizardStepTitle = $state("");
let wizardAlerts: any[] = $state([]);
let wizardForm: any = $state(null);
let wizardListItems: any[] = $state([]);
let wizardConfirm: any = $state(null);
let wizardScopeMode = $state("ALL");
let wizardWindowFrom = $state("");
let wizardWindowTo = $state("");
let wizardMonths: string[] = $state([]);
let wizardBusy = $state(false);
let wizardInitializing = $state(false);
let wizardAccountInput = $state("");
let wizardBankInput = $state("");
let wizardNeedsAccount = $state(false);
let wizardNeedsBank = $state(false);

let es: EventSource | null = null;
let toast: { level: "info"|"success"|"warning"|"error"; message: string } | null = $state(null);
let toastTimer: any = null;

let confirmBusyExtracto = $state(false);
let confirmBusyContable = $state(false);

const threadId = crypto?.randomUUID?.() ?? `t-reconciliar-${Date.now()}`;

function showToast(level: "info"|"success"|"warning"|"error", message: string) {
  toast = { level, message };
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast = null), 2600);
}

$effect(() => {
  if (!dialogRef) return;
  if (dialogOpen && !dialogRef.open) dialogRef.showModal?.();
  if (!dialogOpen && dialogRef.open) dialogRef.close?.();
});

$effect(() => {
  if (!wizardDialogRef) return;
  if (wizardOpen && !wizardDialogRef.open) wizardDialogRef.showModal?.();
  if (!wizardOpen && wizardDialogRef.open) wizardDialogRef.close?.();
});

function seedFormDefaults(spec: any) {
  const d: Record<string, any> = {};
  for (const f of (spec?.fields ?? [])) {
    if (f.type === "file") continue;
    d[f.name] = ("default" in f && f.default != null) ? f.default : "";
  }
  formValues = d;
  fileObjs = [];
}

function resolveWizardBank() {
  return (
    previewExtracto?.detected?.bank ||
    previewContable?.detected?.bank ||
    ""
  );
}

function resolveWizardAccount() {
  return (
    previewExtracto?.detected?.account_full ||
    previewExtracto?.detected?.account_core_dv ||
    previewExtracto?.detected?.account ||
    previewExtracto?.detected?.account_id ||
    previewContable?.detected?.account_full ||
    previewContable?.detected?.account_core_dv ||
    previewContable?.detected?.account ||
    previewContable?.detected?.account_id ||
    ""
  );
}

function resolveWizardDatasetRef() {
  const extracto = previewExtracto || {};
  const originalUri = (extracto?.original_uri || "").toString();
  const v2Ref = originalUri && !originalUri.startsWith("file://") ? originalUri : "";
  const uploads = Array.isArray(extracto?.meta?.uploads) ? extracto.meta.uploads : [];
  const uploadCanonical = uploads.find((u: any) => u?.canonical_uri)?.canonical_uri || "";
  return (
    extracto?.dataset_ref ||
    extracto?.canonical_uri ||
    extracto?.manifest_uri ||
    extracto?.meta?.manifest_uri ||
    extracto?.meta?.canonical_uri ||
    uploadCanonical ||
    v2Ref ||
    ""
  );
}

function connectSSE() {
  if (es) es.close();
  es = new EventSource(`${URL_REST}/api/ag-ui/notify/stream?threadId=${encodeURIComponent(threadId)}`);
  es.onmessage = (ev) => {
    try { handle(JSON.parse(ev.data)); } catch {}
  };
  es.onerror = () => showToast("error", "Conexión SSE caída.");
}

function connectWizardNotifySSE(targetThreadId: string) {
  if (!targetThreadId) return;
  if (targetThreadId === threadId) {
    if (!es) connectSSE();
    return;
  }
  if (wizardNotifySse && wizardNotifyThreadId === targetThreadId) return;
  if (wizardNotifySse) wizardNotifySse.close();
  wizardNotifyThreadId = targetThreadId;
  wizardNotifySse = new EventSource(
    `${URL_REST}/api/ag-ui/notify/stream?threadId=${encodeURIComponent(targetThreadId)}`
  );
  wizardNotifySse.onmessage = (ev) => {
    try { handle(JSON.parse(ev.data)); } catch {}
  };
  wizardNotifySse.onerror = () => showToast("error", "Conexión SSE del wizard caída.");
}

function connectWizardSSE(runId: string, sseUrl?: string | null) {
  if (wizardSse) wizardSse.close();
  const url = sseUrl
    ? (sseUrl.startsWith("http") ? sseUrl : `${URL_REST}${sseUrl}`)
    : `${URL_REST}/api/reconcile_wizard/runs/${runId}/events`;
  wizardSse = new EventSource(url);
  wizardSse.onopen = () => {
    wizardError = null;
  };
  wizardSse.onmessage = (ev) => {
    try { handleWizard(JSON.parse(ev.data)); } catch {}
  };
  wizardSse.onerror = () => {
    wizardInitializing = false;
    wizardStatus = "error";
    wizardError = "No se pudo conectar con los eventos del asistente.";
    showToast("error", "Conexión SSE del wizard caída.");
  };
}

function wizardStepIndex() {
  if (wizardStepId === "SUMMARY") return 3;
  if (wizardStepId === "MONTHS" || wizardStepId === "WINDOW") return 2;
  return 1;
}

function handle(msg: any) {
  const t = (msg?.type || "").toUpperCase();

  if (t === "DEBUG" && msg.stage === "CONNECTED") {
    showToast("info", `SSE conectado (${threadId})`);
    return;
  }

  if (t === "TEXT_MESSAGE_REQUEST_UPLOAD") {
    formSpec = msg?.payload?.form || null;
    seedFormDefaults(formSpec);
    dialogOpen = true;
    return;
  }

  if (t === "INGEST_PREVIEW") {
    const payload = msg?.payload || {};
    const kind = (payload.kind || "").toLowerCase();
    const role = (payload.role || "").toLowerCase();
    const resolvedRole =
      kind === "gl" ? "contable" :
      kind === "bank_movements" ? "extracto" :
      role || "";

    if (resolvedRole === "extracto") {
      previewExtracto = payload;
    } else if (resolvedRole === "contable") {
      previewContable = payload;
    } else {
      previewExtracto = payload; // fallback
    }
    dialogOpen = false;
    showToast("info", "Vista previa lista. Revisá y confirmá.");
    return;
  }

  if (t === "INGEST_CANONICAL_READY") {
    const payload = msg?.payload || {};
    const role = (payload.role || "").toLowerCase();
    const canonical_uri = payload.canonical_uri || "";
    if (role === "extracto" && previewExtracto) {
      previewExtracto = { ...(previewExtracto || {}), canonical_uri };
      showToast("info", "Canónico listo (extracto).");
    } else if (role === "contable" && previewContable) {
      previewContable = { ...(previewContable || {}), canonical_uri };
      showToast("info", "Canónico listo (contable).");
    }
    return;
  }

  if (t === "RUN_START") {
    if (wizardOpen) wizardOpen = false;
    reconciling = true; // spinner ON
    showToast("success", "Iniciando conciliación…");
    return;
  }

  if (t === "RESULTS_READY") {
    // payload.summary esperado desde /api/reconcile/start
    results = msg?.payload?.summary || null;
    if (results?.days_window != null) {
      daysWindowStore.set(normalizeDaysWindow(results.days_window));
    }
    reconciling = false; // spinner OFF
    showToast("success", "Resultados listos.");
    return;
  }

  if (t === "TEXT_MESSAGE_CONTENT" && msg.delta) {
    showToast("info", msg.delta);
    return;
  }
}

function handleWizard(msg: any) {
  const t = (msg?.type || "").toUpperCase();
  const payload = typeof msg?.payload === "string"
    ? (() => { try { return JSON.parse(msg.payload); } catch { return msg.payload; } })()
    : (msg?.payload ?? null);

  if (t === "HEARTBEAT") return;
  wizardEvents = [...wizardEvents, msg].slice(-40);

  if (t === "WIZARD_STATE_SET") {
    wizardState = payload || null;
    wizardStatus = "ready";
    wizardError = null;
    const selection = wizardState?.selection || {};
    const scopeMode = (selection.scope_mode || "").toUpperCase();
    wizardScopeMode =
      scopeMode === "WINDOW" ? "RANGE" :
      scopeMode === "MANUAL" ? "MONTHS" : "ALL";
    wizardMonths = selection.months || [];
    const windowRange = selection.window_range || {};
    if (windowRange.from) wizardWindowFrom = windowRange.from;
    if (windowRange.to) wizardWindowTo = windowRange.to;
    const previewRange = wizardState?.context?.preview?.range || [];
    if (!wizardWindowFrom && previewRange[0]) wizardWindowFrom = previewRange[0];
    if (!wizardWindowTo && previewRange[1]) wizardWindowTo = previewRange[1];
    if (wizardState?.step) wizardStepId = wizardState.step;
    wizardInitializing = false;
    return;
  }

  if (t === "STEP_SET") {
    wizardStepId = payload?.step_id || wizardStepId;
    wizardStepTitle = payload?.title || "";
    wizardConfirm = null;
    if (wizardStatus !== "ready") wizardStatus = "ready";
    return;
  }

  if (t === "RUN_STARTED") {
    wizardInitializing = true;
    wizardStatus = "starting";
    return;
  }

  if (t === "RUN_FAILED") {
    wizardInitializing = false;
    wizardStatus = "error";
    wizardError = msg?.payload?.error || "El asistente falló al inicializar.";
    return;
  }

  if (t === "ALERT_ADD") {
    wizardAlerts = [...wizardAlerts, payload];
    return;
  }

  if (t === "FORM_SNAPSHOT") {
    wizardForm = payload?.form || null;
    return;
  }

  if (t === "LIST_SNAPSHOT") {
    wizardListItems = payload?.items || [];
    return;
  }

  if (t === "CONFIRMATION_REQUIRED") {
    wizardConfirm = payload || {};
    return;
  }

  if (t === "RUN_READY_TO_EXECUTE") {
    showToast("success", "Plan listo. Confirmá para iniciar.");
    return;
  }

  if (t === "TEXT_MESSAGE_ADD" && payload?.text) {
    showToast("info", payload.text);
  }
}

async function onSendText(customText?: string) {
  const text = ((customText ?? chatInput) || "").trim();
  if (!text || sending) return;
  // Sincroniza el textarea cuando se usan accesos rápidos
  chatInput = text;
  sending = true;
  try {
    const correlationId = crypto?.randomUUID?.() ?? `corr-${Date.now()}`;
    const res = await fetch(`${URL_REST}/api/chat/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threadId, correlationId, text }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast("info", "Solicitud enviada.");
  } catch {
    showToast("error", "No se pudo procesar el mensaje.");
  } finally { sending = false; }
}

function onKeydownChat(e: KeyboardEvent) {
  if ((e.ctrlKey || (e as any).metaKey) && e.key === "Enter") {
    e.preventDefault(); onSendText();
  }
}

// ===== Upload (modal) =====
async function onSubmitUpload() {
  if (!formSpec) return;

  const fd = new FormData();
  fd.set("threadId", threadId);
  fd.set("correlationId", crypto?.randomUUID?.() ?? `corr-upload-${Date.now()}`);
  const selectedFiles = Array.from(fileInputRef?.files || []);
  if (!selectedFiles.length) { showToast("warning", "Seleccioná un archivo."); return; }
  for (const file of selectedFiles) {
    fd.append("file", file, file.name);
  }
  showToast("info", `Subiendo ${selectedFiles.length} archivo(s)…`);

  uploadBusy = true;
  try {
    // Fallback robusto a v2 + role deducida si el backend no lo manda
    const roleDefault = formSpec?.payload?.role ?? "extracto";
    const endpoint = formSpec?.submit?.endpoint || `/api/uploads/v2/ingest?role=${encodeURIComponent(roleDefault)}`;
    const method = formSpec?.submit?.method || "POST";

    const res = await fetch(`${URL_REST}${endpoint}`, { method, body: fd });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    showToast("success", j?.message || "Archivo recibido.");
    dialogOpen = false; // cerrar modal al terminar
  } catch {
    showToast("error", "No se pudo subir el archivo.");
  } finally {
    uploadBusy = false;
  }
}

// ===== Confirmación por card =====
async function onConfirmPreview(role: "extracto"|"contable") {
  const p = role === "extracto" ? previewExtracto : previewContable;
  if (!p) return;

  if (role === "extracto") confirmBusyExtracto = true;
  else confirmBusyContable = true;

  try {
    const fd = new FormData();
    fd.set("threadId", threadId);
    fd.set("correlationId", crypto?.randomUUID?.() ?? `corr-confirm-${role}-${Date.now()}`);
    fd.set("role", role);
    fd.set("source_file_id", p.source_file_id || "");
    fd.set("original_uri", p.original_uri || "");
    fd.set("bank", p?.detected?.bank || "");
    fd.set("period_from", p?.suggest?.period_from || p?.detected?.period_from || "");
    fd.set("period_to", p?.suggest?.period_to || p?.detected?.period_to || "");

    const res = await fetch(`${URL_REST}/api/ingest/confirm`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    showToast("success", j?.message || `Confirmado (${role}).`);

    // Marcar card como confirmada para ocultar el botón
    if (role === "extracto") {
      previewExtracto = { ...(previewExtracto || {}), confirmed: true };
    } else {
      previewContable = { ...(previewContable || {}), confirmed: true };
    }
  } catch {
    showToast("error", `No se pudo confirmar (${role}).`);
  } finally {
    if (role === "extracto") confirmBusyExtracto = false;
    else confirmBusyContable = false;
  }
}

async function startReconcileDirect() {
  if (!(previewExtracto?.confirmed && previewContable?.confirmed)) {
    showToast("warning", "Faltan confirmar ambos archivos.");
    return;
  }
  // limpiamos resultados previos y prendemos spinner
  results = null;
  reconciling = true;

  const fd = new FormData();
  const currentDaysWindow = get(daysWindowStore) ?? DEFAULT_DAYS_WINDOW;

  fd.set("threadId", threadId);
  fd.set("uri_extracto", previewExtracto.canonical_uri || previewExtracto.original_uri || "");
  fd.set("uri_contable", previewContable.canonical_uri || previewContable.original_uri || "");
  fd.set("days_window", String(currentDaysWindow));

  try {
    const res = await fetch(`${URL_REST}/api/reconcile/start`, { method: "POST", body: fd });
    if (!res.ok) {
      reconciling = false; // IMPORTANTE: apagar spinner si el POST falla
      throw new Error(`HTTP ${res.status}`);
    }
    const j = await res.json();
    // El summary llega por SSE (RESULTS_READY). Como fallback mostramos si vino en el body:
    if (j?.summary && !results) {
      results = j.summary;
      if (results?.days_window != null) {
        daysWindowStore.set(normalizeDaysWindow(results.days_window));
      }
      reconciling = false;
    }
  } catch {
    reconciling = false;
    showToast("error", "No se pudo iniciar la conciliación.");
  }
}

async function sendWizardAction(actionType: string, payload: Record<string, any>) {
  if (!wizardRunId) return;
  try {
    const res = await fetch(`${URL_REST}/api/reconcile_wizard/runs/${wizardRunId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_type: actionType, payload }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch {
    showToast("error", "No se pudo enviar la acción del wizard.");
  }
}

async function startWizard() {
  if (!(previewExtracto?.confirmed && previewContable?.confirmed)) {
    showToast("warning", "Faltan confirmar ambos archivos.");
    return;
  }
  wizardOpen = true;
  wizardStatus = "opening";
  wizardError = null;
  wizardBusy = true;
  wizardInitializing = true;
  wizardEvents = [];
  wizardRunId = null;
  wizardThreadId = null;
  wizardSseUrl = null;
  wizardNeedsAccount = false;
  wizardNeedsBank = false;
  wizardAlerts = [];
  wizardForm = null;
  wizardListItems = [];
  wizardConfirm = null;
  wizardState = null;
  wizardStepTitle = "";
  wizardStepId = "SCOPE";
  wizardScopeMode = "ALL";
  wizardMonths = [];
  wizardWindowFrom = "";
  wizardWindowTo = "";
  const detectedBank = resolveWizardBank();
  const detectedAccount = resolveWizardAccount();
  const datasetRef = resolveWizardDatasetRef();
  wizardBankInput = detectedBank || wizardBankInput;
  wizardAccountInput = detectedAccount || wizardAccountInput;
  wizardBankInput = (wizardBankInput || "").trim();
  wizardAccountInput = (wizardAccountInput || "").trim();
  if (!wizardBankInput) {
    wizardStatus = "error";
    wizardNeedsBank = true;
    wizardError = "Banco no detectado. Revisá la vista previa antes de continuar.";
    wizardInitializing = false;
    wizardBusy = false;
    return;
  }
  if (!wizardAccountInput) {
    wizardStatus = "error";
    wizardNeedsAccount = true;
    wizardError = "Cuenta no detectada. Completá la cuenta para iniciar el asistente.";
    wizardInitializing = false;
    wizardBusy = false;
    return;
  }
  if (!datasetRef) {
    wizardStatus = "error";
    wizardError = "Dataset canónico no disponible. Esperá a que termine la canonicalización.";
    wizardInitializing = false;
    wizardBusy = false;
    return;
  }
  try {
    wizardStatus = "starting";
    const payload = {
      workspace_id: previewExtracto?.workspace_id || previewContable?.workspace_id || "",
      bank: wizardBankInput,
      account: wizardAccountInput,
      dataset_ref: datasetRef,
    };
    const res = await fetch(`${URL_REST}/api/reconcile_wizard/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    if (j?.status && !["ok", "started"].includes(j.status)) {
      throw new Error(`status ${j.status}`);
    }
    if (j?.ok === false) {
      throw new Error(j?.message || "respuesta inválida");
    }
    wizardRunId = j?.run_id || null;
    wizardThreadId = j?.thread_id || null;
    wizardSseUrl = j?.sse_url || null;
    if (!wizardRunId) throw new Error("run_id vacío");
    connectWizardSSE(wizardRunId, wizardSseUrl);
    if (wizardThreadId) connectWizardNotifySSE(wizardThreadId);
  } catch {
    wizardStatus = "error";
    wizardError = "No se pudo iniciar el asistente. Reintentá en unos segundos.";
    showToast("error", "No se pudo iniciar el asistente.");
    wizardInitializing = false;
  } finally {
    wizardBusy = false;
  }
}

function retryWizard() {
  wizardError = null;
  if (wizardRunId) {
    wizardStatus = "starting";
    wizardInitializing = true;
    connectWizardSSE(wizardRunId, wizardSseUrl);
    return;
  }
  startWizard();
}

function toggleMonth(month: string) {
  if (wizardMonths.includes(month)) {
    wizardMonths = wizardMonths.filter((m) => m !== month);
  } else {
    wizardMonths = [...wizardMonths, month];
  }
}

async function onWizardScopeNext() {
  const modeApi = (wizardScopeMode === "ALL")
    ? "ALL_RANGE"
    : (wizardScopeMode === "RANGE" ? "WINDOW" : wizardScopeMode);
  if (wizardScopeMode === "ALL") {
    await sendWizardAction("SELECT_SCOPE", { mode: modeApi });
    return;
  }
  if (wizardScopeMode === "MONTHS") {
    await sendWizardAction("SELECT_SCOPE", { mode: modeApi });
    return;
  }
  if (wizardScopeMode === "RANGE") {
    await sendWizardAction("SELECT_SCOPE", {
      mode: modeApi,
    });
  }
}

async function onWizardSelectionNext() {
  if (wizardStepId === "MONTHS") {
    if (!wizardMonths.length) {
      showToast("warning", "Seleccioná al menos un mes.");
      return;
    }
    await sendWizardAction("SELECT_SCOPE", { mode: "MONTHS", months: wizardMonths });
    return;
  }
  if (wizardStepId === "WINDOW") {
    if (!wizardWindowFrom || !wizardWindowTo) {
      showToast("warning", "Seleccioná un rango válido.");
      return;
    }
    await sendWizardAction("SELECT_SCOPE", { mode: "WINDOW", from: wizardWindowFrom, to: wizardWindowTo });
  }
}

async function onWizardConfirmSelection() {
  if (!wizardConfirm) return;
  await sendWizardAction("CONFIRM_START", { kind: wizardConfirm?.kind || "confirm" });
}

async function onWizardConfirmStart() {
  await sendWizardAction("CONFIRM_START", { kind: "start" });
  wizardOpen = false;
  showToast("info", "Configuración enviada. Esperando inicio...");
}

$effect(() => {
  if (typeof window === "undefined") return;
  connectSSE();
});
</script>

<!-- Chat -->
<section class="card bg-base-100 border border-base-300 shadow-sm">
  <div class="card-body gap-3">
    <div class="flex items-center gap-2">
      <h2 class="font-semibold text-lg">Asistente de Conciliación</h2>
      <span class="badge">concilia</span>
    </div>

    <div class="flex flex-col gap-2">
      <div class="flex gap-2">
        <button class="btn btn-active btn-primary btn-xs" on:click|preventDefault={() => onSendText("subir extracto")}>
          Subir extracto
        </button>
        <button class="btn btn-active btn-primary btn-xs" on:click|preventDefault={() => onSendText("subir contable")}>
          Subir contable
        </button>
      </div>
      <textarea
        class="textarea textarea-bordered w-full"
        bind:value={chatInput}
        placeholder="Escribí: 'subir extracto' o 'subir contable' (Ctrl/Cmd + Enter)"
        rows="3"
        spellcheck="false"
        on:keydown={onKeydownChat}
      />
      <div class="flex justify-end">
        <button class="btn btn-primary" on:click|preventDefault={onSendText} disabled={sending} aria-busy={sending}>
          {#if sending}
            <span class="loading loading-spinner loading-sm mr-2" /> Procesando…
          {:else}
            Enviar
          {/if}
        </button>
      </div>
    </div>
  </div>
</section>

<!-- Modal de Upload -->
<dialog class="modal" bind:this={dialogRef} on:close={() => (dialogOpen = false)}>
  <div class="modal-box max-w-3xl">
    <h3 class="font-bold text-lg">{formSpec?.title || "Subí el archivo para analizar"}</h3>
    {#if formSpec?.hint}<p class="opacity-70 text-sm mb-2">{formSpec.hint}</p>{/if}

    <div class="grid grid-cols-1 gap-3">
      <label class="label"><span class="label-text">Archivo *</span></label>
      <input
        class="file-input file-input-bordered w-full"
        type="file"
        multiple
        accept={formSpec?.fields?.[0]?.accept || ".xlsx,.xls,.csv"}
        on:change={(e:any)=>{fileObjs = Array.from(e?.target?.files || []);}}
        bind:this={fileInputRef}
        disabled={uploadBusy}
      />
    </div>

    <div class="modal-action">
      <button class="btn btn-primary" on:click|preventDefault={onSubmitUpload} disabled={uploadBusy} aria-busy={uploadBusy}>
        {#if uploadBusy}
          <span class="loading loading-spinner loading-sm mr-2" />
        {/if}
        {formSpec?.submit?.label || "Subir y analizar"}
      </button>
      <form method="dialog">
        <button class="btn" on:click={() => (dialogOpen = false)} disabled={uploadBusy}>Cerrar</button>
      </form>
    </div>
  </div>
</dialog>

<!-- Modal Wizard -->
<dialog class="modal" bind:this={wizardDialogRef} on:close={() => (wizardOpen = false)}>
  <div class="modal-box max-w-3xl">
    <div class="flex items-center justify-between gap-2">
      <h3 class="font-bold text-lg">Asistente de Conciliación</h3>
      <span class="badge">Paso {wizardStepIndex()}/3</span>
    </div>
    {#if wizardStepTitle}
      <p class="text-sm opacity-70 mt-1">{wizardStepTitle}</p>
    {/if}
    {#if wizardEvents.length}
      <p class="text-xs opacity-60 mt-1">
        Último evento: {wizardEvents[wizardEvents.length - 1]?.type || "—"}
      </p>
    {/if}
    {#if wizardStatus === "error" && wizardError}
      <div class="alert alert-error text-sm mt-3">
        <div class="flex flex-col gap-2 w-full">
          <span>{wizardError}</span>
          {#if wizardNeedsBank || wizardNeedsAccount}
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
              <label class="flex flex-col gap-1">
                <span class="opacity-70">Banco</span>
                <input class="input input-bordered input-sm" type="text" bind:value={wizardBankInput} />
              </label>
              <label class="flex flex-col gap-1">
                <span class="opacity-70">Cuenta</span>
                <input class="input input-bordered input-sm" type="text" bind:value={wizardAccountInput} />
              </label>
            </div>
          {/if}
          <div>
            <button class="btn btn-sm btn-primary" on:click|preventDefault={retryWizard} disabled={wizardBusy}>
              Reintentar
            </button>
          </div>
        </div>
      </div>
    {/if}
    {#if wizardInitializing}
      <div class="alert alert-info text-sm mt-3">
        <span>Inicializando asistente…</span>
      </div>
    {/if}

    {#if wizardStepIndex() === 1}
      {#if wizardState?.context?.preview}
        <div class="mt-4 text-sm space-y-2">
          <div>
            <span class="font-semibold">Ventana maxima detectada:</span>
            {wizardState.context.preview.range?.[0]} → {wizardState.context.preview.range?.[1]}
          </div>
          {#if (wizardState.context.preview.missing_months || []).length}
            <div>
              <span class="font-semibold">Meses faltantes:</span>
              {wizardState.context.preview.missing_months.join(", ")}
            </div>
          {/if}
          {#if (wizardState.context.preview.partial_months || []).length}
            <div>
              <span class="font-semibold">Meses parciales:</span>
              {wizardState.context.preview.partial_months.map((m:any)=>m.month).join(", ")}
            </div>
          {/if}
          {#if (wizardState.context.preview.gaps || []).length}
            <div>
              <span class="font-semibold">Gaps detectados:</span>
              {wizardState.context.preview.gaps.map((g:any)=>`${g.from} → ${g.to}`).join(", ")}
            </div>
          {/if}
          {#if (wizardState.context.preview.outliers || []).length}
            <div>
              <span class="font-semibold">Outliers:</span>
              {wizardState.context.preview.outliers.map((o:any)=>o.date).join(", ")}
            </div>
          {/if}
        </div>
      {/if}

      {#if wizardAlerts.length}
        <div class="alert alert-warning text-sm mt-3">
          <div>
            <span class="font-semibold">Atención:</span>
            <ul class="list-disc ml-6">
              {#each wizardAlerts as alert}
                <li>{alert?.message || "Revisar cobertura y outliers."}</li>
              {/each}
            </ul>
          </div>
        </div>
      {/if}

      <div class="mt-4 space-y-2">
        <p class="font-semibold">Elegí el alcance</p>
        <label class="flex items-center gap-2">
          <input type="radio" bind:group={wizardScopeMode} value="ALL" />
          <span>Todo el rango detectado</span>
        </label>
        <label class="flex items-center gap-2">
          <input type="radio" bind:group={wizardScopeMode} value="MONTHS" />
          <span>Elegir meses</span>
        </label>
        <label class="flex items-center gap-2">
          <input type="radio" bind:group={wizardScopeMode} value="RANGE" />
          <span>Ventana por rango de fechas</span>
        </label>
      </div>

      <div class="modal-action">
        <button
          class="btn btn-primary"
          on:click|preventDefault={onWizardScopeNext}
          disabled={wizardBusy || !wizardRunId || wizardStatus !== "ready" || !wizardState}
        >
          Continuar
        </button>
        <form method="dialog">
          <button class="btn" on:click={() => (wizardOpen = false)}>Cerrar</button>
        </form>
      </div>
    {:else if wizardStepIndex() === 2}
      {#if wizardStepId === "MONTHS"}
        <div class="mt-3 space-y-2">
          <p class="font-semibold text-sm">Seleccioná meses disponibles</p>
          {#if !wizardListItems.length}
            <p class="text-sm opacity-70">Cargando meses…</p>
          {:else}
            {#each wizardListItems as item}
              <label class="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  disabled={!item.selectable}
                  checked={wizardMonths.includes(item.month)}
                  on:change={() => toggleMonth(item.month)}
                />
                <span>{item.month}</span>
                <span class="badge badge-outline">{item.status}</span>
                {#if item.status === "partial" && (item.missing_days || []).length}
                  <span class="opacity-60">faltan {item.missing_days.length} dias</span>
                {/if}
              </label>
            {/each}
          {/if}
        </div>
      {:else}
        <div class="mt-3 space-y-2 text-sm">
          <p class="font-semibold">Definí ventana</p>
          <div class="grid grid-cols-2 gap-3">
            <label class="flex flex-col gap-1">
              <span class="opacity-70">Desde</span>
              <input class="input input-bordered input-sm" type="date" bind:value={wizardWindowFrom} />
            </label>
            <label class="flex flex-col gap-1">
              <span class="opacity-70">Hasta</span>
              <input class="input input-bordered input-sm" type="date" bind:value={wizardWindowTo} />
            </label>
          </div>
        </div>
      {/if}

      {#if wizardConfirm}
        <div class="alert alert-warning text-sm mt-3">
          <div>
            <span class="font-semibold">Confirmación requerida.</span>
            <div>{wizardConfirm?.message || "Confirmá para continuar."}</div>
            <button
              class="btn btn-sm btn-warning mt-2"
              on:click|preventDefault={onWizardConfirmSelection}
              disabled={wizardBusy || !wizardRunId || wizardStatus !== "ready" || !wizardState}
            >
              Confirmar selección
            </button>
          </div>
        </div>
      {/if}

      <div class="modal-action">
        <button
          class="btn btn-primary"
          on:click|preventDefault={onWizardSelectionNext}
          disabled={wizardBusy || !wizardRunId || wizardStatus !== "ready" || !wizardState}
        >
          Continuar
        </button>
        <form method="dialog">
          <button class="btn" on:click={() => (wizardOpen = false)}>Cerrar</button>
        </form>
      </div>
    {:else}
      <div class="mt-3 space-y-2 text-sm">
        <p class="font-semibold">Resumen</p>
        <div><span class="font-semibold">Meses:</span> {(wizardState?.selection?.months || []).join(", ") || "N/A"}</div>
        <div>
          <span class="font-semibold">Ventana:</span>
          {#if wizardState?.selection?.window_range}
            {wizardState.selection.window_range.from} → {wizardState.selection.window_range.to}
          {:else}
            rango completo
          {/if}
        </div>
        <div>
          <span class="font-semibold">Rango detectado:</span>
          {wizardState?.context?.preview?.range?.[0]} → {wizardState?.context?.preview?.range?.[1]}
        </div>
        <div>
          <span class="font-semibold">Archivos:</span>
          {(wizardState?.context?.preview?.files || []).length}
        </div>
      </div>

      <div class="modal-action">
        <button
          class="btn btn-primary"
          on:click|preventDefault={onWizardConfirmStart}
          disabled={wizardBusy || !wizardRunId || wizardStatus !== "ready" || !wizardState}
        >
          Confirmar e iniciar
        </button>
        <form method="dialog">
          <button class="btn" on:click={() => (wizardOpen = false)}>Cerrar</button>
        </form>
      </div>
    {/if}
  </div>
</dialog>

<!-- Card PREVIEW: Extracto -->
{#if previewExtracto}
  <section class="card bg-base-100 border border-base-300 shadow-sm mt-4">
    <div class="card-body">
      <div class="flex items-center gap-2">
        <h3 class="font-semibold text-lg">Vista previa — Extracto</h3>
        <span class="badge">bank_movements</span>
      </div>

      {#if previewExtracto?.validation}
        {#if previewExtracto.validation.is_valid === false}
          <div class="alert alert-error text-sm mt-2">
            <div>
              <span class="font-semibold">El archivo no pasa validación de extracto.</span>
              {#if (previewExtracto.validation.errors || []).length}
                <ul class="list-disc ml-6">
                  {#each previewExtracto.validation.errors as err}
                    <li>{err}</li>
                  {/each}
                </ul>
              {/if}
            </div>
          </div>
        {:else}
          <div class="alert alert-success text-sm mt-2">
            <span>Estructura de extracto detectada.</span>
            {#if (previewExtracto.validation.warnings || []).length}
              <ul class="list-disc ml-6">
                {#each previewExtracto.validation.warnings as warn}
                  <li>{warn}</li>
                {/each}
              </ul>
            {/if}
          </div>
        {/if}
      {/if}

      {#if previewExtracto?.meta?.coverage}
        {@const missingMonths = previewExtracto.meta.coverage?.missing_months || []}
        {@const gaps = previewExtracto.meta.coverage?.gaps || []}
        {@const partialMonths = previewExtracto.meta.coverage?.partial_months || []}
        {@const overlap = previewExtracto.meta.coverage?.overlap || null}
        {#if (missingMonths.length || gaps.length || partialMonths.length)}
          <div class="alert alert-warning text-sm mt-2">
            <div>
              <span class="font-semibold">Cobertura incompleta.</span>
              {#if overlap?.days_total}
                <div class="mt-1">
                  <span class="opacity-70">Solapamiento de fechas entre archivos:</span>
                  <b>{overlap.days_total}</b>
                  <span class="opacity-70">día(s)</span>
                </div>
              {/if}
              {#if missingMonths.length}
                <div class="mt-1">
                  <span class="opacity-70">Meses faltantes:</span>
                  <b>{missingMonths.join(", ")}</b>
                </div>
              {/if}
              {#if partialMonths.length}
                <div class="mt-1 opacity-70">Meses parciales (por días con movimientos):</div>
                <ul class="list-disc ml-6">
                  {#each partialMonths as pm (pm.month)}
                    <li>
                      {pm.month}: faltan {pm.missing_days} de {pm.total_days} días
                      {#if Array.isArray(pm.missing_ranges) && pm.missing_ranges.length}
                        <span class="opacity-70">
                          (
                          {#each pm.missing_ranges.slice(0, 4) as r, i (r.from)}
                            {#if i > 0}; {/if}{r.from} → {r.to}
                          {/each}
                          {#if pm.missing_ranges.length > 4}
                            ; +{pm.missing_ranges.length - 4} más
                          {/if}
                          )
                        </span>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}
              {#if gaps.length}
                <div class="mt-1 opacity-70">Gaps detectados (por meses):</div>
                <ul class="list-disc ml-6">
                  {#each gaps as g (g.from)}
                    <li>{g.from} → {g.to} ({g.days} días)</li>
                  {/each}
                </ul>
              {/if}
            </div>
          </div>
        {/if}
      {/if}

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm mt-1">
        <div><span class="opacity-70">Banco:</span> <b>{previewExtracto?.detected?.bank || "—"}</b></div>
        <div><span class="opacity-70">Cuenta:</span> <b>{previewExtracto?.detected?.account_full || previewExtracto?.detected?.account_core_dv || "—"}</b></div>
        <div><span class="opacity-70">Archivos:</span> <b>{previewExtracto?.meta?.uploads_count ?? 1}</b></div>
        <div><span class="opacity-70">Rango:</span> <b>{previewExtracto?.suggest?.period_from || previewExtracto?.detected?.period_from || "—"} → {previewExtracto?.suggest?.period_to || previewExtracto?.detected?.period_to || "—"}</b></div>
        <div class="md:col-span-2 text-xs opacity-60">
          meta.path: {previewExtracto?.meta?.path || "—"} · meta.filename: {previewExtracto?.meta?.filename || "—"}
        </div>
        {#if Array.isArray(previewExtracto?.meta?.uploads) && previewExtracto.meta.uploads.length}
          {@const uploadsSorted = [...previewExtracto.meta.uploads].sort((a:any, b:any) => {
            const da = (a?.period_from || "").toString();
            const db = (b?.period_from || "").toString();
            if (da && db && da !== db) return da < db ? -1 : 1;
            if (da && !db) return -1;
            if (!da && db) return 1;
            const fa = (a?.filename || "").toString();
            const fb = (b?.filename || "").toString();
            return fa.localeCompare(fb);
          })}
          {#if (previewExtracto?.meta?.uploads_count ?? previewExtracto.meta.uploads.length) > 1}
            <div class="md:col-span-2">
              <details class="mt-1">
                <summary class="cursor-pointer opacity-70">Ver archivos ({previewExtracto?.meta?.uploads_count ?? previewExtracto.meta.uploads.length})</summary>
                <ul class="list-disc ml-6 mt-1">
                  {#each uploadsSorted as u (u.original_uri)}
                    <li>
                      {u.filename}
                      {#if u.period_from || u.period_to}
                        <span class="opacity-70">
                          {" "}({u.period_from || "—"} a {u.period_to || "—"}{#if u.days_present != null}, días: {u.days_present}{/if})
                        </span>
                      {/if}
                    </li>
                  {/each}
                </ul>
              </details>
            </div>
          {:else}
            {@const u0 = uploadsSorted[0]}
            <div class="md:col-span-2">
              <span class="opacity-70">Archivo subido:</span>
              <b>{u0?.filename || "—"}</b>
              <span class="opacity-70">
                {" "}({u0?.period_from || "—"} a {u0?.period_to || "—"}{#if u0?.days_present != null}, días: {u0.days_present}{/if})
              </span>
            </div>
          {/if}
        {/if}
        <div class="md:col-span-2">
          <span class="opacity-70">Header:</span>
          <span class="whitespace-pre-wrap">{previewExtracto?.detected?.header_excerpt || "—"}</span>
        </div>
      </div>

      <div class="mt-3 flex gap-2 items-center">
        {#if !previewExtracto?.confirmed}
          <button class="btn btn-primary" on:click|preventDefault={()=>onConfirmPreview("extracto")} disabled={confirmBusyExtracto || (previewExtracto?.validation?.is_valid === false)}>
            {#if confirmBusyExtracto}<span class="loading loading-spinner loading-sm mr-2" />{:else}Confirmar y procesar{/if}
          </button>
        {:else}
          <span class="badge badge-success">Confirmado</span>
        {/if}
        <button class="btn btn-ghost" on:click={() => (previewExtracto = null)}>Descartar</button>
      </div>
    </div>
  </section>
{/if}

<!-- Card PREVIEW: Contable -->
{#if previewContable}
  <section class="card bg-base-100 border border-base-300 shadow-sm mt-4">
    <div class="card-body">
      <div class="flex items-center gap-2">
        <h3 class="font-semibold text-lg">Vista previa — Contable (PILAGA)</h3>
        <span class="badge">gl</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm mt-1">
        <div><span class="opacity-70">Banco:</span> <b>{previewContable?.detected?.bank || "—"}</b></div>
        <div><span class="opacity-70">Cuenta:</span> <b>{previewContable?.detected?.account_full || previewContable?.detected?.account_core_dv || "—"}</b></div>
        <div><span class="opacity-70">Rango:</span> <b>{previewContable?.suggest?.period_from || previewContable?.detected?.period_from || "—"} → {previewContable?.suggest?.period_to || previewContable?.detected?.period_to || "—"}</b></div>
        <div class="md:col-span-2">
          <span class="opacity-70">Header:</span>
          <span class="whitespace-pre-wrap">{previewContable?.detected?.header_excerpt || "—"}</span>
        </div>
      </div>

      {#if previewContable?.validation}
        {#if previewContable.validation.is_valid === false}
          <div class="alert alert-error text-sm mt-2">
            <div>
              <span class="font-semibold">El archivo no pasa validación contable.</span>
              {#if (previewContable.validation.errors || []).length}
                <ul class="list-disc ml-6">
                  {#each previewContable.validation.errors as err}
                    <li>{err}</li>
                  {/each}
                </ul>
              {/if}
            </div>
          </div>
        {:else}
          <div class="alert alert-success text-sm mt-2">
            <span>Formato contable detectado.</span>
            {#if (previewContable.validation.warnings || []).length}
              <ul class="list-disc ml-6">
                {#each previewContable.validation.warnings as warn}
                  <li>{warn}</li>
                {/each}
              </ul>
            {/if}
          </div>
        {/if}
      {/if}

      <div class="mt-3 flex gap-2 items-center">
        {#if !previewContable?.confirmed}
          <button class="btn btn-primary" on:click|preventDefault={()=>onConfirmPreview("contable")} disabled={confirmBusyContable || (previewContable?.validation?.is_valid === false)}>
            {#if confirmBusyContable}<span class="loading loading-spinner loading-sm mr-2" />{:else}Confirmar y procesar{/if}
          </button>
        {:else}
          <span class="badge badge-success">Confirmado</span>
        {/if}
        <button class="btn btn-ghost" on:click={() => (previewContable = null)}>Descartar</button>
      </div>
    </div>
  </section>
{/if}

<!-- CTA: Iniciar conciliación -->
{#if previewExtracto?.confirmed && previewContable?.confirmed}
  <div class="mt-4 flex">
    <button class="btn btn-primary" on:click|preventDefault={startWizard} disabled={wizardBusy || reconciling} aria-busy={wizardBusy || reconciling}>
      {#if wizardBusy}
        <span class="loading loading-spinner loading-sm mr-2" /> Abriendo…
      {:else}
        Abrir asistente de conciliación
      {/if}
    </button>
  </div>
{/if}

<!-- Resultados -->
{#if results}
  <ReconciliarResumen client:load uriExtracto={previewExtracto?.original_uri} uriContable={previewContable?.original_uri} />
  <!-- Detalle separado, consumiendo /api/reconcile/details -->
  <ReconciliarDetalle
    urlRest={URL_REST}
    threadId={threadId}
    extractoUri={previewExtracto?.original_uri}
    contableUri={previewContable?.original_uri}
    summary={results}
    client:load
  />  
{/if}

{#if toast}
  <div class="toast toast-end">
    <div class={"alert " + (
      toast.level === "success" ? "alert-success" :
      toast.level === "warning" ? "alert-warning" :
      toast.level === "error" ? "alert-error" : "alert-info"
    )}>
      <span>{toast.message}</span>
    </div>
  </div>
{/if}
