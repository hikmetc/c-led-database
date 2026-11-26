<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { base } from '$app/paths';
	import { replaceState } from '$app/navigation';
	import { getSite } from '$lib/context';
	import type { AnalyteView } from '$lib/site';
	import type { Interferent, SlimRow } from '$lib/types';
	import { analyteFacets, analyteRows, exportRows, warmAnalyte, type FacetOption } from '$lib/data/queries';
	import { decodeState, defaultState, encodeState, activeFilterCount, emptyFilters, FILTER_KEYS, type FilterKey, type ViewState } from '$lib/urlstate';
	import { judge, sliderMax, summarize, clampAps } from '$lib/aps';
	import { quantile } from '$lib/scales';
	import { drawerRow } from '$lib/stores';
	import * as f from '$lib/format';
	import ApsControl from './ApsControl.svelte';
	import FilterMenu from './FilterMenu.svelte';
	import ChartFrame from './ChartFrame.svelte';
	import RankedBars, { type Ranked } from './RankedBars.svelte';
	import DirectionBars, { type DirectionRow } from './DirectionBars.svelte';
	import EffectStrip, { type StripPoint } from './EffectStrip.svelte';
	import EvidenceTable from './EvidenceTable.svelte';
	import StateBlock from './StateBlock.svelte';

	let { analyte, interferent }: { analyte: AnalyteView; interferent?: Interferent } = $props();
	const site = getSite();
	const fixed = $derived(interferent ? { interferent_id: interferent.interferent_id } : ({} as Record<string, string>));
	const facetKeys = $derived(FILTER_KEYS.filter((k) => !(interferent && (k === 'interferent' || k === 'concept'))));
	const FACET_LABELS: Record<FilterKey, string> = {
		interferent: 'Interferent', concept: 'Concept', platform: 'Platform', analyzer: 'Analyzer',
		sample: 'Sample type', direction: 'Direction', ref: 'Reference'
	};

	let view = $state<ViewState>(defaultState());
	let hydrated = $state(false);
	let rows = $state<SlimRow[]>([]);
	let facets = $state<Record<string, FacetOption[]>>({});
	let status = $state<'loading' | 'ready' | 'error'>('loading');
	let error = $state('');
	let attempt = $state(0);
	let numeric = $state<'all' | 'with' | 'without'>('all');
	let beyond = $state(0);
	let apsCeiling = $state(0);
	let downloading = $state(false);
	let tableEl = $state<HTMLElement | undefined>();
	let filtersEl = $state<HTMLDetailsElement | undefined>();

	onMount(() => {
		// data and chart library start downloading at once, in parallel
		if (site.data.manifest) warmAnalyte(site.data.manifest, analyte.analyte_id);
		void import('@observablehq/plot');
		view = decodeState(new URL(location.href).searchParams);
		if (view.aps !== null) view.aps = clampAps(view.aps);
		hydrated = true;
		if (window.matchMedia('(max-width: 760px)').matches && filtersEl) filtersEl.open = false;
	});

	// keep the URL in step with the view, so any view can be shared
	$effect(() => {
		if (!hydrated) return;
		const qs = encodeState(view, new URL(location.href).searchParams).toString();
		const url = location.pathname + (qs ? `?${qs}` : '') + location.hash;
		if (url === location.pathname + location.search + location.hash) return;
		try {
			replaceState(url, {});
		} catch {
			history.replaceState(history.state, '', url);
		}
	});

	const aps = $derived(view.aps ?? analyte.aps_percent);
	// The numbers follow the slider at once; the strip chart (thousands of marks) is redrawn
	// only when the slider rests, so dragging stays smooth.
	let chartAps = $state(NaN);
	$effect(() => {
		const target = aps;
		if (!Number.isFinite(untrack(() => chartAps))) {
			chartAps = target;
			return;
		}
		const t = setTimeout(() => (chartAps = target), 120);
		return () => clearTimeout(t);
	});
	const filterKey = $derived(JSON.stringify(view.filters));

	$effect(() => {
		const manifest = site.data.manifest;
		if (!hydrated || !manifest) return;
		void attempt;
		const filters = JSON.parse(filterKey);
		let cancelled = false;
		if (!untrack(() => rows.length)) status = 'loading';
		analyteRows(manifest, analyte.analyte_id, filters, fixed)
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
	$effect(() => {
		const manifest = site.data.manifest;
		if (!hydrated || !manifest) return;
		void attempt;
		analyteFacets(manifest, analyte.analyte_id, fixed).then((x) => (facets = x)).catch(() => {});
	});

	function labelOf(key: FilterKey, value: string): string {
		if (key === 'interferent') return site.index?.interferentById.get(value)?.interferent_canonical ?? value;
		if (key === 'concept') return f.humanize(value);
		if (key === 'direction') return f.directionLabel(value);
		if (key === 'ref') return f.refStatusLabel(value);
		return f.isNotReported(value) ? f.NOT_REPORTED : value;
	}
	function setFilter(key: FilterKey, values: string[]) {
		view.filters[key] = values;
	}

	const summary = $derived(summarize(rows, aps));
	const plottable = $derived(rows.filter((r) => r.pct_change !== null));
	$effect(() => {
		const abs = plottable.map((r) => Math.abs(r.pct_change!));
		apsCeiling = Math.max(untrack(() => apsCeiling), sliderMax(analyte.aps_percent, abs));
	});

	interface Group {
		key: string;
		label: string;
		rows: SlimRow[];
	}
	const groups = $derived.by(() => {
		const m = new Map<string, Group>();
		for (const r of rows) {
			let g = m.get(r.interferent_id);
			if (!g) m.set(r.interferent_id, (g = { key: r.interferent_id, label: r.interferent_canonical, rows: [] }));
			g.rows.push(r);
		}
		return [...m.values()];
	});
	const ranked: Ranked[] = $derived(
		groups
			.map((g) => {
				const s = summarize(g.rows, aps);
				return { key: g.key, label: g.label, href: interferent ? undefined : `${base}/interferent/${g.key}/`, rows: s.rows, plottable: s.plottable, exceeds: s.exceeds, share: s.share };
			})
			.sort((a, b) => (b.share ?? -1) - (a.share ?? -1) || b.plottable - a.plottable || a.label.localeCompare(b.label))
	);
	const rankedWithValues = $derived(ranked.filter((r) => r.share !== null));
	const majority = $derived(rankedWithValues.filter((r) => (r.share ?? 0) >= 0.5).length);

	const stripGroups = $derived.by(() => {
		const a = Number.isFinite(chartAps) ? chartAps : aps;
		return groups
			.map((g) => ({ g, s: summarize(g.rows, a) }))
			.filter((x) => x.s.plottable > 0)
			.sort((x, y) => (y.s.share ?? 0) - (x.s.share ?? 0) || y.s.plottable - x.s.plottable || x.g.label.localeCompare(y.g.label))
			.map(({ g, s }) => ({ key: g.key, label: `${g.label}  ·  ${s.exceeds}/${s.plottable}`, aps: a }));
	});
	const cut = (s: string | null, n = 70) => (f.isNotReported(s) ? f.NOT_REPORTED : s!.length > n ? s!.slice(0, n - 1) + '…' : s!);
	const stripPoints: StripPoint[] = $derived(
		plottable.map((r) => ({
			id: r.row_id,
			group: r.interferent_id,
			pct: r.pct_change!,
			tip: `${f.pct(r.pct_change)} · ${f.directionLabel(r.direction)}\nAnalyzer: ${cut(r.analyzer)}\nPlatform: ${cut(r.platform)}\n${r.doi ? `DOI ${r.doi}` : r.pmid ? `PMID ${r.pmid}` : 'Full reference only'}`
		}))
	);
	const stripTable = $derived(
		rankedWithValues.map((r) => {
			const v = groups.find((g) => g.key === r.key)!.rows.filter((x) => x.pct_change !== null).map((x) => x.pct_change!).sort((a, b) => a - b);
			return [r.label, r.plottable, r.exceeds, f.share(r.share), f.pct(v[0]), f.pct(quantile(v, 0.5)), f.pct(v[v.length - 1])];
		})
	);

	const KNOWN_DIRECTIONS = ['up', 'down', 'none', 'not_reported'];
	const directionOrder = $derived.by(() => {
		const seen = new Set(rows.map((r) => r.direction ?? 'not_reported'));
		return [...KNOWN_DIRECTIONS.filter((d) => seen.has(d)), ...[...seen].filter((d) => !KNOWN_DIRECTIONS.includes(d)).sort()];
	});
	const directionRows: DirectionRow[] = $derived(
		[...groups]
			.sort((a, b) => b.rows.length - a.rows.length)
			.map((g) => {
				const counts: Record<string, number> = {};
				for (const r of g.rows) counts[r.direction ?? 'not_reported'] = (counts[r.direction ?? 'not_reported'] ?? 0) + 1;
				return { key: g.key, label: g.label, total: g.rows.length, counts };
			})
	);
	const topDirection = $derived.by(() => {
		const totals: Record<string, number> = {};
		for (const r of rows) totals[r.direction ?? 'not_reported'] = (totals[r.direction ?? 'not_reported'] ?? 0) + 1;
		return Object.entries(totals).sort((a, b) => b[1] - a[1])[0] ?? null;
	});

	const tableRows = $derived(numeric === 'all' ? rows : rows.filter((r) => (r.pct_change !== null) === (numeric === 'with')));
	const apsText = $derived(`${f.aps(aps)} APS${view.aps === null ? ' (default)' : ' (custom)'}`);
	const live = $derived(
		status !== 'ready' ? '' : `${f.int(rows.length)} evidence ${rows.length === 1 ? 'row' : 'rows'}. ${f.int(summary.exceeds)} of ${f.int(summary.plottable)} numeric results exceed the ${apsText}.`
	);
	const chartCaption = $derived(
		`n = ${f.int(summary.plottable)} results with a numeric change, judged against the ${apsText}. ${f.int(summary.notPlottable)} ${summary.notPlottable === 1 ? 'row has' : 'rows have'} no numeric value and ${summary.notPlottable === 1 ? 'is' : 'are'} not drawn.`
	);

	function listNotPlottable() {
		numeric = 'without';
		tableEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}
	async function download() {
		const manifest = site.data.manifest;
		if (!manifest || downloading) return;
		downloading = true;
		try {
			let out = await exportRows(manifest, analyte.analyte_id, view.filters, fixed, aps);
			if (numeric !== 'all') out = out.filter((r) => (r.pct_change !== null) === (numeric === 'with'));
			const cols = out.length ? Object.keys(out[0]) : [];
			const blob = new Blob([f.toCsv(cols, out)], { type: 'text/csv;charset=utf-8' });
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = `cled_${interferent?.interferent_id ?? analyte.analyte_id}_${out.length}_rows.csv`;
			document.body.append(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(a.href), 1000);
		} catch (e: any) {
			error = e?.message ?? String(e);
		} finally {
			downloading = false;
		}
	}
</script>

<div class="toolbar">
	<div class="wrap bar">
		<ApsControl value={aps} defaultAps={analyte.aps_percent} max={apsCeiling || 20} onchange={(v) => (view.aps = v)} />
		<details class="filters" open bind:this={filtersEl}>
			<summary class="btn">Filters{#if activeFilterCount(view.filters)}<span class="n">{activeFilterCount(view.filters)}</span>{/if}</summary>
			<div class="menus">
				{#each facetKeys as key (key)}
					<FilterMenu
						label={FACET_LABELS[key]}
						options={(facets[key] ?? []).map((o) => ({ value: o.value, label: labelOf(key, o.value), n: o.n }))}
						selected={view.filters[key]}
						onchange={(v) => setFilter(key, v)}
					/>
				{/each}
			</div>
		</details>
	</div>
</div>

<div class="wrap body">
	<p class="live" aria-live="polite" role="status" data-testid="result-summary">{live}</p>
	{#if activeFilterCount(view.filters)}
		<ul class="chips" aria-label="Active filters">
			{#each facetKeys as key (key)}
				{#each view.filters[key] as v (v)}
					<li><button type="button" onclick={() => setFilter(key, view.filters[key].filter((x) => x !== v))} aria-label="Remove filter {FACET_LABELS[key]}: {labelOf(key, v)}"><span class="k">{FACET_LABELS[key]}</span> <span class="v">{labelOf(key, v)}</span> <span aria-hidden="true">×</span></button></li>
				{/each}
			{/each}
			<li><button type="button" class="clear" onclick={() => (view.filters = emptyFilters())}>Clear all</button></li>
		</ul>
	{/if}

	{#if !site.data.manifest}
		<StateBlock kind="error" message="The data manifest could not be read." />
	{:else if status === 'error'}
		<StateBlock kind="error" message={error} onretry={() => (attempt += 1)} />
	{:else if status === 'loading'}
		<StateBlock kind="loading" message="Loading evidence" height={360} />
	{:else if rows.length === 0}
		<StateBlock kind="empty" message="No evidence row matches these filters. Remove a filter to see more." />
	{:else}
		{#if !interferent}
			<ChartFrame
				title="{majority} of {rankedWithValues.length} interferents exceed the {f.aps(aps)} APS in at least half of their numeric results"
				caption={chartCaption}
				columns={['Interferent', 'Rows', 'Numeric results', 'Exceed APS', 'Share']}
				rows={ranked.map((r) => [r.label, r.rows, r.plottable, r.exceeds, f.share(r.share)])}
			>
				<RankedBars items={ranked} />
			</ChartFrame>
		{/if}

		{#if summary.plottable > 0}
			<ChartFrame
				image
				title="{f.int(summary.exceeds)} of {f.int(summary.plottable)} {interferent ? '' : ''}numeric results exceed the {f.aps(aps)} APS"
				alt="Strip chart of percent change per interferent. {f.int(summary.exceeds)} of {f.int(summary.plottable)} numeric results lie outside the band of plus or minus {f.aps(aps)}. Use View as table for the numbers."
				caption="{chartCaption} Each mark is one evidence row; the shaded band is ±{f.aps(aps)}. ◆ outside the band, ○ inside."
				columns={['Interferent', 'Numeric results', 'Exceed APS', 'Share', 'Minimum', 'Median', 'Maximum']}
				rows={stripTable}
			>
				{#snippet controls()}
					<div class="scale" role="group" aria-label="Axis scale">
						<button class="btn" type="button" aria-pressed={view.scale === 'symlog'} onclick={() => (view.scale = 'symlog')}>Symmetric log</button>
						<button class="btn" type="button" aria-pressed={view.scale === 'linear'} onclick={() => (view.scale = 'linear')}>Linear, clipped</button>
					</div>
				{/snippet}
				<EffectStrip points={stripPoints} groups={stripGroups} scale={view.scale} bind:beyond onselect={(id) => drawerRow.set({ id, aps })} />
				{#snippet extra()}
					{#if view.scale === 'linear' && beyond > 0}<strong data-testid="beyond-note">{f.int(beyond)} {beyond === 1 ? 'value' : 'values'} beyond axis, drawn as ▶ at the edge.</strong>{/if}
					{#if summary.notPlottable > 0}<button type="button" class="linkbtn" onclick={listNotPlottable}>List the {f.int(summary.notPlottable)} rows without a numeric value</button>{/if}
				{/snippet}
			</ChartFrame>
		{:else}
			<div class="chartless">
				<StateBlock kind="empty" message="None of the {f.int(rows.length)} rows in this selection reports a numeric change, so there is nothing to plot. They are listed in the table below." />
			</div>
		{/if}

		<ChartFrame
			title={topDirection ? `${f.directionLabel(topDirection[0])} is the most common reported direction (${f.int(topDirection[1])} of ${f.int(rows.length)} rows)` : 'Reported direction of effect'}
			caption="n = {f.int(rows.length)} rows, all rows of the selection (direction does not depend on the APS)."
			columns={['Interferent', ...directionOrder.map((d) => f.directionLabel(d)), 'Rows']}
			rows={directionRows.map((r) => [r.label, ...directionOrder.map((d) => r.counts[d] ?? 0), r.total])}
		>
			<DirectionBars items={directionRows} order={directionOrder} />
		</ChartFrame>

		<section bind:this={tableEl} class="evidence" aria-labelledby="evidence-h">
			<div class="ehead">
				<h2 class="h3" id="evidence-h">Evidence rows <span class="muted">{f.int(tableRows.length)}</span></h2>
				<div class="eactions">
					<div class="seg" role="group" aria-label="Rows to list">
						<button class="btn" type="button" aria-pressed={numeric === 'all'} onclick={() => (numeric = 'all')}>All</button>
						<button class="btn" type="button" aria-pressed={numeric === 'with'} onclick={() => (numeric = 'with')}>Numeric</button>
						<button class="btn" type="button" aria-pressed={numeric === 'without'} onclick={() => (numeric = 'without')} data-testid="only-not-plottable">Not plottable</button>
					</div>
					<button class="btn" type="button" onclick={download} disabled={downloading} data-testid="download-csv">{downloading ? 'Preparing…' : 'Download CSV'}</button>
				</div>
			</div>
			{#if tableRows.length}
				<EvidenceTable rows={tableRows} {aps} showInterferent={!interferent} />
			{:else}
				<StateBlock kind="empty" message="No row of this kind in the selection." />
			{/if}
		</section>
	{/if}
</div>

<style>
	.toolbar {
		position: sticky;
		top: 53px;
		z-index: 20;
		background: var(--nav-bg);
		-webkit-backdrop-filter: saturate(180%) blur(20px);
		backdrop-filter: saturate(180%) blur(20px);
		border-bottom: 1px solid var(--hairline);
		padding: 10px 0;
	}
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		gap: 10px 28px;
	}
	.filters > summary {
		display: none;
		list-style: none;
	}
	.filters > summary::-webkit-details-marker {
		display: none;
	}
	.filters .n {
		font-weight: 600;
	}
	.menus {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	@media (max-width: 760px) {
		.filters > summary {
			display: inline-flex;
		}
		.filters[open] > summary {
			margin-bottom: 10px;
		}
		.filters {
			width: 100%;
		}
	}
	.body {
		padding-top: 28px;
		padding-bottom: var(--section);
	}
	.live {
		color: var(--text-2);
		font-size: 0.9375rem;
		min-height: 1.5em;
		margin-bottom: 16px;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		list-style: none;
		margin: 0 0 28px;
		padding: 0;
	}
	.chips button {
		display: inline-flex;
		gap: 6px;
		align-items: baseline;
		max-width: min(520px, 86vw);
		padding: 5px 12px;
		border: 0;
		border-radius: 980px;
		background: var(--bg-2);
		font-size: 0.8125rem;
		cursor: pointer;
	}
	.chips .k {
		color: var(--text-2);
		flex: none;
	}
	.chips .v {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chips .clear {
		background: none;
		color: var(--link);
	}
	.scale {
		display: flex;
		gap: 8px;
		margin-bottom: 12px;
	}
	.linkbtn {
		border: 0;
		background: none;
		padding: 0;
		color: var(--link);
		font-size: inherit;
		cursor: pointer;
		text-decoration: underline;
	}
	.chartless {
		margin-bottom: 56px;
	}
	.ehead {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
		margin-bottom: 16px;
	}
	.ehead h2 .muted {
		font-weight: 400;
	}
	.eactions,
	.seg {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.evidence {
		scroll-margin-top: 140px;
	}
</style>
