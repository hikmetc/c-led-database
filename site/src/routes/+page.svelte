<script lang="ts">
	import { base } from '$app/paths';
	import { getSite } from '$lib/context';
	import { SITE_NAME, SITE_STAGE } from '$lib/env';
	import { RANGE_MIN_BYTES } from '$lib/data/store';
	import { dataHref } from '$lib/data/href';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';
	import SearchBox from '$lib/components/SearchBox.svelte';
	import Kpi from '$lib/components/Kpi.svelte';
	import Matrix from '$lib/components/Matrix.svelte';

	const site = getSite();
	const index = $derived(site.index);
	const stats = $derived(site.data.stats);
	const identified = $derived.by(() => {
		const s = stats?.by_reference_status;
		if (!s || !stats?.generated_rows) return null;
		return Math.round((((s.doi ?? 0) + (s.pmid ?? 0)) / stats.generated_rows) * 100);
	});
</script>

<Seo title={SITE_NAME} description="{SITE_NAME} ({SITE_STAGE}): structured, source-cited evidence on how interferents bias clinical laboratory measurements, judged against an analytical performance specification for each analyte." />

<svelte:head>{#if index && index.manifest.files.slim_all.bytes < RANGE_MIN_BYTES}<link rel="preload" as="fetch" crossorigin="anonymous" href={dataHref(index.manifest.files.slim_all.path)} />{/if}</svelte:head>

<section class="hero">
	<div class="wrap">
		<p class="stage">{SITE_STAGE}</p>
		<h1>{SITE_NAME}</h1>
		<p class="lede">Source-cited evidence on how interferents bias clinical laboratory measurements, judged against an analytical performance specification for each analyte.</p>
		<div class="search"><SearchBox large /></div>
	</div>
</section>

{#if index && stats}
	<section class="kpis" aria-label="The database in numbers">
		<dl class="wrap" data-testid="kpis">
			<Kpi value={stats.generated_rows} label="Evidence rows" />
			<Kpi value={index.analytes.length} label="Analytes" />
			<Kpi value={index.interferentById.size} label="Interference causes" />
			{#if stats.references}<Kpi value={stats.references} label="Distinct references" />{/if}
			{#if identified !== null}<Kpi value={identified} suffix=" %" label="Rows with a DOI or PubMed ID" />{/if}
		</dl>
	</section>

	<section class="section alt" id="matrix" aria-labelledby="matrix-h">
		<div class="wrap">
			<p class="eyebrow">Across analytes</p>
			<h2 id="matrix-h">Which interference affects which analyte</h2>
			<p class="lede">{index.concepts.length} interference concepts across {index.analytes.length} analytes. Darker cells are those where more of the numeric results exceed the analyte's performance specification.</p>
			<div class="mx"><Matrix /></div>
		</div>
	</section>

	<section class="section" id="analytes" aria-labelledby="analytes-h">
		<div class="wrap">
			<p class="eyebrow">Analytes</p>
			<h2 id="analytes-h">Start from an analyte</h2>
			<ul class="cards" data-testid="analyte-cards">
				{#each index.analytes as a (a.analyte_id)}
					<li>
						<a class="card" href="{base}/analyte/{a.analyte_id}/">
							<h3>{a.component}</h3>
							<p class="sys">{a.system}{a.unit ? ` · ${a.unit}` : ''}</p>
							<dl>
								<div><dt>Default APS</dt><dd>{Number.isFinite(a.aps_percent) ? f.aps(a.aps_percent) : 'n/a'}</dd></div>
								<div><dt>Evidence rows</dt><dd>{f.int(a.rows)}</dd></div>
							</dl>
							{#if a.interferents.length}
								<p class="caption top">Most evidence: {a.interferents.slice(0, 3).map((i) => i.interferent_canonical).join('; ')}</p>
							{/if}
						</a>
					</li>
				{/each}
			</ul>
		</div>
	</section>
{/if}

<style>
	.hero {
		padding: clamp(64px, 12vw, 136px) 0 clamp(40px, 6vw, 72px);
		text-align: center;
	}
	.hero h1 {
		font-size: clamp(2.25rem, 1.2rem + 5.2vw, 4.5rem);
		letter-spacing: -0.02em;
		line-height: 1.05;
		max-width: 16ch;
		margin: 0 auto 24px;
	}
	.stage {
		display: inline-block;
		margin: 0 0 20px;
		padding: 4px 14px;
		border: 1px solid var(--control);
		border-radius: 980px;
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.03em;
		color: var(--text-2);
	}
	.hero .lede {
		margin: 0 auto 36px;
	}
	.search {
		display: flex;
		justify-content: center;
	}
	.kpis {
		padding-bottom: clamp(48px, 7vw, 88px);
	}
	.kpis dl {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 28px 24px;
		margin-top: 0;
		margin-bottom: 0;
	}
	h2 {
		margin-bottom: 16px;
	}
	.mx {
		margin-top: 40px;
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 16px;
		list-style: none;
		margin: 40px 0 0;
		padding: 0;
	}
	.card {
		display: flex;
		flex-direction: column;
		height: 100%;
		color: var(--text);
		transition: transform var(--dur) var(--ease);
	}
	.card:hover {
		text-decoration: none;
		transform: translateY(-2px);
		border-color: var(--control);
	}
	.sys {
		color: var(--text-2);
		font-size: 0.875rem;
		margin: 6px 0 20px;
	}
	.card dl {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
		margin: auto 0 0;
	}
	.card dt {
		font-size: 0.75rem;
		color: var(--text-2);
	}
	.card dd {
		margin: 0;
		font-size: 1.3125rem;
		font-weight: 600;
	}
	.top {
		margin: 16px 0 0;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
</style>
