<script lang="ts">
	import { base } from '$app/paths';
	import { getSite } from '$lib/context';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';

	const site = getSite();
	const index = $derived(site.index);
	const stats = $derived(site.data.stats);
</script>

<Seo title="About" description="What the EFLM Laboratory Error Database is, what it covers and what it does not." />
<div class="wrap page prose">
	<p class="eyebrow">About</p>
	<h1>About the database</h1>
	<p class="lede">The EFLM Laboratory Error Database is structured, source-cited evidence on how interferents bias clinical laboratory measurements, judged against an analytical performance specification (APS) for each analyte.</p>

	<h2>What one row is</h2>
	<p>One row of the database is one piece of published evidence that a named interferent changed the measurement of a named analyte. It is recorded with the direction and size of the error, the measurement platform it was observed on, an appraisal of the study, and a citation.</p>
	<p>Each analyte carries one analytical performance specification: a relative allowable bias. Every row is judged against it. On this site you can also judge the rows against an APS of your own.</p>

	<h2>Beta version</h2>
	<p>This is a beta version. The content and the structure of the database may still change.</p>

	<h2>Scope</h2>
	<p>The scope is analytical interference and pre-analytical error: things that make the measured value differ from the true value. It is not a database of reference intervals, clinical decision limits or drug effects on physiology.</p>
	{#if index && stats}
		<p>The database currently holds {f.int(stats.generated_rows)} evidence rows for {index.analytes.length} analytes and {f.int(index.interferentById.size)} interference causes{#if stats.references}, drawn from {f.int(stats.references)} distinct references{/if}.</p>
	{/if}

	<h2>Sources and full texts</h2>
	<p>Every row identifies its source by a DOI, a PubMed ID or a full bibliographic reference. Publisher full texts are not distributed, because they are under copyright; the source can always be retrieved at its publisher.</p>

	<h2>Privacy</h2>
	<p>This site has no analytics, no trackers and no cookies, and it makes no requests to third parties. All queries run in your browser. Your theme choice is stored in your browser only.</p>

	<h2>Not a substitute for judgement</h2>
	<div class="todo">
		<strong>TODO.</strong> A statement of intended use and its limits (for example whether the database is meant for research, education or laboratory practice) has not been provided.
	</div>

	<h2>Who maintains it</h2>
	<div class="todo">
		<strong>TODO.</strong> Authors, affiliations, funding and contact details have not been provided, so none are stated here.
	</div>

	<p>See <a href="{base}/methods/">Methods</a> for how the data are structured, and <a href="{base}/cite/">How to cite</a>.</p>
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
	h1 {
		margin-bottom: 16px;
	}
</style>
