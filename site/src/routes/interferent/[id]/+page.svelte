<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { getSite } from '$lib/context';
	import { RANGE_MIN_BYTES } from '$lib/data/store';
	import { dataHref } from '$lib/data/href';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';
	import Explorer from '$lib/components/Explorer.svelte';
	import NotFound from '$lib/components/NotFound.svelte';

	const site = getSite();
	const interferent = $derived(site.index?.interferentById.get(page.params.id ?? '') ?? null);
	const analyte = $derived(interferent ? (site.index?.analyteById.get(interferent.analyte_id) ?? null) : null);
	// a file that is read whole is preloaded; a large one is read by range requests instead
	const file = $derived.by(() => {
		const f = analyte ? site.data.manifest?.files.slim[analyte.analyte_id] : undefined;
		return f && f.bytes < RANGE_MIN_BYTES ? f.path : undefined;
	});
	const concept = $derived(interferent ? site.index?.conceptById.get(interferent.concept) : null);
</script>

<!-- the page's data starts downloading with the HTML, before any script has run -->
<svelte:head>{#if file}<link rel="preload" as="fetch" crossorigin="anonymous" href={dataHref(file)} />{/if}</svelte:head>

{#if interferent && analyte}
	<Seo title="{interferent.interferent_canonical} on {analyte.component}" description="{f.int(interferent.evidence_rows)} source-cited evidence rows on how {interferent.interferent_canonical} changes the measurement of {analyte.component} in {analyte.system}." />
	<header class="wrap head">
		<p class="eyebrow">Interferent · <a href="{base}/analyte/{analyte.analyte_id}/">{analyte.component}</a></p>
		<h1>{interferent.interferent_canonical}</h1>
		<dl>
			<div><dt>Analyte</dt><dd><a href="{base}/analyte/{analyte.analyte_id}/">{analyte.component}</a></dd></div>
			<div><dt>Default APS</dt><dd>{f.aps(analyte.aps_percent)}</dd></div>
			<div><dt>Evidence rows</dt><dd>{f.int(interferent.evidence_rows)}</dd></div>
			<div><dt>Wordings in the sources</dt><dd>{f.int(interferent.wording_variants)}</dd></div>
		</dl>
		{#if concept}
			<p class="note">
				Concept: <a href="{base}/concept/{concept.concept}/" data-testid="concept-link">{concept.label} across {concept.byAnalyte.size} {concept.byAnalyte.size === 1 ? 'analyte' : 'analytes'}</a>
			</p>
		{/if}
	</header>
	{#key interferent.interferent_id}<Explorer {analyte} {interferent} />{/key}
{:else}
	<NotFound what="interferent" />
{/if}

<style>
	.head {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: 28px;
	}
	h1 {
		margin-bottom: 24px;
		font-size: clamp(2rem, 1.6rem + 1.8vw, 2.75rem);
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
		margin: 0;
		font-size: 0.9375rem;
	}
</style>
