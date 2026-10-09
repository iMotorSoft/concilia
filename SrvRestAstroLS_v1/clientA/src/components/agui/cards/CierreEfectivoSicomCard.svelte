<script lang="ts">
  const props = $props<{
    summary?: Record<string, any> | null;
  }>();

  const summary = $derived(props.summary ?? null);
  const finalRec = $derived(summary?.sicom?.final_reconciliation ?? null);

  function fmtMoney(value: number | string | null | undefined) {
    if (value === null || value === undefined) return "—";
    const num = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(num)) return "—";
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(num);
  }
</script>

{#if finalRec}
  <article class="card bg-base-100 border border-base-300 shadow-sm">
    <div class="card-body gap-3">
      <div>
        <h3 class="font-semibold text-lg">Cierre efectivo vía SICOM</h3>
        <p class="text-sm opacity-75">
          Muestra solo lo que efectivamente cierra en el circuito `PILAGA → SICOM → extracto`.
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
        <div class="stat bg-success/10 rounded-xl">
          <div class="stat-title">Filas PILAGA con banco</div>
          <div class="stat-value text-lg">{finalRec?.pilaga_rows_with_extracto ?? "—"}</div>
          <div class="stat-desc">{finalRec?.pilaga_unique_ops_with_extracto ?? "—"} OP únicas</div>
        </div>
        <div class="stat bg-success/10 rounded-xl">
          <div class="stat-title">Egresos PILAGA trazados</div>
          <div class="stat-value text-lg">{fmtMoney(finalRec?.pilaga_amount_with_extracto)}</div>
          <div class="stat-desc">Importe bruto, no saldo neto</div>
        </div>
        <div class="stat bg-base-200 rounded-xl">
          <div class="stat-title">Lotes banco con soporte contable</div>
          <div class="stat-value text-lg">{finalRec?.extracto_lotes_with_contable_support ?? "—"}</div>
          <div class="stat-desc">{fmtMoney(finalRec?.extracto_amount_with_contable_support)}</div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        <div class="rounded-xl border border-base-300 p-4">
          <div class="font-medium">Solo trazado por SICOM</div>
          <div class="mt-2">Filas PILAGA: <b>{finalRec?.pilaga_rows_traced_only ?? "—"}</b></div>
          <div>Importe bruto: <b>{fmtMoney(finalRec?.pilaga_amount_traced_only)}</b></div>
        </div>
        <div class="rounded-xl border border-base-300 p-4">
          <div class="font-medium">Lotes en extracto aún sin soporte contable</div>
          <div class="mt-2">Lotes: <b>{finalRec?.extracto_lotes_only_sicom ?? "—"}</b></div>
          <div>Importe: <b>{fmtMoney(finalRec?.extracto_amount_only_sicom)}</b></div>
        </div>
      </div>

      <div class="text-sm opacity-80">
        Banco(s) observados en el cierre final:
        <b>{(finalRec?.banks_in_final_reconciliation || []).join(", ") || "—"}</b>
      </div>
    </div>
  </article>
{/if}
