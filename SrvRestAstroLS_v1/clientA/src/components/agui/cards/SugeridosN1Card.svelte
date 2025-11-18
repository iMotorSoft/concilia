<script lang="ts">
  import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from '../reconcileConfig';

  type SimpleRow = { fecha: string; monto: number; documento: string };
  type GroupRow = {
    // N→1 clásico: banco (target) + PILAGA componentes
    bank_row?: SimpleRow | null;
    pilaga_rows?: SimpleRow[];
    // 1→N (simétrico): PILAGA (target) + banco componentes
    pilaga_row?: SimpleRow | null;
    bank_rows?: SimpleRow[];
    monto_total?: number;
    estado?: string;
    direction?: "p_to_bank" | "bank_to_pilaga";
  };

  const props = $props<{
    urlRest: string;
    extractoUri: string;
    contableUri: string;
  }>();

  const urlRest = $derived(props.urlRest || "");
  const extractoUri = $derived(props.extractoUri || "");
  const contableUri = $derived(props.contableUri || "");

  const TITLE = "Sugeridos (N→1)";
  const ENDPOINT = "/api/reconcile/details/n1/sugeridos";

  let expanded = $state(false);
let loading = $state(false);
let errorMsg: string | null = $state(null);
let rows: GroupRow[] = $state([]);
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
    if (typeof countDisplay === "number") {
      return `${countDisplay} sugeridos`;
    }
    return "— sugeridos";
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

  function sumComponents(row: GroupRow): number {
    const list = row?.direction === "bank_to_pilaga" ? (row?.bank_rows || []) : (row?.pilaga_rows || []);
    const s = list.reduce((acc, r) => acc + (Number(r?.monto) || 0), 0);
    return Number.isFinite(s) ? s : 0;
  }

  function targetRow(row: GroupRow): SimpleRow | null | undefined {
    if (row?.direction === "bank_to_pilaga") return row?.pilaga_row;
    return row?.bank_row;
  }

async function fetchData() {
  if (!extractoUri || !contableUri) {
    errorMsg = "Faltan archivos confirmados.";
    return;
  }
  expanded = true; // mostrar cuerpo mientras calcula
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

      rows = (payload.rows || []) as GroupRow[];
      const inferredCount = typeof payload.total === "number" ? payload.total : rows.length;
      countDisplay = inferredCount;
      const providedTotal = typeof payload.total_amount === "number" ? payload.total_amount : null;
      const inferredTotal = rows.reduce((acc, r) => acc + (Number(r?.monto_total) || sumComponents(r)), 0);
      totalAmount = providedTotal ?? inferredTotal;
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
          <span class="badge badge-warning badge-outline">
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
    <div class="px-6 pb-6 -mt-2 space-y-3">
      {#if loading}
        <div class="flex items-center gap-2 text-sm opacity-80">
          <span class="loading loading-spinner loading-sm" aria-hidden="true" />
          <span>Cargando detalle… {(elapsedMs/1000).toFixed(1)}s</span>
        </div>
      {:else if errorMsg}
        <div class="alert alert-error">{errorMsg}</div>
      {:else}
        <div class="space-y-4">
          {#each rows as r}
            <div class="border border-base-200 rounded-lg overflow-hidden">
              <div class="flex flex-wrap items-center justify-between gap-2 px-4 py-2 bg-base-200">
                <div class="flex items-center gap-2 text-sm">
                  <span class="badge badge-outline">{r?.direction === "bank_to_pilaga" ? "1→N (Banco)" : "N→1 (Banco)"}</span>
                  <span class="opacity-80">Target: {targetRow(r)?.fecha ?? "—"} — {fmtMoney(targetRow(r)?.monto)}</span>
                  <span class="opacity-60 max-w-[320px] truncate" title={targetRow(r)?.documento}>{targetRow(r)?.documento ?? "—"}</span>
                </div>
                <div class="flex items-center gap-2 text-sm">
                  <span class="badge badge-neutral badge-outline">{(r?.direction === "bank_to_pilaga" ? r?.bank_rows?.length : r?.pilaga_rows?.length) ?? 0} componentes</span>
                  <span class="badge badge-warning badge-outline">{fmtMoney(r?.monto_total ?? sumComponents(r))}</span>
                </div>
              </div>

              <div class="px-4 py-3 overflow-x-auto">
                <div class="text-xs opacity-70 mb-1">
                  {r?.direction === "bank_to_pilaga" ? "Componentes banco" : "Componentes PILAGA"}
                </div>
                <table class="table table-xs">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Monto</th>
                      <th>Documento</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#if r?.direction === "bank_to_pilaga"}
                      {#each r?.bank_rows || [] as br}
                        <tr>
                          <td>{br?.fecha ?? "—"}</td>
                          <td>{fmtMoney(br?.monto)}</td>
                          <td class="max-w-[320px] truncate" title={br?.documento}>{br?.documento ?? "—"}</td>
                        </tr>
                      {/each}
                      {#if !(r?.bank_rows || []).length}
                        <tr><td colspan="3" class="opacity-60">Sin componentes</td></tr>
                      {/if}
                    {:else}
                      {#each r?.pilaga_rows || [] as pr}
                        <tr>
                          <td>{pr?.fecha ?? "—"}</td>
                          <td>{fmtMoney(pr?.monto)}</td>
                          <td class="max-w-[320px] truncate" title={pr?.documento}>{pr?.documento ?? "—"}</td>
                        </tr>
                      {/each}
                      {#if !(r?.pilaga_rows || []).length}
                        <tr><td colspan="3" class="opacity-60">Sin componentes</td></tr>
                      {/if}
                    {/if}
                  </tbody>
                </table>
              </div>
            </div>
          {/each}
          {#if !rows.length}
            <div class="text-sm opacity-60">Sin registros sugeridos.</div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</article>
