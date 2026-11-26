<script lang="ts">
	import { getSite } from '$lib/context';
	import Seo from '$lib/components/Seo.svelte';

	const site = getSite();
	const dictionary = $derived([...site.data.dictionary].sort((a, b) => a.position - b.position));
	const slim = $derived(site.data.manifest?.slim_columns ?? []);
	// Meaning of the derived fields, as documented in STRUCTURE.md (section 8).
	const DERIVED: Record<string, string> = {
		row_id: 'Stable identifier of the row: <analyte_id>.<table stem>.<row number in that table>.',
		analyte_id: 'Short identifier of the analyte.',
		interferent_id: 'Identifier of the canonical interference cause: <analyte_id>.<key>.',
		interferent_canonical: 'Canonical name of the interference cause.',
		concept: 'Cross-analyte concept the cause belongs to.',
		interferent_verbatim: 'The interferent exactly as named in the source.',
		direction: 'Direction of effect, normalised to up, down, none or not_reported.',
		direction_study: 'Direction judged against the source study’s own criterion, normalised.',
		direction_aps: 'Direction judged against the database APS, normalised.',
		pct_change: 'Signed percent change, numeric or null.',
		pct_change_source: 'Where pct_change comes from: calculated or as_reported.',
		plottable: 'True when pct_change is numeric.',
		aps_percent: 'The analyte’s analytical performance specification, in percent.',
		aps_verdict: 'exceeds, within, not_computable, not_reported or other, parsed from the source prose.',
		exceeds_aps: 'abs(pct_change) > aps_percent, or null.',
		has_effect_data: 'False when the row carries no direction, magnitude or percent change.',
		doi: 'DOI of the source, where one is recorded.',
		pmid: 'PubMed ID of the source, where one is recorded.',
		reference_status: 'How the row identifies its source: doi, pmid, reference_only, citation_only or unidentified.',
		reference_origin: 'source_table, or enriched when the identifier was recovered outside the source table.',
		source_file: 'The evidence table the row comes from.',
		source_row: 'Row number in that table.'
	};
</script>

<Seo title="Data dictionary" description="Definition of every column of the evidence tables and of the derived fields in the Parquet files." />
<div class="wrap wide page">
	<p class="eyebrow">Reference</p>
	<h1>Data dictionary</h1>
	<p class="lede">Every evidence table has the same {dictionary.length} columns, in the same order. Source text is kept verbatim; normalised fields are added alongside, never by overwriting the original.</p>

	<h2>Source columns</h2>
	<div class="table-scroll">
		<table class="plain-table" data-testid="dictionary-table">
			<thead><tr><th scope="col" class="num">#</th><th scope="col">Column</th><th scope="col">Parquet column</th><th scope="col">Type</th><th scope="col">Values</th><th scope="col">Definition</th></tr></thead>
			<tbody>
				{#each dictionary as d (d.position)}
					<tr>
						<td class="num">{d.position}</td>
						<th scope="row">{d.column}</th>
						<td><code>{d.parquet_column}</code></td>
						<td>{d.type}</td>
						<td>{d.values}</td>
						<td class="def">{d.definition}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if slim.length}
		<h2>Fields of the slim Parquet files</h2>
		<p class="caption">The slim files carry identifiers, normalised fields and the short text columns used for tables, filters and charts.</p>
		<div class="table-scroll">
			<table class="plain-table">
				<thead><tr><th scope="col">Field</th><th scope="col">Type</th><th scope="col">Meaning</th></tr></thead>
				<tbody>
					{#each slim as c (c.name)}
						<tr><th scope="row"><code>{c.name}</code></th><td>{c.type}</td><td class="def">{DERIVED[c.name] ?? 'Short form of the source column of the same meaning.'}</td></tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	<h2>Reading the columns correctly</h2>
	<ul class="prose">
		<li><strong>Significant-bias threshold is the source study's own criterion</strong>, not the database APS. It is often a statistical test and frequently not reported.</li>
		<li><strong>Percentage change (calculated) is the primary effect size.</strong> It is derived from the baseline and final values printed in the source. Percentage change (as reported) is what the paper printed itself, which is often absent.</li>
		<li><strong>The concentration and change columns carry their units inside the text</strong>, because sources report in incompatible units. They are not directly plottable.</li>
		<li><strong>"not reported in the information source" means the source does not state it.</strong> It never means zero, and is never plotted as zero.</li>
	</ul>
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
	h1 {
		margin-bottom: 16px;
	}
	h2 {
		margin: 56px 0 16px;
	}
	.plain-table th[scope='row'] {
		color: var(--text);
		white-space: normal;
		min-width: 160px;
	}
	.def {
		min-width: 280px;
	}
	code {
		overflow-wrap: anywhere;
	}
</style>
