<script lang="ts">
  import { authFetch as fetch } from '../../auth/transport.js';
  import { daysWindowStore, DEFAULT_DAYS_WINDOW, normalizeDaysWindow } from '../reconcileConfig';
  import CopyTableButton from '../CopyTableButton.svelte';

  type SicomLot = { banco_raw?: string; nro_pago?: string };
  type SicomOp = {
    op_key?: string;
    exact_matches?: { banco_raw?: string; nro_pago?: string }[];
    op_matches?: { banco_raw?: string; nro_pago?: string }[];
    op_match_count?: number;
  };
  type SimpleRow = {
    fecha: string;
    monto: number;
    documento: string;
    sicom?: {
      lot_matches?: SicomLot[];
      op_key?: string;
      exact_matches?: { banco_raw?: string; nro_pago?: string }[];
      op_matches?: { banco_raw?: string; nro_pago?: string }[];
      op_match_count?: number;
    } | null;
  };
  type GroupRow = {
    bank_row?: SimpleRow | null;
    pilaga_rows?: SimpleRow[];
    monto_total?: number;
    diff?: number;
    estado?: string;
    sicom_basis?: {
      mandatory?: boolean;
      nro_pago?: string;
      diff_vs_bank?: number;
    };
  };

  const props = $props<{
    urlRest: string;
    extractoUri: string;
    contableUri: string;
    sicomUri?: string;
    bankScope?: string;
    accountScope?: string;
  }>();

  const urlRest = $derived(props.urlRest || "");
  const extractoUri = $derived(props.extractoUri || "");
  const contableUri = $derived(props.contableUri || "");
  const sicomUri = $derived(props.sicomUri || "");
  const bankScope = $derived(props.bankScope || "");
  const accountScope = $derived(props.accountScope || "");

  const TITLE = "Agrupaciones contables → banco";
  const ENDPOINT = "/api/reconcile/details/n1/grupos";

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
let calculated = $state(false);

  function fmtMoney(value: number | string | null | undefined) {
    if (value === null || value === undefined) return "—";
    const num = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(num)) return "—";
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(num);
  }

  function countLabel(): string {
    if (typeof countDisplay === "number") {
      return `${countDisplay} grupos`;
    }
    return "— grupos";
  }

  function displayAmount(): number | null {
    if (typeof totalAmount === "number") return totalAmount;
    return null;
  }

function resetState() {
  expanded = false;
  loading = false;
  calculated = false;
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
    const sic = sicomUri || "";
    const fingerprint = `${extr}|${cont}|${sic}|${bankScope}|${accountScope}`;
    if (fingerprint === lastSourceFingerprint) return;
    lastSourceFingerprint = fingerprint;
    resetState();
  });

  async function toggleExpanded() {
    expanded = !expanded;
  }

  function sumPilaga(row: GroupRow): number {
    const list = row?.pilaga_rows || [];
    const s = list.reduce((acc, r) => acc + (Number(r?.monto) || 0), 0);
    return Number.isFinite(s) ? s : 0;
  }

  function bankSicomLabel(row?: SimpleRow | null): string {
    const lot = row?.sicom?.lot_matches?.[0];
    if (!lot) return "";
    return `${lot?.banco_raw || "SICOM"} · lote ${lot?.nro_pago || "—"}`;
  }

  function diffAmount(row: GroupRow): number {
    const diff = Number(row?.diff ?? row?.sicom_basis?.diff_vs_bank ?? 0);
    return Number.isFinite(diff) ? diff : 0;
  }

  function pilagaSicomLabel(row?: SimpleRow | null): string {
    const first = row?.sicom?.exact_matches?.[0];
    if (first) return `${row?.sicom?.op_key || "OP"} · lote ${first?.nro_pago || "—"}`;
    const lotes = Array.from(new Set((row?.sicom?.op_matches || []).map((item) => item?.nro_pago).filter(Boolean)));
    if (lotes.length === 1) return `${row?.sicom?.op_key || "OP"} · lote ${lotes[0]}`;
    if (lotes.length) return `${row?.sicom?.op_key || "OP"} · lotes ${lotes.join(", ")}`;
    if (row?.sicom?.op_key) return `${row.sicom.op_key} · ${row?.sicom?.op_match_count ?? 0} match(es)`;
    return "";
  }

  function extractOpKey(value?: string | null): string {
    const txt = String(value || "").toUpperCase();
    const match = txt.match(/(\d+\/\d{4})/);
    return match?.[1] || "";
  }

  function opListLabel(row: GroupRow): string {
    const keys = Array.from(new Set((row?.pilaga_rows || []).map((item) => extractOpKey(item?.documento)).filter(Boolean)));
    if (!keys.length) return "—";
    if (keys.length <= 4) return keys.join(", ");
    return `${keys.slice(0, 4).join(", ")} +${keys.length - 4}`;
  }

async function fetchData() {
  if (!extractoUri || !contableUri) {
    errorMsg = "Faltan archivos confirmados.";
    return;
  }
  if (calculated) return;
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
      fd.set("uri_sicom", sicomUri || "");
      fd.set("bank_scope", bankScope || "");
      fd.set("account_scope", accountScope || "");
      fd.set("days_window", String(daysWindow ?? DEFAULT_DAYS_WINDOW));

      const res = await fetch(`${urlRest}${ENDPOINT}`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (!payload?.ok) throw new Error(payload?.message || "Respuesta inválida.");

      rows = (payload.rows || []) as GroupRow[];
      const inferredCount = typeof payload.total === "number" ? payload.total : rows.length;
      countDisplay = inferredCount;
      const providedTotal = typeof payload.total_amount === "number" ? payload.total_amount : null;
      const inferredTotal = rows.reduce((acc, r) => acc + (Number(r?.monto_total) || sumPilaga(r)), 0);
      totalAmount = providedTotal ?? inferredTotal;
      calculated = true;
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
      disabled={loading || calculated}
      aria-busy={loading}
    >
      {#if loading}Calculando…{:else if calculated}Calculado{:else}Calcular{/if}
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
        <div class="flex justify-end mb-2">
          <CopyTableButton tableId="aprobados-n-a-uno-table" />
        </div>
        <div class="overflow-x-auto">
          <table id="aprobados-n-a-uno-table" class="table table-sm">
            <thead>
              <tr>
                <th>Fecha banco</th>
                <th>Monto banco</th>
                <th>Documento banco</th>
                <th># PILAGA</th>
                <th>OP involucradas</th>
                <th>Total PILAGA</th>
                <th>Diferencia</th>
              </tr>
            </thead>
            <tbody>
              {#each rows as r, index}
                <tr>
                  <td>{r?.bank_row?.fecha ?? "—"}</td>
                  <td>{fmtMoney(r?.bank_row?.monto)}</td>
                  <td class="max-w-[320px] truncate" title={r?.bank_row?.documento}>
                    <div>{r?.bank_row?.documento ?? "—"}</div>
                    {#if bankSicomLabel(r?.bank_row)}
                      <div class="text-xs opacity-70">{bankSicomLabel(r?.bank_row)}</div>
                    {/if}
                  </td>
                  <td>{r?.pilaga_rows?.length ?? 0}</td>
                  <td class="max-w-[260px] truncate" title={opListLabel(r)}>{opListLabel(r)}</td>
                  <td>{fmtMoney(r?.monto_total ?? sumPilaga(r))}</td>
                  <td>{fmtMoney(diffAmount(r))}</td>
                </tr>
                {#if (r?.pilaga_rows ?? []).length}
                  <tr class="bg-base-200/50">
                    <td colspan="7">
                      <div class="text-xs opacity-70 mb-1">Componentes PILAGA</div>
                      <div class="flex justify-end mb-2">
                        <CopyTableButton tableId={`aprobados-componentes-${index}`} />
                      </div>
                      <div class="overflow-x-auto">
                        <table id={`aprobados-componentes-${index}`} class="table table-xs">
                          <thead>
                            <tr>
                              <th>Fecha</th>
                              <th>Monto</th>
                              <th>OP</th>
                              <th>Documento</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each r.pilaga_rows as pr}
                              <tr>
                                <td>{pr?.fecha ?? "—"}</td>
                                <td>{fmtMoney(pr?.monto)}</td>
                                <td>{extractOpKey(pr?.documento) || "—"}</td>
                                <td class="max-w-[520px] truncate" title={pr?.documento}>
                                  <div>{pr?.documento ?? "—"}</div>
                                  {#if pilagaSicomLabel(pr)}
                                    <div class="text-xs opacity-70">{pilagaSicomLabel(pr)}</div>
                                  {/if}
                                </td>
                              </tr>
                            {/each}
                          </tbody>
                        </table>
                      </div>
                    </td>
                  </tr>
                {/if}
              {/each}
              {#if !rows.length}
                <tr><td colspan="7" class="opacity-60">Sin registros</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      {/if}

      <div class="flex justify-end">
        <button
          class="btn btn-xs btn-outline"
          on:click|preventDefault={fetchData}
          disabled={loading || calculated}
          aria-busy={loading}
        >
          {#if loading}Actualizando…{:else}Refrescar{/if}
        </button>
      </div>
    </div>
  {/if}
</article>
