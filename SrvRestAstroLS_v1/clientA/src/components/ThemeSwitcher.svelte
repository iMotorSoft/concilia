<script>
  import { onMount } from "svelte";

  const themes = [
    "light","dark","cupcake","bumblebee","emerald","corporate","synthwave","retro",
    "cyberpunk","valentine","halloween","garden","forest","aqua","lofi","pastel",
    "fantasy","wireframe","black","luxury","dracula","cmyk","autumn","business",
    "acid","lemonade","night","coffee","winter","dim","nord","sunset","caramellatte","abyss","silk"
  ];

  let theme = "light"; // valor por defecto

  onMount(() => {
    // ✅ Esto sólo corre en el browser
    theme =
      localStorage.getItem("theme") ||
      document.documentElement.getAttribute("data-theme") ||
      "light";

    document.documentElement.setAttribute("data-theme", theme);
  });

  // Cada vez que cambie `theme`, actualizamos
  $: if (typeof window !== "undefined") {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }
</script>

<div class="form-control w-full max-w-xs">
  <label class="label"><span class="label-text">Tema</span></label>
  <select class="select select-bordered" bind:value={theme}>
    {#each themes as t}
      <option value={t}>{t}</option>
    {/each}
  </select>
</div>

