<script lang="ts">
	import { base } from '$app/paths';
	import SearchBox from './SearchBox.svelte';
	let { what = 'page' }: { what?: string } = $props();
</script>

<svelte:head><title>Not found · EFLM Laboratory Error Database</title><meta name="robots" content="noindex" /></svelte:head>
<section class="wrap nf">
	<p class="eyebrow">404</p>
	<h1>This {what} is not in the database.</h1>
	<p class="lede">The address may be mistyped, or the entry may have been renamed. Search for it, or start from the <a href="{base}/">overview</a>.</p>
	<SearchBox large />
</section>

<style>
	.nf {
		padding-top: clamp(64px, 10vw, 120px);
		padding-bottom: clamp(64px, 10vw, 120px);
	}
	h1 {
		margin-bottom: 16px;
	}
	.lede {
		margin-bottom: 32px;
	}
</style>
