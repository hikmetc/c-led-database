<script lang="ts">
	import { base } from '$app/paths';
	import { getSite } from '$lib/context';
	import { REPO_URL } from '$lib/env';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';

	const site = getSite();
	const manifest = $derived(site.data.manifest);
	const index = $derived(site.index);
	const total = $derived.by(() => {
		if (!manifest) return 0;
		const fl = manifest.files;
		return fl.slim_all.bytes + Object.values(fl.slim).reduce((s, x) => s + x.bytes, 0) + Object.values(fl.detail).reduce((s, x) => s + x.bytes, 0);
	});
</script>

<Seo title="Downloads" description="Download the EFLM Laboratory Error Database: the source CSV tables on GitHub, and the Parquet files this website reads." />
<div class="wrap page">
	<p class="eyebrow">Data</p>
	<h1>Downloads</h1>
	<p class="lede">The evidence tables are plain CSV files in the repository. The website reads a compact Parquet copy of the same rows, which you can download here.</p>

	<div class="grid">
		<div class="card">
			<h2>Source tables</h2>
			<p>CSV evidence tables, one folder per analyte, with the registries and the build scripts.</p>
			{#if REPO_URL}<a class="btn primary" href={REPO_URL} rel="noopener">Open the repository on GitHub</a>{:else}<p class="caption">The repository link is set when the site is deployed.</p>{/if}
		</div>
		<div class="card">
			<h2>Parquet bundle</h2>
			<p>All Parquet files and the three registry files in one archive, attached to each published release.</p>
			{#if REPO_URL}
				<a class="btn" href="{REPO_URL}/releases/latest/download/cled-parquet.zip" rel="noopener">cled-parquet.zip (latest release)</a>
				<p class="caption note">Available once a release has been published; see <a href="{REPO_URL}/releases" rel="noopener">releases</a>.</p>
			{:else}<p class="caption">The release link is set when the site is deployed.</p>{/if}
		</div>
	</div>

	{#if manifest && index}
		<h2 class="h">Parquet files</h2>
		<p class="caption">Schema version {manifest.schema_version} · {f.int(manifest.row_count)} rows · {f.bytes(total)} in total{manifest.compression ? ` · ${manifest.compression}` : ''}. Slim files hold the columns used for tables, filters and charts; detail files hold every source column, verbatim.</p>
		<div class="table-scroll">
			<table class="plain-table" data-testid="downloads-table">
				<thead><tr><th scope="col">Analyte</th><th scope="col" class="num">Rows</th><th scope="col">Slim</th><th scope="col">Detail</th></tr></thead>
				<tbody>
					<tr>
						<th scope="row">All analytes</th>
						<td class="num">{f.int(manifest.files.slim_all.rows)}</td>
						<td><a href="{base}/data/{manifest.files.slim_all.path}" download>{manifest.files.slim_all.path.split('/').pop()}</a> <span class="muted">{f.bytes(manifest.files.slim_all.bytes)}</span></td>
						<td><span class="muted">per analyte, below</span></td>
					</tr>
					{#each index.analytes as a (a.analyte_id)}
						{@const s = manifest.files.slim[a.analyte_id]}
						{@const d = manifest.files.detail[a.analyte_id]}
						<tr>
							<th scope="row">{a.component}</th>
							<td class="num">{f.int(s.rows)}</td>
							<td><a href="{base}/data/{s.path}" download>{s.path.split('/').slice(-2).join('/')}</a> <span class="muted">{f.bytes(s.bytes)}</span></td>
							<td><a href="{base}/data/{d.path}" download>{d.path.split('/').slice(-2).join('/')}</a> <span class="muted">{f.bytes(d.bytes)}</span></td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="caption after">
			Registry files: <a href="{base}/data/parquet/manifest.json">manifest.json</a> · <a href="{base}/data/analytes.json">analytes.json</a> · <a href="{base}/data/interferents.json">interferents.json</a> · <a href="{base}/data/stats.json">stats.json</a>.
			Column definitions are in the <a href="{base}/data-dictionary/">data dictionary</a>. Full-text articles are not distributed.
		</p>
	{/if}
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
	h1 {
		margin-bottom: 16px;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 16px;
		margin: 40px 0 56px;
	}
	.card h2 {
		font-size: 1.3125rem;
		margin-bottom: 8px;
	}
	.note {
		margin: 12px 0 0;
	}
	.h {
		margin-bottom: 8px;
	}
	.plain-table th[scope='row'] {
		color: var(--text);
		font-weight: 600;
		white-space: normal;
	}
	.table-scroll {
		margin-top: 16px;
	}
	.after {
		margin-top: 16px;
		max-width: 52rem;
	}
</style>
