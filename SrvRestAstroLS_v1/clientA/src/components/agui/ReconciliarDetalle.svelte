<script lang="ts">
  const {
    urlRest,
    threadId: _threadId,
    extractoUri,
    contableUri,
    daysWindow = 5,
  } = $props<{
    urlRest: string;
    threadId: string;
    extractoUri: string;
    contableUri: string;
    daysWindow?: number;
  }>();

  let loading = $state(false);
  let errorMsg: string | null = $state(null);
  let noEnBancoRows: Array<{fecha:string, monto:number, documento:string}> = $state([]);
  let noEnPilagaRows: Array<{fecha:string, monto:number, documento:string}> = $state([]);

  function fmtMoney(n: number | string | null | undefined) {
    const v = typeof n === "number" ? n : (n ? Number(n) : 0);
    if (Number.isNaN(v)) return "—";
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(v);
  }

  async function fetchDetails(
    uriExtracto: string = extractoUri,
    uriContable: string = contableUri,
    windowDays: number = daysWindow ?? 5
  ) {
    loading = true; errorMsg = null;
    try {
      const fd = new FormData();
      fd.set("uri_extracto", uriExtracto || "");
      fd.set("uri_contable", uriContable || "");
      fd.set("days_window", String(windowDays ?? 5));

      const res = await fetch(`${urlRest}/api/reconcile/details`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();

      if (!j?.ok) throw new Error(j?.message || "Respuesta inválida.");

      noEnBancoRows   = j.no_en_banco_rows || [];
      noEnPilagaRows  = j.no_en_pilaga_rows || [];
    } catch (e:any) {
      errorMsg = e?.message || "No se pudo cargar el detalle.";
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    // Reintenta cuando cambian los props relevantes
    fetchDetails(extractoUri, contableUri, daysWindow ?? 5);
  });
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm mt-4">
  <div class="card-body">
    <div class="flex items-center gap-2 mb-2">
      <h3 class="font-semibold text-lg">Detalle de no conciliados</h3>
      {#if loading}<span class="loading loading-spinner loading-sm" />{/if}
      {#if errorMsg}<span class="badge badge-error">{errorMsg}</span>{/if}
      {#if !loading && !errorMsg}
        <button class="btn btn-xs btn-outline ml-auto" on:click|preventDefault={fetchDetails}>Refrescar</button>
      {/if}
    </div>

    <!-- PILAGA NO reflejado en Banco -->
    <div class="mt-2">
      <div class="flex items-center gap-2 mb-2">
        <h4 class="font-semibold">PILAGA NO reflejado en Banco</h4>
        <span class="badge">{noEnBancoRows.length}</span>
      </div>
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
            {#each noEnBancoRows as r}
              <tr>
                <td>{r.fecha}</td>
                <td>{fmtMoney(r.monto)}</td>
                <td class="max-w-[520px] truncate" title={r.documento}>{r.documento}</td>
              </tr>
            {/each}
            {#if !noEnBancoRows.length && !loading}
              <tr><td colspan="3" class="opacity-60">Sin registros</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Banco NO reflejado en PILAGA -->
    <div class="mt-6">
      <div class="flex items-center gap-2 mb-2">
        <h4 class="font-semibold">Banco NO reflejado en PILAGA</h4>
        <span class="badge">{noEnPilagaRows.length}</span>
      </div>
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
            {#each noEnPilagaRows as r}
              <tr>
                <td>{r.fecha}</td>
                <td>{fmtMoney(r.monto)}</td>
                <td class="max-w-[520px] truncate" title={r.documento}>{r.documento}</td>
              </tr>
            {/each}
            {#if !noEnPilagaRows.length && !loading}
              <tr><td colspan="3" class="opacity-60">Sin registros</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>
