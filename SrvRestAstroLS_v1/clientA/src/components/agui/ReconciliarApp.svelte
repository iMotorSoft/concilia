<script lang="ts">
  // /src/components/agui/ReconciliarApp.svelte
  // Wrapper temporal que reutiliza la app existente.
  import ConciliaApp from "./ConciliaApp.svelte";

  // Permitimos pasar threadId si querés fijarlo desde la página.
  export let threadId: string | undefined;
</script>

<ConciliaApp {threadId} />

