<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { getSite } from '$lib/context';
	import { RANGE_MIN_BYTES } from '$lib/data/store';
	import { analyteTitle } from '$lib/site';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';
	import Explorer from '$lib/components/Explorer.svelte';
	import NotFound from '$lib/components/NotFound.svelte';

	const site = getSite();
	const analyte = $derived(site.index?.analyteById.get(page.params.id ?? '') ?? null);
	const refs = $derived(analyte ? analyte.interferents.length : 0);
	// a file that is read whole is preloaded; a large one is read by range requests instead
	const file = $derived.by(() => {
		const f = analyte ? site.data.manifest?.files.slim[analyte.analyte_id] : undefined;
		return f && f.bytes < RANGE_MIN_BYTES ? f.path : undefined;
	});
</script>

<!-- the page's data starts downloading with the HTML, before any script has run -->
<svelte:head>{#if file}<link rel="preload" as="fetch" crossorigin="anonymous" href="{base}/data/{file}" />{/if}</svelte:head>

{#if analyte}
	<Seo title={analyteTitle(analyte)} description="Interference evidence for {analyte.component} in {analyte.system}: {f.int(analyte.rows)} source-cited evidence rows across {refs} interference causes, judged against a {f.aps(analyte.aps_percent)} analytical performance specification." />
	<header class="wrap head">
		<p class="eyebrow">Analyte</p>
		<h1>{analyte.component}</h1>
		<dl>
			<div><dt>System</dt><dd>{analyte.system || f.NOT_REPORTED}</dd></div>
			<div><dt>Unit</dt><dd>{analyte.unit || f.NOT_REPORTED}</dd></div>
			<div><dt>Kind of property</dt><dd>{analyte.kind_of_property || f.NOT_REPORTED}</dd></div>
			<div><dt>Default APS</dt><dd data-testid="default-aps">{Number.isFinite(analyte.aps_percent) ? f.aps(analyte.aps_percent) : 'n/a'}</dd></div>
			<div><dt>Evidence rows</dt><dd data-testid="analyte-rows">{f.int(analyte.rows)}</dd></div>
			<div><dt>Interference causes</dt><dd>{f.int(analyte.interferents.length)}</dd></div>
		</dl>
		<p class="caption note">
			{#if analyte.aps_type}APS type: {analyte.aps_type}.{/if}
			{#if analyte.aps_note}{analyte.aps_note}{/if}
			{#if analyte.synonyms}Also written as: {analyte.synonyms}.{/if}
		</p>
	</header>
	{#key analyte.analyte_id}<Explorer {analyte} />{/key}
{:else}
	<NotFound what="analyte" />
{/if}

<style>
	.head {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: 28px;
	}
	h1 {
		margin-bottom: 24px;
	}
	dl {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 16px 24px;
		margin: 0 0 16px;
	}
	dt {
		font-size: 0.8125rem;
		color: var(--text-2);
	}
	dd {
		margin: 0;
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.note {
		max-width: 52rem;
		margin: 0;
	}
</style>
