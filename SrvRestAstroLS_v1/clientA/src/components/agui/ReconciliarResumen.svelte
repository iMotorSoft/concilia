<script lang="ts">
  // src/components/agui/ReconciliarResumen.svelte
  import { URL_REST } from '../global';
  import { authFetch as fetch } from '../auth/transport.js';
  import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from './reconcileConfig';
  import CopyTableButton from './CopyTableButton.svelte';

  const props = $props<{
    uriExtracto?: string;
    uriContable?: string;
    uriSicom?: string;
    bankScope?: string;
    accountScope?: string;
  }>();

  const uriExtracto = $derived(props.uriExtracto ?? "");
  const uriContable = $derived(props.uriContable ?? "");
  const uriSicom = $derived(props.uriSicom ?? "");
  const bankScope = $derived(props.bankScope ?? "");
  const accountScope = $derived(props.accountScope ?? "");

  let daysWindow = $state(DEFAULT_DAYS_WINDOW); // editable por input
  let appliedDaysWindow = $state(DEFAULT_DAYS_WINDOW); // último valor aplicado con botón

  $effect(() => {
    const unsubscribe = daysWindowStore.subscribe((value) => {
      const v = normalizeDaysWindow(value);
      daysWindow = v;
      appliedDaysWindow = v;
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

  async function fetchSummaryHead(
    uriExtr: string = uriExtracto,
    uriCont: string = uriContable,
    windowDays: number = appliedDaysWindow ?? DEFAULT_DAYS_WINDOW
  ) {
    errorHead = null;
    summaryHead = null;
    loadingHead = true;

    try {
      const fd = new FormData();
      fd.set("uri_extracto", uriExtr || "");
      fd.set("uri_contable", uriCont || "");
      fd.set("uri_sicom", uriSicom || "");
      fd.set("bank_scope", bankScope || "");
      fd.set("account_scope", accountScope || "");
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
    windowDays: number = appliedDaysWindow ?? DEFAULT_DAYS_WINDOW
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
      fd.set("uri_sicom", uriSicom || "");
      fd.set("bank_scope", bankScope || "");
      fd.set("account_scope", accountScope || "");
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

  async function refreshAll(windowDays: number = appliedDaysWindow ?? DEFAULT_DAYS_WINDOW) {
    appliedDaysWindow = normalizeDaysWindow(windowDays);
    refreshElapsedMs = 0;
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      refreshElapsedMs += 100;
    }, 100);
    await fetchSummaryHead(uriExtracto, uriContable, windowDays);
    await fetchDescomposicion(uriExtracto, uriContable, windowDays);
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  let lastUris = $state({ extr: "", cont: "", sicom: "", bank: "", account: "" });
  $effect(() => {
    const extr = uriExtracto;
    const cont = uriContable;
    const sicom = uriSicom;
    const bank = bankScope;
    const account = accountScope;
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
    if (
      extr !== lastUris.extr ||
      cont !== lastUris.cont ||
      sicom !== lastUris.sicom ||
      bank !== lastUris.bank ||
      account !== lastUris.account
    ) {
      lastUris = { extr, cont, sicom, bank, account };
      refreshAll(appliedDaysWindow);
    }
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
        />
        <button
          class="btn btn-primary"
          on:click|preventDefault={() => {
            const v = normalizeDaysWindow(daysWindow);
            daysWindow = v;
            appliedDaysWindow = v;
            daysWindowStore.set(v);
            refreshAll(v);
          }}
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
      <div><b>SICOM:</b> {uriSicom || "—"}</div>
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
          <div class="stat-title">Coincidencias directas 1→1</div>
          <div class="stat-value text-lg">{summaryHead?.conciliados_pares ?? "—"}</div>
        </div>
      </div>

      {#if summaryHead?.sicom?.final_reconciliation}
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 text-sm">
          <div class="stat bg-success/10 rounded-xl">
            <div class="stat-title">PILAGA con contraparte en extracto</div>
            <div class="stat-value text-lg">{summaryHead?.sicom?.final_reconciliation?.pilaga_rows_with_extracto ?? "—"}</div>
            <div class="stat-desc">
              {summaryHead?.sicom?.final_reconciliation?.pilaga_unique_ops_with_extracto ?? "—"} OP únicas
            </div>
          </div>
          <div class="stat bg-success/10 rounded-xl">
            <div class="stat-title">Lotes banco con soporte contable</div>
            <div class="stat-value text-lg">{summaryHead?.sicom?.final_reconciliation?.extracto_lotes_with_contable_support ?? "—"}</div>
            <div class="stat-desc">
              vía `PILAGA → SICOM → extracto`
            </div>
          </div>
          <div class="stat bg-base-200 rounded-xl">
            <div class="stat-title">Ventana (días)</div>
            <div class="stat-value text-lg">{summaryHead?.days_window ?? "—"}</div>
          </div>
        </div>
      {:else}
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
      {/if}

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

      {#if summaryHead?.sicom?.used}
        <div class="card bg-base-200 mt-4">
          <div class="card-body">
            <h4 class="font-semibold">SICOM: trazabilidad operativa y cierre bancario</h4>
            <p class="text-sm opacity-80">
              `SICOM` se usa para explicar lotes y reconstruir el puente entre `OP` contable y banco.
              El cierre principal sigue siendo `PILAGA ↔ extracto`.
            </p>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <div>
                <span class="opacity-70">Scope del caso:</span><br/>
                <b>{summaryHead?.sicom?.scope?.bank_scope || "—"}</b>
              </div>
              <div>
                <span class="opacity-70">Cuenta:</span><br/>
                <b>{summaryHead?.sicom?.scope?.account_scope_raw || "—"}</b>
              </div>
              <div>
                <span class="opacity-70">Filtrado aplicado:</span><br/>
                <b>{summaryHead?.sicom?.scope?.scope_applied ? "Sí" : "No"}</b>
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm mt-3">
              <div><span class="opacity-70">Filas SICOM:</span><br/><b>{summaryHead?.sicom?.source?.rows_scoped ?? "—"} / {summaryHead?.sicom?.source?.rows_total ?? "—"}</b></div>
              <div><span class="opacity-70">OP únicas:</span><br/><b>{summaryHead?.sicom?.source?.op_count_scoped ?? "—"}</b></div>
              <div><span class="opacity-70">Nro Pago únicos:</span><br/><b>{summaryHead?.sicom?.source?.nro_pago_count_scoped ?? "—"}</b></div>
              <div><span class="opacity-70">Lotes:</span><br/><b>{summaryHead?.sicom?.source?.lote_count_scoped ?? "—"}</b></div>
            </div>
            <div class="mt-3 text-sm">
              <span class="opacity-70">Bancos en scope:</span>
              <b> {(summaryHead?.sicom?.source?.banks_scoped || []).join(", ") || "—"}</b>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm mt-4">
              <div>
                <div class="font-medium">1. Lotes SICOM que pegan en extracto</div>
                <div class="mt-1">Lotes exactos: <b>{summaryHead?.sicom?.extracto_coverage?.matched_lotes ?? "—"} / {summaryHead?.sicom?.extracto_coverage?.total_lotes ?? "—"}</b></div>
                <div>Importe conciliado por lote: <b>${formatNumber(summaryHead?.sicom?.extracto_coverage?.matched_amount)}</b></div>
                <div>Cobertura por cantidad: <b>{formatNumber(summaryHead?.sicom?.extracto_coverage?.coverage_count_pct)}%</b></div>
                <div>Cobertura por importe: <b>{formatNumber(summaryHead?.sicom?.extracto_coverage?.coverage_amount_pct)}%</b></div>
              </div>
              <div>
                <div class="font-medium">2. Trazabilidad operativa `PILAGA → SICOM`</div>
                <div class="mt-1">Filas con match OP + importe: <b>{summaryHead?.sicom?.pilaga_coverage?.matched_rows ?? "—"}</b></div>
                <div>OP únicas con match: <b>{summaryHead?.sicom?.pilaga_coverage?.matched_unique_ops ?? "—"}</b></div>
                <div>Importe trazado: <b>${formatNumber(summaryHead?.sicom?.pilaga_coverage?.matched_amount)}</b></div>
              </div>
              <div>
                <div class="font-medium">3. Cierre efectivo `PILAGA → SICOM → extracto`</div>
                <div class="mt-1">Filas PILAGA con contraparte bancaria: <b>{summaryHead?.sicom?.final_reconciliation?.pilaga_rows_with_extracto ?? "—"}</b></div>
                <div>OP únicas con contraparte bancaria: <b>{summaryHead?.sicom?.final_reconciliation?.pilaga_unique_ops_with_extracto ?? "—"}</b></div>
                <div>Importe bruto de egresos PILAGA trazados: <b>${formatNumber(summaryHead?.sicom?.final_reconciliation?.pilaga_amount_with_extracto)}</b></div>
                <div>Lotes de extracto con soporte contable: <b>{summaryHead?.sicom?.final_reconciliation?.extracto_lotes_with_contable_support ?? "—"}</b></div>
                <div>Importe de extracto con soporte contable: <b>${formatNumber(summaryHead?.sicom?.final_reconciliation?.extracto_amount_with_contable_support)}</b></div>
              </div>
            </div>
            <div class="mt-4 text-sm grid grid-cols-1 md:grid-cols-2 gap-3">
              <div class="rounded-lg border border-base-300 p-3">
                <div class="font-medium">Explicado por SICOM pero no cerrado contra extracto</div>
                <div class="mt-1">Filas PILAGA solo trazadas: <b>{summaryHead?.sicom?.final_reconciliation?.pilaga_rows_traced_only ?? "—"}</b></div>
                <div>Importe bruto solo trazado: <b>${formatNumber(summaryHead?.sicom?.final_reconciliation?.pilaga_amount_traced_only)}</b></div>
              </div>
              <div class="rounded-lg border border-base-300 p-3">
                <div class="font-medium">Lotes de extracto explicados por SICOM sin soporte contable</div>
                <div class="mt-1">Lotes: <b>{summaryHead?.sicom?.final_reconciliation?.extracto_lotes_only_sicom ?? "—"}</b></div>
                <div>Importe: <b>${formatNumber(summaryHead?.sicom?.final_reconciliation?.extracto_amount_only_sicom)}</b></div>
              </div>
            </div>
          </div>
        </div>
      {/if}

      <div class="card bg-base-200 mt-4">
        <div class="card-body">
          <h4 class="font-semibold">Descomposición de movimientos</h4>
          {#if descomposicion}
            <p class="text-sm opacity-80">
              Estas categorías describen el motor directo de matching (`1→1`, agrupados y sugeridos).
              No equivalen por sí solas al cierre final vía `SICOM`.
            </p>
            <div class="flex justify-end mb-2">
              <CopyTableButton tableId="descomposicion-table" />
            </div>
            <div class="overflow-x-auto">
              <table id="descomposicion-table" class="table table-sm">
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

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-sm">
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">PILAGA sin reflejo bancario directo</div>
          <div class="stat-value text-lg">{summaryHead?.no_en_banco ?? "—"}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Banco sin reflejo contable directo</div>
          <div class="stat-value text-lg">{summaryHead?.no_en_pilaga ?? "—"}</div>
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
