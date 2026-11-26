<script lang="ts">
	import Seo from '$lib/components/Seo.svelte';
	let { data } = $props();
</script>

<Seo title="Changelog" description="What changed in each version of the EFLM Laboratory Error Database, and why." />
<div class="wrap page prose">
	<p class="eyebrow">Versions</p>
	<h1>Changelog</h1>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- built from the repository's own CHANGELOG.md -->
	{@html data.html}
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
</style>
