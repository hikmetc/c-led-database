<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { getSite } from '$lib/context';
	import type { SlimRow } from '$lib/types';
	import { conceptRows } from '$lib/data/queries';
	import { summarize } from '$lib/aps';
	import { quantile } from '$lib/scales';
	import { drawerRow } from '$lib/stores';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';
	import ChartFrame from '$lib/components/ChartFrame.svelte';
	import EffectStrip, { type StripPoint } from '$lib/components/EffectStrip.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import NotFound from '$lib/components/NotFound.svelte';

	const site = getSite();
	const concept = $derived(site.index?.conceptById.get(page.params.concept ?? '') ?? null);
	let rows = $state<SlimRow[]>([]);
	let status = $state<'loading' | 'ready' | 'error'>('loading');
	let error = $state('');
	let attempt = $state(0);
	let scale = $state<'symlog' | 'linear'>('symlog');
	let beyond = $state(0);

	$effect(() => {
		const manifest = site.data.manifest;
		const c = concept?.concept;
		void attempt;
		if (!manifest || !c) return;
		if (typeof window === 'undefined') return;
		let cancelled = false;
		status = 'loading';
		conceptRows(manifest, c)
			.then((r) => {
				if (cancelled) return;
				rows = r;
				status = 'ready';
			})
			.catch((e) => {
				if (cancelled) return;
				error = e?.message ?? String(e);
				status = 'error';
			});
		return () => {
			cancelled = true;
		};
	});

	const perAnalyte = $derived.by(() => {
		if (!concept || !site.index) return [];
		return site.index.analytes
			.filter((a) => concept.byAnalyte.has(a.analyte_id))
			.map((a) => {
				const mine = rows.filter((r) => r.analyte_id === a.analyte_id);
				const s = summarize(mine, a.aps_percent);
				const v = mine.filter((r) => r.pct_change !== null).map((r) => r.pct_change!).sort((x, y) => x - y);
				return { analyte: a, interferents: concept.byAnalyte.get(a.analyte_id)!, s, v };
			});
	});
	const total = $derived.by(() => {
		const plottable = rows.filter((r) => r.pct_change !== null).length;
		return { plottable, notPlottable: rows.length - plottable };
	});
	const exceeds = $derived(perAnalyte.reduce((n, p) => n + p.s.exceeds, 0));
	const groups = $derived(perAnalyte.filter((p) => p.s.plottable > 0).map((p) => ({ key: p.analyte.analyte_id, label: `${p.analyte.component}  ·  APS ${f.aps(p.analyte.aps_percent)}  ·  ${p.s.exceeds}/${p.s.plottable}`, aps: p.analyte.aps_percent })));
	const cut = (s: string | null, n = 70) => (f.isNotReported(s) ? f.NOT_REPORTED : s!.length > n ? s!.slice(0, n - 1) + '…' : s!);
	const points: StripPoint[] = $derived(
		rows.filter((r) => r.pct_change !== null).map((r) => ({
			id: r.row_id,
			group: r.analyte_id,
			pct: r.pct_change!,
			tip: `${f.pct(r.pct_change)} · ${f.directionLabel(r.direction)}\n${cut(r.interferent_canonical)}\nAnalyzer: ${cut(r.analyzer)}\n${r.doi ? `DOI ${r.doi}` : r.pmid ? `PMID ${r.pmid}` : 'Full reference only'}`
		}))
	);
</script>

{#if concept}
	<Seo title="{concept.label} across analytes" description="{concept.label} as a cause of laboratory measurement error: {f.int(concept.rows)} source-cited evidence rows across {concept.byAnalyte.size} {concept.byAnalyte.size === 1 ? 'analyte' : 'analytes'}." />
	<header class="wrap head">
		<p class="eyebrow">Interference concept</p>
		<h1>{concept.label}</h1>
		<p class="lede">{f.int(concept.rows)} evidence rows across {concept.byAnalyte.size} {concept.byAnalyte.size === 1 ? 'analyte' : 'analytes'}. Each analyte is judged against its own default APS.</p>
	</header>
	<div class="wrap body">
		{#if !site.data.manifest}
			<StateBlock kind="error" message="The data manifest could not be read." />
		{:else if status === 'error'}
			<StateBlock kind="error" message={error} onretry={() => (attempt += 1)} />
		{:else if status === 'loading'}
			<StateBlock kind="loading" message="Loading evidence" height={320} />
		{:else}
			{#if groups.length}
				<ChartFrame
					image
					title="{f.int(exceeds)} of {f.int(total.plottable)} numeric {concept.label.toLowerCase()} results exceed their analyte's APS"
					alt="Strip charts of percent change for {concept.label}, one row per analyte on a shared axis, each with its own APS band. Use View as table for the numbers."
					caption="n = {f.int(total.plottable)} results with a numeric change; {f.int(total.notPlottable)} rows have no numeric value and are not drawn. One row per analyte, shared x axis; each shaded band is ± that analyte's default APS. ◆ outside the band, ○ inside."
					columns={['Analyte', 'Default APS', 'Rows', 'Numeric results', 'Exceed APS', 'Share', 'Minimum', 'Median', 'Maximum']}
					rows={perAnalyte.map((p) => [p.analyte.component, f.aps(p.analyte.aps_percent), p.s.rows, p.s.plottable, p.s.exceeds, f.share(p.s.share), p.v.length ? f.pct(p.v[0]) : 'n/a', p.v.length ? f.pct(quantile(p.v, 0.5)) : 'n/a', p.v.length ? f.pct(p.v[p.v.length - 1]) : 'n/a'])}
				>
					{#snippet controls()}
						<div class="scale" role="group" aria-label="Axis scale">
							<button class="btn" type="button" aria-pressed={scale === 'symlog'} onclick={() => (scale = 'symlog')}>Symmetric log</button>
							<button class="btn" type="button" aria-pressed={scale === 'linear'} onclick={() => (scale = 'linear')}>Linear, clipped</button>
						</div>
					{/snippet}
					<EffectStrip {points} {groups} {scale} bind:beyond onselect={(id) => drawerRow.set({ id })} />
					{#snippet extra()}
						{#if scale === 'linear' && beyond > 0}<strong>{f.int(beyond)} {beyond === 1 ? 'value' : 'values'} beyond axis, drawn as ▶ at the edge.</strong>{/if}
					{/snippet}
				</ChartFrame>
			{:else}
				<div class="gap"><StateBlock kind="empty" message="None of the rows under this concept reports a numeric change, so there is nothing to plot. Open an interferent below to read the evidence." /></div>
			{/if}

		{/if}

		<h2>By analyte</h2>
		<ul class="list">
			{#each perAnalyte as p (p.analyte.analyte_id)}
				<li id={p.analyte.analyte_id} class="card">
					<h3><a href="{base}/analyte/{p.analyte.analyte_id}/?concept={concept.concept}">{p.analyte.component}</a></h3>
					<p class="caption">
						{f.int(p.interferents.reduce((n, i) => n + i.evidence_rows, 0))} rows{#if status === 'ready'} · {p.s.plottable ? `${f.int(p.s.exceeds)} of ${f.int(p.s.plottable)} numeric results exceed the ${f.aps(p.analyte.aps_percent)} APS` : 'no numeric results'}{/if}
					</p>
					<ul>
						{#each p.interferents as i (i.interferent_id)}
							<li><a href="{base}/interferent/{i.interferent_id}/">{i.interferent_canonical}</a> <span class="muted">{f.int(i.evidence_rows)}</span></li>
						{/each}
					</ul>
				</li>
			{/each}
		</ul>
	</div>
{:else}
	<NotFound what="concept" />
{/if}

<style>
	.head {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: 12px;
	}
	h1 {
		margin-bottom: 16px;
	}
	.body {
		padding-top: 28px;
		padding-bottom: var(--section);
	}
	.scale {
		display: flex;
		gap: 8px;
		margin-bottom: 12px;
	}
	.gap {
		margin-bottom: 48px;
	}
	h2 {
		margin-bottom: 24px;
	}
	.list {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 16px;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.list > li {
		scroll-margin-top: 80px;
	}
	.list h3 {
		margin-bottom: 4px;
	}
	.card ul {
		margin: 12px 0 0;
		padding-left: 1.1em;
		font-size: 0.9375rem;
	}
	.card ul li {
		margin-bottom: 4px;
	}
</style>
