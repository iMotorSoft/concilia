<script lang="ts">
  // src/components/agui/ReconciliarResumen.svelte
  import { URL_REST } from '../global';

  const props = $props<{
    uriExtracto?: string;
    uriContable?: string;
    daysWindow?: number;
  }>();

  const uriExtracto = $derived(props.uriExtracto ?? "");
  const uriContable = $derived(props.uriContable ?? "");
  const daysWindowProp = $derived(props.daysWindow ?? 5);

  let daysWindow = $state(daysWindowProp); // editable desde la UI

  $effect(() => {
    daysWindow = daysWindowProp;
  });

  const formatNumber = (value: any) => {
    if (value === null || value === undefined) return "—";
    const num = Number(value);
    if (Number.isNaN(num) || !Number.isFinite(num)) return String(value);
    try {
      return num.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } catch {
      return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
  };

  let loading = $state(false);
  let summary: any = $state(null);
  let errorMsg: string | null = $state(null);

  async function fetchSummary(
    uriExtr: string = uriExtracto,
    uriCont: string = uriContable,
    windowDays: number = daysWindow ?? 5
  ) {
    errorMsg = null;
    summary = null;
    loading = true;

    try {
      const fd = new FormData();
      fd.set("uri_extracto", uriExtr || "");
      fd.set("uri_contable", uriCont || "");
      fd.set("days_window", String(windowDays || 5));

      const res = await fetch(`${URL_REST}/api/reconcile/summary`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      if (!j?.ok) throw new Error(j?.message || "Error en resumen");
      summary = j.summary || null;
    } catch (err: any) {
      errorMsg = err?.message || "No se pudo obtener el resumen";
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    const extr = uriExtracto;
    const cont = uriContable;
    const windowDays = daysWindowProp;
    if (!extr || !cont) {
      summary = null;
      return;
    }
    fetchSummary(extr, cont, windowDays);
  });
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm">
  <div class="card-body gap-3">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h3 class="font-semibold text-lg">Sumario de período</h3>
      <div class="flex gap-2 items-center">
        <input
          type="number"
          min="0"
          class="input input-bordered w-24"
          bind:value={daysWindow}
          title="Ventana de días para match"
        />
        <button class="btn btn-primary" on:click|preventDefault={() => fetchSummary()} disabled={loading || !uriExtracto || !uriContable} aria-busy={loading}>
          {#if loading}
            <span class="loading loading-spinner loading-sm mr-2" /> Actualizando…
          {:else}
            Actualizar sumario
          {/if}
        </button>
      </div>
    </div>

    <!-- URIs (opcional mostrar para debug) -->
    <div class="text-xs opacity-60">
      <div><b>Extracto:</b> {uriExtracto || "—"}</div>
      <div><b>Contable:</b> {uriContable || "—"}</div>
    </div>

    {#if errorMsg}
      <div class="alert alert-error mt-2">{errorMsg}</div>
    {/if}

    {#if summary}
      <!-- Métricas existentes -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 text-sm">
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Movimientos PILAGA</div>
          <div class="stat-value text-lg">{summary?.movimientos_pilaga ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Movimientos Banco</div>
          <div class="stat-value text-lg">{summary?.movimientos_banco ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Conciliados (pares)</div>
          <div class="stat-value text-lg">{summary?.conciliados_pares ?? "—"}</div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 text-sm">
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">No en Banco</div>
          <div class="stat-value text-lg">{summary?.no_en_banco ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">No en PILAGA</div>
          <div class="stat-value text-lg">{summary?.no_en_pilaga ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Ventana (días)</div>
          <div class="stat-value text-lg">{summary?.days_window ?? "—"}</div>
        </div>
      </div>

      <!-- Totales nuevos -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div class="card bg-base-200">
          <div class="card-body">
            <h4 class="font-semibold">Banco — Debe / Haber</h4>
            <div class="grid grid-cols-3 gap-2 text-sm">
              <div><span class="opacity-70">Debe:</span><br/><b>${formatNumber(summary?.banco?.debe)}</b></div>
              <div><span class="opacity-70">Haber:</span><br/><b>${formatNumber(summary?.banco?.haber)}</b></div>
              <div><span class="opacity-70">Resultado del período:</span><br/><b>${formatNumber(summary?.banco?.neto)}</b></div>
            </div>
            <div class="mt-3 text-sm grid grid-cols-2 gap-2 opacity-80">
              <div>Saldo inicial: <b>${formatNumber(summary?.banco?.saldo_inicial)}</b></div>
              <div>Saldo final: <b>${formatNumber(summary?.banco?.saldo_final)}</b></div>
            </div>
          </div>
        </div>

        <div class="card bg-base-200">
          <div class="card-body">
            <h4 class="font-semibold">PILAGA — Ingresos / Egresos</h4>
            <div class="grid grid-cols-3 gap-2 text-sm">
              <div><span class="opacity-70">Ingresos:</span><br/><b>${formatNumber(summary?.pilaga?.ingresos)}</b></div>
              <div><span class="opacity-70">Egresos:</span><br/><b>${formatNumber(summary?.pilaga?.egresos)}</b></div>
              <div><span class="opacity-70">Resultado del período:</span><br/><b>${formatNumber(summary?.pilaga?.neto)}</b></div>
            </div>
            <div class="mt-3 text-sm grid grid-cols-2 gap-2 opacity-80">
              <div>Saldo inicial: <b>${formatNumber(summary?.pilaga?.saldo_inicial)}</b></div>
              <div>Saldo final: <b>${formatNumber(summary?.pilaga?.saldo_final)}</b></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Coherencia -->
      <div class="alert mt-3" class:alert-success={(summary?.diferencia_neto ?? 0) === 0} class:alert-warning={(summary?.diferencia_neto ?? 0) !== 0}>
        <span>
          Diferencia de neto (Banco - PILAGA): <b>${formatNumber(summary?.diferencia_neto)}</b>
        </span>
      </div>
    {/if}
  </div>
</section>
