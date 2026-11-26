<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { PUBLIC_SITE_URL, sitePath } from '$lib/env';

	let { title, description }: { title: string; description: string } = $props();
	const full = $derived(title === 'C-LED' ? 'C-LED: Clinical Laboratory Error Database' : `${title} · C-LED`);
	const canonical = $derived(PUBLIC_SITE_URL ? PUBLIC_SITE_URL + sitePath(page.url.pathname, base) : '');
	const image = $derived(PUBLIC_SITE_URL ? `${PUBLIC_SITE_URL}/og.png` : `${base}/og.png`);
</script>

<svelte:head>
	<title>{full}</title>
	<meta name="description" content={description} />
	<meta property="og:type" content="website" />
	<meta property="og:site_name" content="C-LED" />
	<meta property="og:title" content={full} />
	<meta property="og:description" content={description} />
	<meta property="og:image" content={image} />
	<meta name="twitter:card" content="summary_large_image" />
	{#if canonical}<link rel="canonical" href={canonical} /><meta property="og:url" content={canonical} />{/if}
</svelte:head>
