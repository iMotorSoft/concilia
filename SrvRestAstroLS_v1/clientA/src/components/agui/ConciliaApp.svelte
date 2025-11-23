<script lang="ts">
  // Chat → evento (modal de upload) → upload (multipart) → INGEST_PREVIEW (card) → Confirmar → RUN_START
  import { URL_REST } from '../global';

  // ===== Tipos simples (evitamos TS inline compleja) =====
  type ToastLevel = 'info' | 'success' | 'warning' | 'error';
  interface Toast { level: ToastLevel; message: string }
  interface FormField {
    name: string;
    label?: string;
    type: 'text'|'select'|'file';
    required?: boolean;
    placeholder?: string;
    accept?: string;
    options?: Array<{label:string; value:string}|string>;
    default?: string;
  }
  interface FormSpec {
    title?: string;
    hint?: string;
    fields: FormField[];
    submit?: { endpoint: string; method?: string; label?: string };
  }

  // ===== Runes state =====
  let chatInput = $state<string>("");
  let sending   = $state<boolean>(false);

  // Modal (subida de archivo)
  let dialogOpen = $state<boolean>(false);
  let dialogRef: HTMLDialogElement | null = null;

  // Especificación del form + valores + archivo
  let formSpec = $state<FormSpec | null>(null);
  let formValues = $state<Record<string, any>>({});
  let fileObj = $state<File | null>(null);

  // SSE + toast
  let es: EventSource | null = null;
  let toast = $state<Toast | null>(null);
  let toastTimer: any = null;

  // Vista previa luego del upload
  let preview = $state<any>(null);
  let confirmBusy  = $state<boolean>(false);

  // Identidad (topic SSE)
  const threadId = crypto?.randomUUID?.() ?? `t-concilia-${Date.now()}`;

  // ===== Helpers =====
  function showToast(level: ToastLevel, message: string) {
    toast = { level, message };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2600);
  }

  $effect(() => {
    if (typeof window === "undefined" || !dialogRef) return;
    if (dialogOpen && !dialogRef.open) dialogRef.showModal?.();
    if (!dialogOpen && dialogRef.open) dialogRef.close?.();
  });

  function seedFormDefaults(spec: FormSpec) {
    const defaults: Record<string, any> = {};
    for (const f of (spec?.fields ?? [])) {
      if (f.type === "file") continue;
      if ("default" in f && f.default != null) defaults[f.name] = f.default;
      else if (f.type === "select" && Array.isArray(f.options) && f.options.length > 0) {
        const opt = f.options[0] as any;
        defaults[f.name] = (typeof opt === "object") ? (opt.value ?? "") : opt;
      } else defaults[f.name] = "";
    }
    formValues = defaults;
    fileObj = null;
  }

  // ===== SSE =====
  function connectSSE() {
    if (es) es.close();
    es = new EventSource(`${URL_REST}/api/ag-ui/notify/stream?threadId=${encodeURIComponent(threadId)}`, { withCredentials: false });
    es.onmessage = (ev) => {
      try { handle(JSON.parse(ev.data)); } catch {}
    };
    es.onerror = () => showToast("error", "Conexión SSE caída. Recargá la página.");
  }

  function handle(msg: any) {
    const t = (msg?.type || "").toUpperCase();

    if (t === "DEBUG" && msg.stage === "CONNECTED") {
      showToast("info", `SSE conectado (${msg.threadId})`);
      return;
    }

    // Abrir modal con formulario de subida
    if (t === "TEXT_MESSAGE_REQUEST_UPLOAD") {
      formSpec = (msg?.payload?.form || null) as FormSpec | null;
      if (formSpec) seedFormDefaults(formSpec);
      dialogOpen = true;
      preview = null;
      return;
    }

    // Recibimos vista previa tras el upload (sniff server-side)
    if (t === "INGEST_PREVIEW") {
      dialogOpen = false;
      preview = msg?.payload || null;
      showToast("info", "Revisá la vista previa antes de procesar.");
      return;
    }

    if (t === "RUN_START") {
      showToast("success", "Análisis iniciado. Procesando…");
      return;
    }

    if (t === "TEXT_MESSAGE_CONTENT" && msg.delta) {
      showToast("info", msg.delta);
      return;
    }

    if (t === "DIALOG_SNAPSHOT" && msg.dialog?.body) {
      showToast("info", msg.dialog.body);
      return;
    }
  }

  // ===== Chat → orquestador decide =====
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
    } finally {
      sending = false;
    }
  }

  function onKeydownChat(e: KeyboardEvent) {
    if ((e.ctrlKey || (e as any).metaKey) && e.key === "Enter") {
      e.preventDefault(); onSendText();
    }
  }

  // ===== Upload (multipart) =====
  async function onSubmitUpload() {
    if (!formSpec) return;
    const fd = new FormData();
    fd.set("threadId", threadId);
    fd.set("correlationId", crypto?.randomUUID?.() ?? `corr-upload-${Date.now()}`);

    for (const f of (formSpec.fields ?? [])) {
      if (f.type === "file") continue;
      fd.set(f.name, String(formValues[f.name] ?? ""));
    }
    if (!fileObj) { showToast("warning", "Seleccioná un archivo."); return; }
    fd.set("file", fileObj, fileObj.name);

    try {
      const endpoint = formSpec.submit?.endpoint || "/api/uploads/bank-movements";
      const method   = formSpec.submit?.method || "POST";
      const res = await fetch(`${URL_REST}${endpoint}`, { method, body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      showToast("success", j?.message || "Archivo recibido. Generando vista previa…");
    } catch {
      showToast("error", "No se pudo subir el archivo.");
    }
  }

  // ===== Confirmación de la vista previa =====
  async function onConfirmPreview() {
    if (!preview) return;
    confirmBusy = true;
    try {
      const fd = new FormData();
      fd.set("threadId", threadId);
      fd.set("correlationId", crypto?.randomUUID?.() ?? `corr-confirm-${Date.now()}`);
      fd.set("source_file_id", preview.source_file_id || "");
      fd.set("original_uri", preview.original_uri || "");
      fd.set("account_id", preview.account_id || "");
      fd.set("bank", preview?.detected?.bank || "");
      fd.set("period_from", preview?.suggest?.period_from || "");
      fd.set("period_to", preview?.suggest?.period_to || "");

      const res = await fetch(`${URL_REST}/api/ingest/confirm`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      showToast("success", j?.message || "Listo, iniciando…");
    } catch {
      showToast("error", "No se pudo confirmar.");
    } finally {
      confirmBusy = false;
    }
  }

  // ===== Mount =====
  $effect(() => {
    if (typeof window === "undefined") return;
    connectSSE();
  });
</script>

<!-- ====== Card: Asistente / Chat ====== -->
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
        placeholder="Ej: 'Conciliar julio Banco Ciudad' (Ctrl/Cmd + Enter para enviar)"
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

    <p class="text-xs opacity-70">
      El sistema decide el siguiente paso: pedir archivo, preguntar un dato faltante o responder.
    </p>
  </div>
</section>

<!-- ====== Modal de Upload ====== -->
<dialog class="modal" bind:this={dialogRef} on:close={() => (dialogOpen = false)}>
  <div class="modal-box max-w-3xl">
    <h3 class="font-bold text-lg">{formSpec?.title || "Subí el archivo para analizar"}</h3>
    {#if formSpec?.hint}<p class="opacity-70 text-sm mb-2">{formSpec.hint}</p>{/if}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      {#each (formSpec?.fields || []) as f (f.name)}
        <div>
          <label class="label"><span class="label-text">{f.label}{f.required ? " *" : ""}</span></label>

          {#if f.type === "text"}
            <input class="input input-bordered w-full" type="text" bind:value={formValues[f.name]} placeholder={f.placeholder || ""}>

          {:else if f.type === "select"}
            <select class="select select-bordered w-full" bind:value={formValues[f.name]}>
              {#each (f.options || []) as opt ((typeof opt === 'object' ? (opt as any).value : opt) || f.name)}
                {#if typeof opt === "object"}
                  <option value={(opt as any).value}>{(opt as any).label}</option>
                {:else}
                  <option value={opt as string}>{opt as string}</option>
                {/if}
              {/each}
            </select>

          {:else if f.type === "file"}
            <input
              class="file-input file-input-bordered w-full"
              type="file"
              accept={f.accept || ""}
              on:change={(e:any)=>{fileObj = e?.target?.files?.[0] || null;}}
            />

          {:else}
            <input class="input input-bordered w-full" type="text" bind:value={formValues[f.name]} placeholder={f.placeholder || ""}>
          {/if}
        </div>
      {/each}
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

<!-- ====== Card de Vista Previa ====== -->
{#if preview}
  <section class="card bg-base-100 border border-base-300 shadow-sm mt-4">
    <div class="card-body">
      <h3 class="font-semibold text-lg">Vista previa de ingestión</h3>

      {#if preview?.validation}
        {#if preview.validation.is_valid === false}
          <div class="alert alert-error text-sm">
            <div>
              <span class="font-semibold">El archivo no pasa validación de extracto.</span>
              {#if (preview.validation.errors || []).length}
                <ul class="list-disc ml-6">
                  {#each preview.validation.errors as err}
                    <li>{err}</li>
                  {/each}
                </ul>
              {/if}
            </div>
          </div>
        {:else}
          <div class="alert alert-success text-sm">
            <span>Estructura de extracto detectada correctamente.</span>
            {#if (preview.validation.warnings || []).length}
              <ul class="list-disc ml-6">
                {#each preview.validation.warnings as warn}
                  <li>{warn}</li>
                {/each}
              </ul>
            {/if}
          </div>
        {/if}
      {/if}

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        <div>
          <span class="opacity-70">Tipo:</span>
          <b>{(preview?.kind === "gl") ? "Contable (PILAGA)" : (preview?.kind === "bank_movements" ? "Movimientos Bancarios" : "Desconocido")}</b>
        </div>

        <div>
          <span class="opacity-70">Banco detectado:</span>
          <b>{preview?.detected?.bank || "—"}</b>
        </div>

        <div>
          <span class="opacity-70">Cuenta (core/dv):</span>
          <b>{preview?.detected?.account_core_dv || "—"}</b>
        </div>

        <div>
          <span class="opacity-70">Rango detectado:</span>
          <b>{preview?.suggest?.period_from || "—"} → {preview?.suggest?.period_to || "—"}</b>
        </div>

        <div class="col-span-1 md:col-span-2">
          <span class="opacity-70">Header:</span>
          <span class="whitespace-pre-wrap">{preview?.detected?.header_excerpt || "—"}</span>
        </div>
      </div>

      {#if preview?.needs?.bank || preview?.needs?.account_id || preview?.needs?.period_range}
        <div class="alert alert-warning mt-3">
          <span>
            Faltan datos por confirmar:
            {preview?.needs?.bank ? " Banco" : ""}{preview?.needs?.account_id ? " · Cuenta interna" : ""}{preview?.needs?.period_range ? " · Rango de fechas" : ""}
          </span>
        </div>
      {/if}

      <div class="mt-3 flex gap-2">
        <button class="btn btn-primary" on:click|preventDefault={onConfirmPreview} disabled={confirmBusy || (preview?.validation?.is_valid === false)}>
          {#if confirmBusy}<span class="loading loading-spinner loading-sm mr-2" />{:else}Confirmar y procesar{/if}
        </button>
        <button class="btn btn-ghost" on:click={() => (preview = null)}>Descartar</button>
      </div>
    </div>
  </section>
{/if}

<!-- ====== Toast ====== -->
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
