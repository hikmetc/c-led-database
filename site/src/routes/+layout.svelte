<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { buildIndex } from '$lib/site';
	import { setSite } from '$lib/context';
	import { warmUp } from '$lib/data/db';
	import Nav from '$lib/components/Nav.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Drawer from '$lib/components/Drawer.svelte';

	let { data, children } = $props();
	const index = $derived(buildIndex(data));
	setSite({
		get data() {
			return data;
		},
		get index() {
			return index;
		}
	});

	onMount(() => {
		// DuckDB loads only after the page has painted and the browser is idle.
		if (!data.manifest) return;
		const idle = window.requestIdleCallback ?? ((cb: () => void) => setTimeout(cb, 200));
		idle(() => warmUp());
	});
</script>

<a class="skip" href="#main">Skip to content</a>
<Nav />
{#if data.manifestError}
	<div class="banner" role="alert">
		<div class="wrap">
			<strong>The data cannot be shown.</strong>
			{data.manifestError} No evidence is displayed, to avoid showing wrong data.
		</div>
	</div>
{/if}
<main id="main" tabindex="-1">
	{@render children()}
</main>
<Footer />
<Drawer />

<style>
	main {
		min-height: 60vh;
		outline: none;
	}
	.banner {
		background: var(--exceeds);
		color: #000;
		padding: 14px 0;
		font-size: 0.9375rem;
	}
</style>
