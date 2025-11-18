<script lang="ts">
  import NoBancoCard from './cards/NoBancoCard.svelte';
  import NoContableCard from './cards/NoContableCard.svelte';
  import Conciliados11Card from './cards/Conciliados11Card.svelte';
  import AprobadosN1Card from './cards/AprobadosN1Card.svelte';
  import SugeridosN1Card from './cards/SugeridosN1Card.svelte';

  const {
    urlRest,
    threadId: _threadId,
    extractoUri,
    contableUri,
    summary = null,
  } = $props<{
    urlRest: string;
    threadId: string;
    extractoUri: string;
    contableUri: string;
    summary?: Record<string, any> | null;
  }>();
</script>

<section class="mt-4 space-y-4">
  <NoBancoCard
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    summary={summary}
  />
  <NoContableCard
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    summary={summary}
  />
  <Conciliados11Card
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
  />
  <AprobadosN1Card
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
  />
  <SugeridosN1Card
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
  />
</section>
