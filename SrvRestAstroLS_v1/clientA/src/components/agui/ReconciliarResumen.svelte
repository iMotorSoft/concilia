<script lang="ts">
  // src/components/agui/ReconciliarResumen.svelte
  import { URL_REST } from '../global';
  import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from './reconcileConfig';

  const props = $props<{
    uriExtracto?: string;
    uriContable?: string;
  }>();

  const uriExtracto = $derived(props.uriExtracto ?? "");
  const uriContable = $derived(props.uriContable ?? "");

  let daysWindow = $state(DEFAULT_DAYS_WINDOW); // editable desde la UI y compartido vía store

  $effect(() => {
    const unsubscribe = daysWindowStore.subscribe((value) => {
      daysWindow = normalizeDaysWindow(value);
    });
    return () => unsubscribe();
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

  const formatCountAmount = (item: any) => {
    if (!item) return "—";
    const count = typeof item.count === "number" ? `${item.count} op` : "— op";
    const amount = formatNumber(item.amount ?? null);
    return `${count} · $${amount}`;
  };

  let loadingHead = $state(false);
  let loadingDescomp = $state(false);
  let summaryHead: any = $state(null);
  let descomposicion: any = $state(null);
  let errorHead: string | null = $state(null);
  let errorDescomp: string | null = $state(null);
  let descompElapsedMs = $state(0);
  let descompTimer: any = null;
  let refreshElapsedMs = $state(0);
  let refreshTimer: any = null;

  function setDaysWindow(value: number | string) {
    daysWindowStore.set(normalizeDaysWindow(value));
  }

  async function fetchSummaryHead(
    uriExtr: string = uriExtracto,
    uriCont: string = uriContable,
    windowDays: number = daysWindow ?? DEFAULT_DAYS_WINDOW
  ) {
    errorHead = null;
    summaryHead = null;
    loadingHead = true;

    try {
      const fd = new FormData();
      fd.set("uri_extracto", uriExtr || "");
      fd.set("uri_contable", uriCont || "");
      fd.set("days_window", String(windowDays || DEFAULT_DAYS_WINDOW));

      const res = await fetch(`${URL_REST}/api/reconcile/summary/head`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      if (!j?.ok) throw new Error(j?.message || "Error en resumen");
      summaryHead = j.summary || null;
    } catch (err: any) {
      errorHead = err?.message || "No se pudo obtener el resumen";
    } finally {
      loadingHead = false;
    }
  }

  async function fetchDescomposicion(
    uriExtr: string = uriExtracto,
    uriCont: string = uriContable,
    windowDays: number = daysWindow ?? DEFAULT_DAYS_WINDOW
  ) {
    errorDescomp = null;
    descomposicion = null;
    loadingDescomp = true;
    descompElapsedMs = 0;
    if (descompTimer) clearInterval(descompTimer);
    descompTimer = setInterval(() => {
      descompElapsedMs += 100;
    }, 100);

    try {
      const fd = new FormData();
      fd.set("uri_extracto", uriExtr || "");
      fd.set("uri_contable", uriCont || "");
      fd.set("days_window", String(windowDays || DEFAULT_DAYS_WINDOW));

      const res = await fetch(`${URL_REST}/api/reconcile/summary/descomposicion`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      if (!j?.ok) throw new Error(j?.message || "Error en descomposición");
      descomposicion = j.descomposicion || null;
    } catch (err: any) {
      errorDescomp = err?.message || "No se pudo obtener la descomposición";
    } finally {
      loadingDescomp = false;
      if (descompTimer) {
        clearInterval(descompTimer);
        descompTimer = null;
      }
    }
  }

  async function refreshAll() {
    refreshElapsedMs = 0;
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      refreshElapsedMs += 100;
    }, 100);
    await fetchSummaryHead();
    await fetchDescomposicion();
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  $effect(() => {
    const extr = uriExtracto;
    const cont = uriContable;
    const windowDays = daysWindow;
    if (!extr || !cont) {
      summaryHead = null;
      descomposicion = null;
      descompElapsedMs = 0;
      if (descompTimer) {
        clearInterval(descompTimer);
        descompTimer = null;
      }
      return;
    }
    refreshAll();
  });
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm">
  <div class="card-body gap-3">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h3 class="font-semibold text-lg">Sumario de período</h3>
      <div class="flex gap-2 items-center">
        <input
          type="number"
          min="1"
          class="input input-bordered w-24"
          bind:value={daysWindow}
          title="Ventana de días para match"
          on:input={(event:any) => setDaysWindow(event?.currentTarget?.value ?? daysWindow)}
        />
        <button
          class="btn btn-primary"
          on:click|preventDefault={() => refreshAll()}
          disabled={loadingHead || loadingDescomp || !uriExtracto || !uriContable}
          aria-busy={loadingHead || loadingDescomp}
        >
          {#if loadingHead || loadingDescomp}
            <span class="loading loading-spinner loading-sm mr-2" /> Actualizando… {(refreshElapsedMs/1000).toFixed(1)}s
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

    {#if errorHead}
      <div class="alert alert-error mt-2">{errorHead}</div>
    {/if}

    {#if summaryHead}
      <!-- Métricas existentes -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 text-sm">
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Movimientos PILAGA</div>
          <div class="stat-value text-lg">{summaryHead?.movimientos_pilaga ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Movimientos Banco</div>
          <div class="stat-value text-lg">{summaryHead?.movimientos_banco ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Conciliados (pares)</div>
          <div class="stat-value text-lg">{summaryHead?.conciliados_pares ?? "—"}</div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 text-sm">
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">No en Banco</div>
          <div class="stat-value text-lg">{summaryHead?.no_en_banco ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">No en PILAGA</div>
          <div class="stat-value text-lg">{summaryHead?.no_en_pilaga ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Ventana (días)</div>
          <div class="stat-value text-lg">{summaryHead?.days_window ?? "—"}</div>
        </div>
      </div>

      <!-- Totales nuevos -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div class="card bg-base-200">
          <div class="card-body">
            <h4 class="font-semibold">Banco — Debe / Haber</h4>
            <div class="grid grid-cols-3 gap-2 text-sm">
              <div><span class="opacity-70">Debe:</span><br/><b>${formatNumber(summaryHead?.banco?.debe)}</b></div>
              <div><span class="opacity-70">Haber:</span><br/><b>${formatNumber(summaryHead?.banco?.haber)}</b></div>
              <div><span class="opacity-70">Resultado del período:</span><br/><b>${formatNumber(summaryHead?.banco?.neto)}</b></div>
            </div>
            <div class="mt-3 text-sm grid grid-cols-2 gap-2 opacity-80">
              <div>Saldo inicial: <b>${formatNumber(summaryHead?.banco?.saldo_inicial)}</b></div>
              <div>Saldo final: <b>${formatNumber(summaryHead?.banco?.saldo_final)}</b></div>
            </div>
          </div>
        </div>

        <div class="card bg-base-200">
          <div class="card-body">
            <h4 class="font-semibold">PILAGA — Ingresos / Egresos</h4>
            <div class="grid grid-cols-3 gap-2 text-sm">
              <div><span class="opacity-70">Ingresos:</span><br/><b>${formatNumber(summaryHead?.pilaga?.ingresos)}</b></div>
              <div><span class="opacity-70">Egresos:</span><br/><b>${formatNumber(summaryHead?.pilaga?.egresos)}</b></div>
              <div><span class="opacity-70">Resultado del período:</span><br/><b>${formatNumber(summaryHead?.pilaga?.neto)}</b></div>
            </div>
            <div class="mt-3 text-sm grid grid-cols-2 gap-2 opacity-80">
              <div>Saldo inicial: <b>${formatNumber(summaryHead?.pilaga?.saldo_inicial)}</b></div>
              <div>Saldo final: <b>${formatNumber(summaryHead?.pilaga?.saldo_final)}</b></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card bg-base-200 mt-4">
        <div class="card-body">
          <h4 class="font-semibold">Descomposición de movimientos</h4>
          {#if descomposicion}
            <p class="text-sm opacity-80">Estas cuatro categorías son disjuntas y suman el resultado del período de cada lado.</p>
            <div class="overflow-x-auto">
              <table class="table table-sm">
                <thead>
                  <tr>
                    <th>Categoría</th>
                    <th>Banco</th>
                    <th>PILAGA</th>
                  </tr>
                    </thead>
                    <tbody>
                  <tr>
                    <td class="font-medium">Conciliados 1→1</td>
                    <td>{formatCountAmount(descomposicion?.conciliados)}</td>
                    <td>{formatCountAmount(descomposicion?.conciliados)}</td>
                  </tr>
                  <tr>
                    <td class="font-medium">Agrupados (≤ $1)</td>
                    <td>{formatCountAmount(descomposicion?.agrupados)}</td>
                    <td>{formatCountAmount(descomposicion?.agrupados)}</td>
                  </tr>
                  <tr>
                    <td class="font-medium">Sugeridos (>$1 y ≤ $5)</td>
                    <td>{formatCountAmount(descomposicion?.sugeridos)}</td>
                    <td>{formatCountAmount(descomposicion?.sugeridos)}</td>
                  </tr>
                  <tr>
                    <td class="font-medium">No reflejado</td>
                    <td>Banco no reflejado en PILAGA: {formatCountAmount(descomposicion?.no_en_pilaga)}</td>
                    <td>PILAGA no reflejado en Banco: {formatCountAmount(descomposicion?.no_en_banco)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          {:else if errorDescomp}
            <div class="alert alert-error">{errorDescomp}</div>
          {:else}
            <div class="flex items-center gap-2 text-sm opacity-80">
              <span class="loading loading-spinner loading-sm" aria-hidden="true"></span>
              <span>Procesando… {(descompElapsedMs/1000).toFixed(1)}s</span>
            </div>
          {/if}
        </div>
      </div>

      <!-- Coherencia -->
      <div class="alert mt-3" class:alert-success={(summaryHead?.diferencia_neto ?? 0) === 0} class:alert-warning={(summaryHead?.diferencia_neto ?? 0) !== 0}>
        <span>
          Diferencia de neto (Banco - PILAGA): <b>${formatNumber(summaryHead?.diferencia_neto)}</b>
        </span>
      </div>
    {/if}
  </div>
</section>
