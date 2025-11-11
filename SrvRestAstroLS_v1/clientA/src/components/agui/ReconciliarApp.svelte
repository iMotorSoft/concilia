<script lang="ts">
  // src/components/agui/ReconciliarApp.svelte
  import { URL_REST } from '../global';

  // ===== Estado =====
  let chatInput = $state("");
  let sending   = $state(false);

  let dialogOpen = $state(false);
  let dialogRef: HTMLDialogElement | null = null;

  let formSpec: any = $state(null);
  let formValues: Record<string, any> = $state({});
  let fileObj: File | null = $state(null);

  // Previews
  let previewExtracto: any = $state(null);
  let previewContable: any = $state(null);

  // Ready & Resultados
  let readyToReconcile = $state(false);
  let readyMeta: any = $state(null);
  let startingRecon = $state(false);
  let resultSummary: any = $state(null);

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

  function seedFormDefaults(spec: any) {
    const d: Record<string, any> = {};
    for (const f of (spec?.fields ?? [])) {
      if (f.type === "file") continue;
      d[f.name] = ("default" in f && f.default != null) ? f.default : "";
    }
    formValues = d;
    fileObj = null;
  }

  function connectSSE() {
    if (es) es.close();
    es = new EventSource(`${URL_REST}/api/ag-ui/notify/stream?threadId=${encodeURIComponent(threadId)}`);
    es.onmessage = (ev) => {
      try { handle(JSON.parse(ev.data)); } catch {}
    };
    es.onerror = () => showToast("error", "Conexión SSE caída.");
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
      const role = msg?.payload?.role;
      if (role === "extracto") {
        previewExtracto = msg?.payload;
      } else if (role === "contable") {
        previewContable = msg?.payload;
      } else {
        previewExtracto = msg?.payload; // fallback
      }
      dialogOpen = false;
      showToast("info", "Vista previa lista. Revisá y confirmá.");
      return;
    }

    if (t === "READY_TO_RECONCILE") {
      readyToReconcile = true;
      readyMeta = msg?.payload || null;
      showToast("success", "Listo para conciliar. Podés iniciar el proceso.");
      return;
    }

    if (t === "RUN_START") {
      showToast("success", "Iniciando conciliación…");
      return;
    }

    if (t === "RESULT_READY") {
      resultSummary = msg?.payload || { note: "Sin datos" };
      showToast("success", "Resultados disponibles.");
      return;
    }

    if (t === "TEXT_MESSAGE_CONTENT" && msg.delta) {
      showToast("info", msg.delta);
      return;
    }
  }

  async function onSendText() {
    const text = (chatInput || "").trim();
    if (!text || sending) return;
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
    if (!fileObj) { showToast("warning", "Seleccioná un archivo."); return; }
    fd.set("file", fileObj, fileObj.name);

    try {
      const roleDefault = formSpec?.payload?.role ?? "extracto";
      const endpoint = formSpec?.submit?.endpoint || `/api/uploads/v2/ingest?role=${encodeURIComponent(roleDefault)}`;
      const method = formSpec?.submit?.method || "POST";

      const res = await fetch(`${URL_REST}${endpoint}`, { method, body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      showToast("success", j?.message || "Archivo recibido.");
    } catch {
      showToast("error", "No se pudo subir el archivo.");
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

      // Marcar card como confirmada
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

  // ===== Iniciar conciliación =====
  async function onStartReconcile() {
    if (!readyToReconcile) return;
    startingRecon = true;
    try {
      const fd = new FormData();
      fd.set("threadId", threadId);
      const res = await fetch(`${URL_REST}/api/reconcile/start`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      showToast("success", j?.message || "Conciliación iniciada.");
    } catch {
      showToast("error", "No se pudo iniciar la conciliación.");
    } finally {
      startingRecon = false;
    }
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
        accept={formSpec?.fields?.[0]?.accept || ".xlsx,.xls,.csv"}
        on:change={(e:any)=>{fileObj = e?.target?.files?.[0] || null;}}
      />
    </div>

    <div class="modal-action">
      <button class="btn btn-primary" on:click|preventDefault={onSubmitUpload}>
        {formSpec?.submit?.label || "Subir y analizar"}
      </button>
      <form method="dialog">
        <button class="btn" on:click={() => (dialogOpen = false)}>Cerrar</button>
      </form>
    </div>
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

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm mt-1">
        <div><span class="opacity-70">Banco:</span> <b>{previewExtracto?.detected?.bank || "—"}</b></div>
        <div><span class="opacity-70">Cuenta:</span> <b>{previewExtracto?.detected?.account_full || previewExtracto?.detected?.account_core_dv || "—"}</b></div>
        <div><span class="opacity-70">Rango:</span> <b>{previewExtracto?.suggest?.period_from || previewExtracto?.detected?.period_from || "—"} → {previewExtracto?.suggest?.period_to || previewExtracto?.detected?.period_to || "—"}</b></div>
        <div class="md:col-span-2">
          <span class="opacity-70">Header:</span>
          <span class="whitespace-pre-wrap">{previewExtracto?.detected?.header_excerpt || "—"}</span>
        </div>
      </div>

      <div class="mt-3 flex gap-2 items-center">
        {#if !previewExtracto?.confirmed}
          <button class="btn btn-primary" on:click|preventDefault={()=>onConfirmPreview("extracto")} disabled={confirmBusyExtracto}>
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

      <div class="mt-3 flex gap-2 items-center">
        {#if !previewContable?.confirmed}
          <button class="btn btn-primary" on:click|preventDefault={()=>onConfirmPreview("contable")} disabled={confirmBusyContable}>
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

<!-- Card RESULTADOS / INICIO -->
{#if readyToReconcile}
  <section class="card bg-base-100 border border-base-300 shadow-sm mt-4">
    <div class="card-body">
      <div class="flex items-center gap-2">
        <h3 class="font-semibold text-lg">Resultados de Conciliación</h3>
        <span class="badge">Listo para iniciar</span>
      </div>

      <div class="text-sm opacity-80">
        <div>Periodo: <b>{readyMeta?.period?.from || "—"} → {readyMeta?.period?.to || "—"}</b></div>
        <div>Banco (consenso): <b>{readyMeta?.bank || "—"}</b></div>
      </div>

      <div class="mt-3 flex items-center gap-2">
        <button class="btn btn-primary" on:click|preventDefault={onStartReconcile} disabled={startingRecon}>
          {#if startingRecon}<span class="loading loading-spinner loading-sm mr-2" />{:else}Iniciar conciliación{/if}
        </button>
      </div>

      {#if resultSummary}
        <div class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div class="stat border rounded-lg p-3">
            <div class="stat-title">Coincidencias</div>
            <div class="stat-value text-base">{resultSummary.matches ?? 0}</div>
          </div>
          <div class="stat border rounded-lg p-3">
            <div class="stat-title">Solo banco</div>
            <div class="stat-value text-base">{resultSummary.bank_only ?? 0}</div>
          </div>
          <div class="stat border rounded-lg p-3">
            <div class="stat-title">Solo contable</div>
            <div class="stat-value text-base">{resultSummary.gl_only ?? 0}</div>
          </div>
          {#if resultSummary.note}
            <div class="md:col-span-3 opacity-70 mt-1">{resultSummary.note}</div>
          {/if}
        </div>
      {/if}
    </div>
  </section>
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

