<script lang="ts">
	import { page } from '$app/state';
	import RowView from '$lib/components/RowView.svelte';
	const rowId = $derived(page.params.row_id ?? '');
</script>

<svelte:head>
	<title>{rowId} · EFLM Laboratory Error Database</title>
	<meta name="description" content="Evidence row {rowId} of the EFLM Laboratory Error Database, with every source column and its reference." />
</svelte:head>
<div class="wrap page">
	{#key rowId}<RowView {rowId} />{/key}
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
		max-width: 880px;
	}
</style>
