<script lang="ts">
  import CierreEfectivoSicomCard from './cards/CierreEfectivoSicomCard.svelte';
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
    sicomUri = "",
    bankScope = "",
    accountScope = "",
    summary = null,
  } = $props<{
    urlRest: string;
    threadId: string;
    extractoUri: string;
    contableUri: string;
    sicomUri?: string;
    bankScope?: string;
    accountScope?: string;
    summary?: Record<string, any> | null;
  }>();
</script>

<section class="mt-4 space-y-4">
  <CierreEfectivoSicomCard summary={summary} />
  <NoBancoCard
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    sicomUri={sicomUri}
    bankScope={bankScope}
    accountScope={accountScope}
    summary={summary}
  />
  <NoContableCard
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    sicomUri={sicomUri}
    bankScope={bankScope}
    accountScope={accountScope}
    summary={summary}
  />
  <Conciliados11Card
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    sicomUri={sicomUri}
    bankScope={bankScope}
    accountScope={accountScope}
  />
  <AprobadosN1Card
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    sicomUri={sicomUri}
    bankScope={bankScope}
    accountScope={accountScope}
  />
  <SugeridosN1Card
    urlRest={urlRest}
    extractoUri={extractoUri}
    contableUri={contableUri}
    sicomUri={sicomUri}
    bankScope={bankScope}
    accountScope={accountScope}
  />
</section>
