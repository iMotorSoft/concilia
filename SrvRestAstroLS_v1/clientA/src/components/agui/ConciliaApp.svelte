<script lang="ts">
  import { URL_REST } from '../global';

  // ===== Runes state =====
  let chatInput = $state("");
  let sending   = $state(false);

  // Modal
  let dialogOpen = $state(false);
  let dialogRef: HTMLDialogElement | null = null;

  // Form spec y valores (desde evento)
  let formSpec: any = $state(null);
  let formValues: Record<string, any> = $state({});
  let fileObj: File | null = $state(null);

  // SSE + toasts
  let es: EventSource | null = null;
  let toast: { level: "info"|"success"|"warning"|"error"; message: string } | null = $state(null);
  let toastTimer: any = null;

  // Identidad de sesión/tema (para topic del SSE)
  const threadId = crypto?.randomUUID?.() ?? `t-concilia-${Date.now()}`;

  function showToast(level: "info"|"success"|"warning"|"error", message: string) {
    toast = { level, message };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2600);
  }

  // Modal open/close reactivo
  $effect(() => {
    if (typeof window === "undefined" || !dialogRef) return;
    if (dialogOpen && !dialogRef.open) dialogRef.showModal?.();
    if (!dialogOpen && dialogRef.open) dialogRef.close?.();
  });

  function seedFormDefaults(spec: any) {
    const defaults: Record<string, any> = {};
    for (const f of (spec?.fields ?? [])) {
      if (f.type === "file") continue;
      if ("default" in f && f.default != null) defaults[f.name] = f.default;
      else if (f.type === "select" && Array.isArray(f.options) && f.options.length > 0) defaults[f.name] = f.options[0].value ?? f.options[0];
      else defaults[f.name] = "";
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

    if (t === "TEXT_MESSAGE_REQUEST_UPLOAD") {
      formSpec = msg?.payload?.form || null;
      seedFormDefaults(formSpec);
      dialogOpen = true;
      return;
    }

    if (t === "RUN_START") {
      dialogOpen = false;
      showToast("success", "Análisis iniciado. Procesando…");
      return;
    }
  }

  // ===== Chat → pedir modal =====
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
      showToast("info", "Solicitud enviada. Se abrirá el modal para subir el archivo.");
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

  // ===== Submit upload (multipart) =====
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
      const res = await fetch(`${URL_REST}${formSpec.submit?.endpoint || "/api/uploads/bank-movements"}`, {
        method: formSpec.submit?.method || "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      showToast("success", j?.message || "Archivo recibido. Iniciando análisis…");
    } catch {
      showToast("error", "No se pudo subir el archivo.");
    }
  }

  // ===== Mount =====
  $effect(() => {
    if (typeof window === "undefined") return;
    connectSSE();
  });
</script>

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
      El sistema detecta tu intención, solicita el archivo de extracto bancario y, tras el upload, inicia el análisis.
    </p>
  </div>
</section>

<!-- Modal de Upload -->
<dialog class="modal" bind:this={dialogRef} on:close={() => (dialogOpen = false)}>
  <div class="modal-box max-w-3xl">
    <h3 class="font-bold text-lg">{formSpec?.title || "Subí el archivo para analizar"}</h3>
    {#if formSpec?.hint}<p class="opacity-70 text-sm mb-2">{formSpec.hint}</p>{/if}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      {#each formSpec?.fields || [] as f (f.name)}
        <div>
          <label class="label"><span class="label-text">{f.label}{f.required ? " *" : ""}</span></label>

          {#if f.type === "text"}
            <input class="input input-bordered w-full" type="text" bind:value={formValues[f.name]} placeholder={f.placeholder || ""}>

          {:else if f.type === "select"}
            <select class="select select-bordered w-full" bind:value={formValues[f.name]}>
              {#each (f.options || []) as opt (opt.value ?? opt)}
                {#if typeof opt === "object"}
                  <option value={opt.value}>{opt.label}</option>
                {:else}
                  <option value={opt}>{opt}</option>
                {/if}
              {/each}
            </select>

          {:else if f.type === "file"}
            <input class="file-input file-input-bordered w-full" type="file" accept={f.accept || ""} on:change={(e:any)=>{fileObj = e?.target?.files?.[0] || null;}} />

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

