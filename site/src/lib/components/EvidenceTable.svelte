<script lang="ts">
	import { onMount } from 'svelte';
	import type { SlimRow } from '$lib/types';
	import { judge } from '$lib/aps';
	import { drawerRow } from '$lib/stores';
	import * as f from '$lib/format';

	let { rows, aps, showInterferent = true }: { rows: SlimRow[]; aps: number; showInterferent?: boolean } = $props();

	interface Column {
		key: string;
		label: string;
		track: string;
		on: boolean;
		num?: boolean;
		sort: (r: SlimRow) => string | number | null;
	}
	const text = (v: string | null) => (f.isNotReported(v) ? null : v!.toLowerCase());
	let columns = $state<Column[]>([
		{ key: 'row_id', label: 'Row', track: '170px', on: true, sort: (r) => r.row_id },
		{ key: 'interferent', label: 'Interferent', track: 'minmax(190px, 1.3fr)', on: true, sort: (r) => r.interferent_canonical.toLowerCase() },
		{ key: 'platform', label: 'Platform / method', track: 'minmax(190px, 1.4fr)', on: true, sort: (r) => text(r.platform) },
		{ key: 'analyzer', label: 'Analyzer', track: 'minmax(150px, 1fr)', on: true, sort: (r) => text(r.analyzer) },
		{ key: 'sample_type', label: 'Sample type', track: 'minmax(170px, 1.2fr)', on: false, sort: (r) => text(r.sample_type) },
		{ key: 'pct_change', label: 'Change', track: '104px', on: true, num: true, sort: (r) => r.pct_change },
		{ key: 'direction', label: 'Direction', track: '108px', on: true, sort: (r) => r.direction },
		{ key: 'verdict', label: 'APS verdict', track: '132px', on: true, sort: (r) => judge(r.pct_change, aps) },
		{ key: 'reference', label: 'Reference', track: '150px', on: true, sort: (r) => r.doi ?? r.pmid ?? null }
	]);
	const visible = $derived(columns.filter((c) => c.on && (showInterferent || c.key !== 'interferent')));
	const template = $derived(visible.map((c) => c.track).join(' '));
	const minWidth = $derived(visible.reduce((w, c) => w + (parseInt(c.track.replace(/\D+/, ' ').trim()) || 150), 0) + 48);

	let sortKey = $state<string | null>(null);
	let sortDir = $state<1 | -1>(1);
	const sorted = $derived.by(() => {
		const col = columns.find((c) => c.key === sortKey);
		if (!col) return rows;
		const keyed = rows.map((r) => ({ r, k: col.sort(r) }));
		keyed.sort((a, b) => {
			if (a.k === null && b.k === null) return 0;
			if (a.k === null) return 1; // missing values always sort last
			if (b.k === null) return -1;
			return (a.k < b.k ? -1 : a.k > b.k ? 1 : 0) * sortDir;
		});
		return keyed.map((x) => x.r);
	});
	function sortBy(key: string) {
		if (sortKey === key) {
			if (sortDir === 1) sortDir = -1;
			else sortKey = null;
		} else {
			sortKey = key;
			sortDir = 1;
		}
		if (scroller) scroller.scrollTop = 0;
	}

	// virtualisation: fixed row height, only the rows in view are in the DOM
	let cards = $state(false);
	let scroller = $state<HTMLDivElement | undefined>();
	let scrollTop = $state(0);
	let viewH = $state(600);
	const rowH = $derived(cards ? 144 : 48);
	const start = $derived(Math.max(0, Math.floor(scrollTop / rowH) - 6));
	const end = $derived(Math.min(sorted.length, Math.ceil((scrollTop + viewH) / rowH) + 6));
	const slice = $derived(sorted.slice(start, end));
	onMount(() => {
		const mq = window.matchMedia('(max-width: 760px)');
		const apply = () => (cards = mq.matches);
		apply();
		mq.addEventListener('change', apply);
		return () => mq.removeEventListener('change', apply);
	});
	$effect(() => {
		void rows;
		if (scroller) scroller.scrollTop = 0;
	});

	let chooser = $state<HTMLDetailsElement | undefined>();
	function open(r: SlimRow) {
		drawerRow.set({ id: r.row_id, aps });
	}
	const shortId = (id: string) => {
		const parts = id.split('.');
		return parts.length >= 3 ? `${parts[0]}…${parts[parts.length - 1]}` : id;
	};
</script>

<div class="bar">
	<details bind:this={chooser} class="chooser">
		<summary class="btn">Columns</summary>
		<fieldset class="pop">
			<legend class="visually-hidden">Columns to show</legend>
			{#each columns as c (c.key)}
				{#if showInterferent || c.key !== 'interferent'}
					<label><input type="checkbox" bind:checked={c.on} disabled={c.key === 'row_id'} /> {c.label}</label>
				{/if}
			{/each}
		</fieldset>
	</details>
	{#if cards}
		<label class="sortsel caption">Sort by
			<select onchange={(e) => { sortKey = e.currentTarget.value || null; sortDir = 1; }}>
				<option value="">Source order</option>
				{#each visible as c (c.key)}<option value={c.key} selected={sortKey === c.key}>{c.label}</option>{/each}
			</select>
		</label>
	{/if}
</div>

<div class="frame">
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="scroller"
		class:cards
		bind:this={scroller}
		bind:clientHeight={viewH}
		onscroll={(e) => (scrollTop = e.currentTarget.scrollTop)}
		tabindex="0"
		role="group"
		aria-label="Evidence rows, scrollable"
		style="--tpl:{template}; --minw:{minWidth}px; max-height:{Math.min(sorted.length * rowH + 50, 640)}px"
	>
		<div role="table" aria-label="Evidence rows" aria-rowcount={sorted.length + 1} data-testid="evidence-table">
			<div role="rowgroup" class="thead" class:visually-hidden={cards}>
				<div role="row" class="tr head" aria-rowindex="1">
					{#each visible as c (c.key)}
						<div role="columnheader" class:num={c.num} aria-sort={sortKey === c.key ? (sortDir === 1 ? 'ascending' : 'descending') : 'none'}>
							<button type="button" onclick={() => sortBy(c.key)}>{c.label}<span aria-hidden="true">{sortKey === c.key ? (sortDir === 1 ? ' ↑' : ' ↓') : ''}</span></button>
						</div>
					{/each}
				</div>
			</div>
			<div role="rowgroup" class="tbody" style="height:{sorted.length * rowH}px">
				{#each slice as r, i (r.row_id)}
					{@const v = judge(r.pct_change, aps)}
					<!-- svelte-ignore a11y_click_events_have_key_events, a11y_interactive_supports_focus -->
					<div role="row" class="tr" aria-rowindex={start + i + 2} style="transform:translateY({(start + i) * rowH}px); height:{rowH}px" onclick={() => open(r)}>
						{#each visible as c (c.key)}
							<div role="cell" class="c-{c.key}" class:num={c.num}>
								{#if c.key === 'row_id'}
									<button type="button" class="mono idbtn" title={r.row_id} onclick={(e) => { e.stopPropagation(); open(r); }} ><span class="visually-hidden">Open evidence row </span>{shortId(r.row_id)}</button>
								{:else if c.key === 'interferent'}
									<span class="clip" title={r.interferent_verbatim ?? r.interferent_canonical}>{r.interferent_canonical}</span>
								{:else if c.key === 'platform'}
									<span class="clip" class:muted={f.isNotReported(r.platform)} title={r.platform}>{f.isNotReported(r.platform) ? f.NOT_REPORTED : r.platform}</span>
								{:else if c.key === 'analyzer'}
									<span class="clip" class:muted={f.isNotReported(r.analyzer)} title={r.analyzer}>{f.isNotReported(r.analyzer) ? f.NOT_REPORTED : r.analyzer}</span>
								{:else if c.key === 'sample_type'}
									<span class="clip" class:muted={f.isNotReported(r.sample_type)} title={r.sample_type}>{f.isNotReported(r.sample_type) ? f.NOT_REPORTED : r.sample_type}</span>
								{:else if c.key === 'pct_change'}
									<span class:muted={r.pct_change === null}>{f.pct(r.pct_change)}</span>
								{:else if c.key === 'direction'}
									<span class:muted={f.isNotReported(r.direction)}>{f.directionLabel(r.direction)}</span>
								{:else if c.key === 'verdict'}
									{#if v === 'exceeds'}<span class="tag exceeds">◆ Exceeds</span>
									{:else if v === 'within'}<span class="tag">○ Within</span>
									{:else}<span class="tag nc" title="No numeric change is reported, so this row cannot be judged against a custom APS. Recorded verdict: {f.verdictLabel(r.aps_verdict)}">Not computable</span>{/if}
								{:else if c.key === 'reference'}
									{#if r.doi}<a href={f.doiUrl(r.doi)} rel="noopener" class="clip" onclick={(e) => e.stopPropagation()} title={r.doi}>DOI</a>{/if}
									{#if r.pmid}<a href={f.pmidUrl(r.pmid)} rel="noopener" onclick={(e) => e.stopPropagation()}>PMID</a>{/if}
									{#if !r.doi && !r.pmid}<span class="muted">Full reference</span>{/if}
								{/if}
							</div>
						{/each}
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>

<style>
	.bar {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 12px;
	}
	.chooser {
		position: relative;
	}
	.chooser summary {
		list-style: none;
	}
	.chooser summary::-webkit-details-marker {
		display: none;
	}
	.pop {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 30;
		display: grid;
		gap: 6px;
		min-width: 220px;
		margin: 0;
		padding: 12px;
		background: var(--bg);
		border: 1px solid var(--hairline);
		border-radius: 14px;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14);
		font-size: 0.875rem;
	}
	.pop input {
		accent-color: var(--accent);
	}
	select {
		height: 34px;
		border: 1px solid var(--control);
		border-radius: 9px;
		background: var(--bg);
		padding: 0 8px;
		font-size: 0.875rem;
	}
	.frame {
		border: 1px solid var(--hairline);
		border-radius: 14px;
		overflow: hidden;
	}
	.scroller {
		overflow: auto;
		min-height: 120px;
	}
	[role='table'] {
		min-width: var(--minw);
		font-size: 0.875rem;
	}
	.cards [role='table'] {
		min-width: 0;
	}
	.thead {
		position: sticky;
		top: 0;
		z-index: 2;
		background: var(--bg-2);
		border-bottom: 1px solid var(--hairline);
	}
	.tr {
		display: grid;
		grid-template-columns: var(--tpl);
		align-items: center;
		gap: 0 12px;
		padding: 0 16px;
	}
	.tbody {
		position: relative;
	}
	.tbody .tr {
		position: absolute;
		left: 0;
		right: 0;
		top: 0;
		border-bottom: 1px solid var(--hairline);
		cursor: pointer;
	}
	.tbody .tr:hover {
		background: var(--bg-2);
	}
	.head {
		height: 44px;
	}
	.head button {
		border: 0;
		background: none;
		padding: 4px 0;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-2);
		cursor: pointer;
		white-space: nowrap;
	}
	[role='cell'] {
		min-width: 0;
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.num {
		justify-content: flex-end;
		text-align: right;
	}
	.clip {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.idbtn {
		border: 0;
		background: none;
		padding: 4px 0;
		color: var(--link);
		cursor: pointer;
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	/* mobile: each row becomes a card */
	.cards .tbody .tr {
		grid-template-columns: 1fr auto;
		grid-auto-rows: min-content;
		align-content: center;
		gap: 3px 12px;
		padding: 10px 16px;
	}
	.cards [role='cell'] {
		grid-column: 1 / -1;
	}
	.cards .c-interferent {
		font-weight: 600;
		order: 1;
	}
	.cards .c-platform {
		order: 2;
		color: var(--text-2);
	}
	.cards .c-analyzer,
	.cards .c-sample_type {
		order: 3;
		color: var(--text-2);
		font-size: 0.8125rem;
	}
	.cards .c-pct_change {
		order: 4;
		grid-column: 1;
		justify-content: flex-start;
		font-weight: 600;
	}
	.cards .c-verdict {
		order: 5;
		grid-column: 2;
		grid-row: span 1;
	}
	.cards .c-direction {
		order: 6;
		grid-column: 1;
		font-size: 0.8125rem;
	}
	.cards .c-reference {
		order: 7;
		grid-column: 2;
		font-size: 0.8125rem;
	}
	.cards .c-row_id {
		order: 8;
		font-size: 0.75rem;
	}
</style>
