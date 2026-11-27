<script lang="ts">
	import { base } from '$app/paths';
	import { getSite } from '$lib/context';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';

	const site = getSite();
	const index = $derived(site.index);
	const stats = $derived(site.data.stats);
	const refs = $derived(stats?.by_reference_status ?? null);
	const plottable = $derived(stats ? Object.values(stats.plottable_by_analyte).reduce((a, b) => a + b, 0) : 0);
</script>

<Seo title="Methods" description="How the EFLM Laboratory Error Database is structured: what counts as evidence, how rows are judged against an analytical performance specification, and the known limitations." />
<div class="wrap page prose">
	<p class="eyebrow">Methods</p>
	<h1>How the database is built</h1>
	<p class="lede">This page describes the structure and rules of the data as documented in the repository. It does not describe how the literature was searched or selected; see the open points at the end.</p>

	<h2>Design principles</h2>
	<ul>
		<li><strong>The evidence tables are the source of truth.</strong> They are plain CSV files, one folder per analyte. Everything else is regenerated from them and the build never writes to them.</li>
		<li><strong>The source text is kept verbatim.</strong> Wording, spelling and units are preserved exactly as each paper printed them. Normalisation is added alongside as derived fields, never by overwriting the original.</li>
		<li><strong>One controlled vocabulary.</strong> Every analyte and every canonical interference cause is defined in one registry. The same cause is worded differently by nearly every paper, so each verbatim wording is mapped to one canonical cause.</li>
		<li><strong>No identifier is ever invented.</strong> A DOI or PubMed ID is written only when it was read from the source or resolved against PubMed or Crossref, and then with its provenance recorded.</li>
		<li><strong>A row with no data is not evidence.</strong></li>
	</ul>

	<h2>What counts as evidence</h2>
	<p>A row with no value in any of eleven data fields is not evidence and is removed. The eleven are direction of effect, the four change columns, magnitude, baseline and final concentration, interferent concentration, platform and analyzer. Removed rows are archived in full, with the reason, in the repository.</p>

	<h2>Rejection criteria</h2>
	<p>Before a table enters the database, every row is screened. A row is rejected, and archived with the reason, when:</p>
	<ul>
		<li>there is not enough information to find its source: no DOI, no PubMed ID, no full reference, and a citation without an author and a year;</li>
		<li>it has no citation;</li>
		<li>it has no value in any of the eleven data fields;</li>
		<li>it duplicates another row: same source, platform, analyzer, concentrations and values;</li>
		<li>its DOI is malformed or unknown to doi.org;</li>
		<li>its recorded APS verdict contradicts its numeric change;</li>
		<li>it comes from an animal study: the specimen is not human;</li>
		<li>its specimen is not the one the analyte is defined for, for example venous blood for an analyte defined in arterial blood (unless the specimen is itself the interference under study);</li>
		<li>the maintainer finds that the source did not measure the analyte, that the cited file is not the article, or that the row is out of scope.</li>
	</ul>
	<p>The first eight are decided automatically from the row; the last three need a person. Animal studies are excluded altogether. Rejected rows are kept, in full, in the repository (<code>meta/rejected_rows.csv</code>).</p>

	<h2>The analytical performance specification</h2>
	<p>Each analyte carries one APS: a relative allowable bias, in percent. A row with a numeric percent change exceeds the APS when the absolute change is greater than it. The APS is data, so this site can re-judge every row against an APS you choose. Where a row reports no numeric change, it cannot be recomputed; the verdict recorded during extraction is shown and the row is marked "not computable".</p>
	{#if index}
		<div class="table-scroll">
			<table class="plain-table">
				<thead><tr><th scope="col">Analyte</th><th scope="col">System</th><th scope="col" class="num">Default APS</th><th scope="col">Type and note</th></tr></thead>
				<tbody>
					{#each index.analytes as a (a.analyte_id)}
						<tr>
							<th scope="row"><a href="{base}/analyte/{a.analyte_id}/">{a.component}</a></th>
							<td>{a.system}</td>
							<td class="num">{Number.isFinite(a.aps_percent) ? f.aps(a.aps_percent) : 'n/a'}</td>
							<td>{a.aps_type}{a.aps_note ? `. ${a.aps_note}` : ''}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
	<p>The <em>significant-bias threshold</em> column is something else: it is the criterion the source study itself used, often a statistical test and often not reported. The two are never conflated.</p>

	<h2>Effect size</h2>
	<p>The primary effect size is the percent change derived from the baseline and final values printed in the source; where that is absent, the percent change printed by the paper itself is used. Concentrations and absolute changes keep their units inside the text, because sources report in incompatible units, and are not plotted.</p>
	{#if stats}
		<p>{f.int(plottable)} of {f.int(stats.generated_rows)} rows ({Math.round((plottable / stats.generated_rows) * 100)} %) carry a numeric percent change. Many sources report an effect only in words or only in absolute units. Charts on this site draw only rows with a numeric value and always say how many rows were left out; a missing value is never read as zero.</p>
	{/if}

	<h2>Study appraisal</h2>
	<p>Each row records four appraisal fields: whether the interferent concentration tested can occur in patients, whether the study design is appropriate for an interference claim, whether the effect matters clinically, and how well the experiment reflects routine practice. Additional sources of bias are recorded as free text.</p>

	<h2>References</h2>
	<p>Every row must identify its source.{#if refs && stats} Of {f.int(stats.generated_rows)} rows, {f.int(refs.doi ?? 0)} carry a DOI, {f.int(refs.pmid ?? 0)} carry a PubMed ID but no DOI, and {f.int(refs.reference_only ?? 0)} carry a full bibliographic reference only.{/if} When an identifier is missing from the source table but can be established, it is recorded separately with the method used and what it was checked against; the source tables are never edited to add it, and nothing is guessed.</p>

	<h2>Known limitations</h2>
	<ul>
		<li>A numeric percent change is present for only part of the rows (see above).</li>
		<li>Concentration and change columns keep their units inside the text and are not directly comparable across sources.</li>
		<li>The recorded APS verdict is parsed from prose written during extraction, so "other" and "not computable" both occur.</li>
		<li>A row identifier shifts if rows are inserted in the middle of a table rather than appended, so a row permalink is stable only while rows are appended.</li>
		<li>Some interferent names in the sources carry a non-English gloss in brackets, kept verbatim.</li>
	</ul>

	<h2>Open points</h2>
	<div class="todo"><strong>TODO.</strong> Literature search strategy, sources searched, dates and inclusion criteria are not documented in the repository.</div>
	<div class="todo"><strong>TODO.</strong> Who extracted the data, with which tools, and how extraction and appraisal were checked is not documented in the repository.</div>
	<div class="todo"><strong>TODO.</strong> The source or rationale of each analyte's APS value is not documented beyond its type and note.</div>

	<p>Column definitions are in the <a href="{base}/data-dictionary/">data dictionary</a>.</p>
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
	h1 {
		margin-bottom: 16px;
	}
	.table-scroll {
		margin-bottom: 1em;
	}
	.plain-table th[scope='row'] {
		font-weight: 600;
		white-space: normal;
	}
</style>
