<script lang="ts">
  let { tableId }: { tableId: string } = $props();

  function cellForExcel(value: string): string {
    const text = String(value ?? "").replace(/[\t\r\n]+/g, " ").trim();
    if (!text || text === "—") return "";

    // Los importes se muestran con locale es-AR ($ 1.234,56), pero para la
    // copia se entregan sin símbolo ni miles y con punto decimal.
    if (!text.includes("$") || /[A-Za-zÁÉÍÓÚÑáéíóúñ]/.test(text)) return text;
    const numeric = text.replace(/[^\d,.-]/g, "");
    if (/^-?\d{1,3}(?:\.\d{3})+,\d+$/.test(numeric)) {
      return numeric.replace(/\./g, "").replace(",", ".");
    }
    if (/^-?\d+,\d+$/.test(numeric)) return numeric.replace(",", ".");
    return numeric;
  }

  function tableToTsv(table: HTMLTableElement): string {
    return Array.from(table.querySelectorAll(":scope > thead > tr, :scope > tbody > tr, :scope > tfoot > tr"))
      .filter((row) => !row.querySelector("table"))
      .map((row) => Array.from(row.querySelectorAll(":scope > th, :scope > td"))
        .map((cell) => cellForExcel((cell as HTMLElement).innerText))
        .join("\t"))
      .filter(Boolean)
      .join("\n");
  }

  async function copy(): Promise<void> {
    const table = document.getElementById(tableId) as HTMLTableElement | null;
    if (!table) return;
    const text = tableToTsv(table);
    if (!text) return;

    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
</script>

<button class="btn btn-xs btn-outline" type="button" on:click|preventDefault={copy} aria-label="Copiar tabla para Excel">
  Copiar
</button>
