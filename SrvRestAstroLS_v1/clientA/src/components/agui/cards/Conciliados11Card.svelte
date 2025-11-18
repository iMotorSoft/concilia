<script lang="ts">
  import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from '../reconcileConfig';

  type PairRow = {
    fecha_banco?: string;
    fecha_pilaga?: string;
    monto?: number;
    documento_banco?: string;
    documento_pilaga?: string;
    date_diff_days?: number;
  };

  const props = $props<{
    urlRest: string;
    extractoUri: string;
    contableUri: string;
  }>();

  const urlRest = $derived(props.urlRest || "");
  const extractoUri = $derived(props.extractoUri || "");
  const contableUri = $derived(props.contableUri || "");

  const TITLE = "Conciliados 1→1";
  const ENDPOINT = "/api/reconcile/details/pares";

  let expanded = $state(false);
  let loading = $state(false);
  let errorMsg: string | null = $state(null);
  let rows: PairRow[] = $state([]);
  let totalAmount: number | null = $state(null);
  let countDisplay: number | null = $state(null);
  let daysWindow = $state(DEFAULT_DAYS_WINDOW);
  let lastSourceFingerprint: string | null = null;

  function fmtMoney(value: number | string | null | undefined) {
    if (value === null || value === undefined) return "—";
    const num = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(num)) return "—";
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(num);
  }

  function countLabel(): string {
    if (typeof countDisplay === "number") {
      return `${countDisplay} pares`;
    }
    return "— pares";
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
  }

  function handleDaysWindowChange(newValue: number) {
    daysWindow = newValue;
    fetchData();
  }

  $effect(() => {
    const unsubscribe = daysWindowStore.subscribe((value) => {
      const normalized = normalizeDaysWindow(value);
      const changed = normalized !== daysWindow;
      if (changed) {
        handleDaysWindowChange(normalized);
      }
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
    if (extr && cont) {
      fetchData();
    }
  });

  async function toggleExpanded() {
    expanded = !expanded;
    if (expanded && !rows.length && !loading) {
      fetchData();
    }
  }

  async function fetchData() {
    if (!extractoUri || !contableUri) {
      errorMsg = "Faltan archivos confirmados.";
      return;
    }
    loading = true;
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

      rows = (payload.rows || []) as PairRow[];
      const inferredCount = typeof payload.total === "number" ? payload.total : rows.length;
      countDisplay = inferredCount;
      const providedTotal = typeof payload.total_amount === "number" ? payload.total_amount : null;
      const inferredTotal = rows.reduce((acc, r) => acc + (Number(r?.monto) || 0), 0);
      totalAmount = providedTotal ?? inferredTotal;
    } catch (err: any) {
      errorMsg = err?.message || "No se pudo cargar el detalle.";
      rows = [];
      countDisplay = null;
      totalAmount = null;
    } finally {
      loading = false;
    }
  }
</script>

<article class="card bg-base-100 border border-base-300 shadow-sm">
  <button
    class="card-body flex items-center justify-between gap-4 cursor-pointer text-left"
    on:click|preventDefault={toggleExpanded}
    aria-expanded={expanded}
  >
    <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
      <span class="font-semibold text-lg">{TITLE}</span>
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="badge badge-neutral badge-outline">{countLabel()}</span>
        <span class="badge badge-success badge-outline">
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

  {#if expanded}
    <div class="px-6 pb-6 -mt-2 space-y-3">
      {#if loading}
        <div class="flex items-center gap-2 text-sm opacity-80">
          <span class="loading loading-spinner loading-sm" /> Cargando detalle…
        </div>
      {:else if errorMsg}
        <div class="alert alert-error">{errorMsg}</div>
      {:else}
        <div class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>Fecha banco</th>
                <th>Monto</th>
                <th>Doc. banco</th>
                <th>Fecha PILAGA</th>
                <th>Doc. PILAGA</th>
                <th>Δ días</th>
              </tr>
            </thead>
            <tbody>
              {#each rows as r}
                <tr>
                  <td>{r?.fecha_banco ?? "—"}</td>
                  <td>{fmtMoney(r?.monto)}</td>
                  <td class="max-w-[240px] truncate" title={r?.documento_banco}>{r?.documento_banco ?? "—"}</td>
                  <td>{r?.fecha_pilaga ?? "—"}</td>
                  <td class="max-w-[240px] truncate" title={r?.documento_pilaga}>{r?.documento_pilaga ?? "—"}</td>
                  <td>{r?.date_diff_days ?? 0}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</article>
