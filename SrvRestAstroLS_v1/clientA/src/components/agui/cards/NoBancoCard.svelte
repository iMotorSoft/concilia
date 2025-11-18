<script lang="ts">
  import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from '../reconcileConfig';

  type DetailRow = { fecha: string; monto: number; documento: string };

  const props = $props<{
    urlRest: string;
    extractoUri: string;
    contableUri: string;
    summary?: Record<string, any> | null;
  }>();

  const urlRest = $derived(props.urlRest || "");
  const extractoUri = $derived(props.extractoUri || "");
  const contableUri = $derived(props.contableUri || "");
  const summary = $derived(props.summary ?? null);

  const TITLE = "PILAGA No reflejado en Bco";
  const ENDPOINT = "/api/reconcile/details/no-banco";

  let expanded = $state(false);
let loading = $state(false);
let errorMsg: string | null = $state(null);
let rows: DetailRow[] = $state([]);
let totalAmount: number | null = $state(null);
let countDisplay: number | null = $state(null);
let daysWindow = $state(DEFAULT_DAYS_WINDOW);
let lastSourceFingerprint: string | null = null;
let elapsedMs = $state(0);
let timerId: any = null;

  function fmtMoney(value: number | string | null | undefined) {
    if (value === null || value === undefined) return "—";
    const num = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(num)) return "—";
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(num);
  }

  function countLabel(): string {
    const count = countDisplay;
    if (typeof count === "number") {
      return `${count} op`;
    }
    return "— op";
  }

  function displayAmount(): number | null {
    if (typeof totalAmount === "number") return totalAmount;
    return null;
  }

function resetState() {
  expanded = false;
  loading = false;
  errorMsg = null;
  rows = [];
  countDisplay = null;
  totalAmount = null;
  elapsedMs = 0;
  if (timerId) {
    clearInterval(timerId);
    timerId = null;
  }
}

  $effect(() => {
    const unsubscribe = daysWindowStore.subscribe((value) => {
      daysWindow = normalizeDaysWindow(value);
    });
    return () => unsubscribe();
  });

  $effect(() => {
    const summaryCount = summary?.no_en_banco;
    if (typeof summaryCount === "number") {
      countDisplay = summaryCount;
    }
  });

  $effect(() => {
    const extr = extractoUri || "";
    const cont = contableUri || "";
    const fingerprint = `${extr}|${cont}`;
    if (fingerprint === lastSourceFingerprint) return;
    lastSourceFingerprint = fingerprint;
    resetState();
  });

  async function toggleExpanded() {
    expanded = !expanded;
  }

async function fetchData() {
  if (!extractoUri || !contableUri) {
    errorMsg = "Faltan archivos confirmados.";
    return;
  }
  expanded = true; // mostrar el cuerpo mientras calcula
  loading = true;
  elapsedMs = 0;
  if (timerId) clearInterval(timerId);
  timerId = setInterval(() => {
    elapsedMs += 100;
  }, 100);
  errorMsg = null;
  rows = [];
  try {
      const fd = new FormData();
      fd.set("uri_extracto", extractoUri || "");
      fd.set("uri_contable", contableUri || "");
      fd.set("days_window", String(daysWindow ?? DEFAULT_DAYS_WINDOW));

      const res = await fetch(`${urlRest}${ENDPOINT}`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (!payload?.ok) throw new Error(payload?.message || "Respuesta inválida.");

      rows = (payload.rows || []) as DetailRow[];
      const inferredCount = typeof payload.total === "number" ? payload.total : rows.length;
      countDisplay = inferredCount;
      totalAmount = typeof payload.total_amount === "number" ? payload.total_amount : rows.reduce((acc, r) => acc + (Number(r.monto) || 0), 0);
  } catch (err: any) {
    errorMsg = err?.message || "No se pudo cargar el detalle.";
    rows = [];
    countDisplay = null;
    totalAmount = null;
  } finally {
    loading = false;
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  }
}
</script>

<article class="card bg-base-100 border border-base-300 shadow-sm">
  <div class="card-body flex items-center justify-between gap-4">
    <button
      class="flex-1 flex items-center justify-between gap-4 cursor-pointer text-left"
      on:click|preventDefault={toggleExpanded}
      aria-expanded={expanded}
    >
      <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
        <span class="font-semibold text-lg">{TITLE}</span>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <span class="badge badge-neutral badge-outline">{countLabel()}</span>
          <span class="badge badge-info badge-outline">
            {fmtMoney(displayAmount())}
          </span>
        </div>
      </div>
      <svg
        class={"w-4 h-4 transition-transform duration-200 " + (expanded ? "rotate-180" : "")}
        viewBox="0 0 20 20"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path d="M5 12l5-5 5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <button
      class="btn btn-primary btn-xs"
      on:click|preventDefault|stopPropagation={fetchData}
      disabled={loading}
      aria-busy={loading}
    >
      {#if loading}Calculando…{:else}Calcular{/if}
    </button>
  </div>

  {#if expanded}
    <div class="px-6 pb-6 -mt-2">
      {#if loading}
        <div class="flex items-center gap-2 text-sm opacity-80">
          <span class="loading loading-spinner loading-sm" aria-hidden="true" />
          <span>Cargando detalle… {(elapsedMs/1000).toFixed(1)}s</span>
        </div>
      {:else if errorMsg}
        <div class="alert alert-error">{errorMsg}</div>
      {:else}
        <div class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Monto</th>
                <th>Documento</th>
              </tr>
            </thead>
            <tbody>
              {#each rows as r}
                <tr>
                  <td>{r.fecha}</td>
                  <td>{fmtMoney(r.monto)}</td>
                  <td class="max-w-[520px] truncate" title={r.documento}>{r.documento}</td>
                </tr>
              {/each}
              {#if !rows.length}
                <tr><td colspan="3" class="opacity-60">Sin registros</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      {/if}

      <div class="flex justify-end mt-3">
        <button
          class="btn btn-xs btn-outline"
          on:click|preventDefault={fetchData}
          disabled={loading}
          aria-busy={loading}
        >
          {#if loading}Actualizando…{:else}Refrescar{/if}
        </button>
      </div>
    </div>
  {/if}
</article>
