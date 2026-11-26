<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { getSite } from '$lib/context';
	import { matrixCells, type MatrixCell } from '$lib/data/queries';
	import * as f from '$lib/format';

	const site = getSite();
	const index = $derived(site.index);
	let shares = $state<Map<string, MatrixCell>>(new Map());
	let status = $state<'loading' | 'ready' | 'error'>('loading');
	let attempt = $state(0);
	let table = $state<HTMLTableElement | undefined>();
	let current = $state('0:0');

	onMount(() => {
		void load();
	});
	async function load() {
		if (!site.data.manifest) return;
		status = 'loading';
		try {
			const cells = await matrixCells(site.data.manifest);
			shares = new Map(cells.map((c) => [`${c.concept}|${c.analyte_id}`, c]));
			status = 'ready';
		} catch {
			status = 'error';
		}
	}

	function cell(concept: string, analyteId: string) {
		const list = index?.conceptById.get(concept)?.byAnalyte.get(analyteId);
		if (!list?.length) return null;
		const n = list.reduce((s, i) => s + i.evidence_rows, 0);
		const q = shares.get(`${concept}|${analyteId}`);
		const share = q && q.plottable > 0 ? q.exceeds / q.plottable : null;
		const bin = share === null ? null : Math.min(4, Math.floor(share * 5));
		const href = list.length === 1 ? `${base}/interferent/${list[0].interferent_id}/` : `${base}/concept/${concept}/#${analyteId}`;
		return { n, q, share, bin, href, causes: list.length };
	}
	function describe(conceptLabel: string, analyte: string, c: NonNullable<ReturnType<typeof cell>>) {
		let s = `${conceptLabel} on ${analyte}: ${f.int(c.n)} evidence ${c.n === 1 ? 'row' : 'rows'}`;
		if (c.q) s += c.share === null ? '; no numeric results' : `; ${f.int(c.q.exceeds)} of ${f.int(c.q.plottable)} numeric results exceed the default APS (${f.share(c.share)})`;
		return s;
	}

	// arrow keys move between filled cells; Tab enters and leaves the grid once
	function onKey(e: KeyboardEvent) {
		const el = (e.target as HTMLElement).closest<HTMLElement>('a[data-pos]');
		if (!el || !table) return;
		const [r, c] = el.dataset.pos!.split(':').map(Number);
		const step: Record<string, [number, number]> = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] };
		const d = step[e.key];
		if (!d) return;
		e.preventDefault();
		const rowsN = index?.concepts.length ?? 0;
		const colsN = index?.analytes.length ?? 0;
		let rr = r + d[0];
		let cc = c + d[1];
		while (rr >= 0 && rr < rowsN && cc >= 0 && cc < colsN) {
			const next = table.querySelector<HTMLElement>(`a[data-pos="${rr}:${cc}"]`);
			if (next) {
				current = `${rr}:${cc}`;
				next.focus();
				return;
			}
			rr += d[0];
			cc += d[1];
		}
	}
	const first = $derived.by(() => {
		if (!index) return '0:0';
		for (let r = 0; r < index.concepts.length; r++)
			for (let c = 0; c < index.analytes.length; c++) if (index.concepts[r].byAnalyte.has(index.analytes[c].analyte_id)) return `${r}:${c}`;
		return '0:0';
	});
	$effect(() => {
		current = first;
	});
</script>

{#if index}
	<div class="legend caption" aria-hidden="true">
		<span>Share of numeric results beyond the default APS</span>
		<span class="scale">
			{#each [0, 1, 2, 3, 4] as b (b)}<span class="sw b{b}">{b * 20}–{b * 20 + 20}</span>{/each}
			<span class="sw nb">no numeric results</span>
		</span>
	</div>
	<div class="scroll" tabindex="-1">
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<table bind:this={table} onkeydown={onKey} data-testid="matrix" data-status={status}>
			<caption class="visually-hidden">
				Evidence rows by interference concept (rows) and analyte (columns). Each cell gives the number of evidence rows and the share of numeric results that exceed the analyte's default APS. Use the arrow keys to move between cells.
			</caption>
			<thead>
				<tr>
					<th scope="col" class="corner"><span class="caption">Concept</span></th>
					{#each index.analytes as a (a.analyte_id)}
						<th scope="col" class="col"><a href="{base}/analyte/{a.analyte_id}/" title="{a.component} ({a.system})"><span>{a.component}</span></a></th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each index.concepts as c, r (c.concept)}
					<tr>
						<th scope="row"><a href="{base}/concept/{c.concept}/">{c.label}</a></th>
						{#each index.analytes as a, ci (a.analyte_id)}
							{@const x = cell(c.concept, a.analyte_id)}
							<td>
								{#if x}
									<a
										href={x.href}
										class="cell {x.bin === null ? (x.q ? 'nb' : 'pending') : `b${x.bin}`}"
										data-pos="{r}:{ci}"
										tabindex={current === `${r}:${ci}` ? 0 : -1}
									>
										<span class="visually-hidden">{describe(c.label, a.component, x)}</span>
										<span class="n" aria-hidden="true">{f.int(x.n)}</span>
										<span class="s" aria-hidden="true">{x.share === null ? (x.q ? '–' : '\u00a0') : f.share(x.share).replace(' ', '')}</span>
										<span class="tip" aria-hidden="true">{describe(c.label, a.component, x)}</span>
									</a>
								{:else}
									<span class="empty" aria-hidden="true"></span><span class="visually-hidden">No evidence</span>
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="caption note">
		{#if status === 'error'}
			The shares could not be computed. <button type="button" class="retry" onclick={() => { attempt += 1; void load(); }}>Try again</button>
		{:else}
			Each cell shows the number of evidence rows and, below it, the share of rows with a numeric change that exceed the analyte's default APS. Empty cells have no evidence. Select a cell to open the evidence.
		{/if}
	</p>
{/if}

<style>
	.legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 16px;
		margin-bottom: 16px;
	}
	.scale {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 4px;
	}
	.sw {
		padding: 2px 8px;
		border-radius: 6px;
		font-size: 0.75rem;
	}
	.scroll {
		position: relative; /* keeps visually hidden cell text inside the scroller */
		overflow-x: auto;
	}
	table {
		border-collapse: separate;
		border-spacing: 3px;
		font-size: 0.8125rem;
	}
	th[scope='row'] {
		position: sticky;
		left: 0;
		z-index: 1;
		background: var(--bg-2);
		text-align: left;
		font-weight: 400;
		white-space: nowrap;
		padding: 0 12px 0 0;
		max-width: 44vw;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	th[scope='row'] a {
		color: var(--text);
	}
	.corner {
		position: sticky;
		left: 0;
		background: var(--bg-2);
		text-align: left;
		vertical-align: bottom;
		font-weight: 400;
	}
	.col {
		vertical-align: bottom;
		padding: 0 0 6px;
		font-weight: 600;
	}
	.col a {
		display: inline-block;
		color: var(--text);
		writing-mode: vertical-rl;
		transform: rotate(180deg);
		max-height: 168px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	td {
		padding: 0;
		width: 58px;
		min-width: 58px;
		height: 40px;
	}
	.cell {
		position: relative;
		display: grid;
		place-content: center;
		justify-items: center;
		width: 100%;
		height: 40px;
		border-radius: 8px;
		line-height: 1.1;
		transition: background var(--dur) var(--ease);
	}
	.cell:hover {
		text-decoration: none;
		outline: 2px solid var(--text);
		outline-offset: 1px;
	}
	.n {
		font-weight: 600;
	}
	.s {
		font-size: 0.6875rem;
	}
	.pending,
	.nb {
		background: var(--bg);
		color: var(--text);
		box-shadow: inset 0 0 0 1px var(--hairline);
	}
	.nb {
		box-shadow: inset 0 0 0 1px var(--control);
	}
	.b0 { background: var(--m0); color: var(--m0-t); }
	.b1 { background: var(--m1); color: var(--m1-t); }
	.b2 { background: var(--m2); color: var(--m2-t); }
	.b3 { background: var(--m3); color: var(--m3-t); }
	.b4 { background: var(--m4); color: var(--m4-t); }
	.empty {
		display: block;
		width: 4px;
		height: 4px;
		margin: auto;
		border-radius: 50%;
		background: var(--hairline);
	}
	.tip {
		display: none;
		position: absolute;
		bottom: calc(100% + 8px);
		left: 50%;
		transform: translateX(-50%);
		z-index: 5;
		width: max-content;
		max-width: 260px;
		padding: 8px 12px;
		border-radius: 10px;
		background: var(--text);
		color: var(--bg);
		font-size: 0.75rem;
		font-weight: 400;
		line-height: 1.35;
		text-align: left;
		pointer-events: none;
		white-space: normal;
	}
	.cell:hover .tip,
	.cell:focus-visible .tip {
		display: block;
	}
	tbody tr:nth-child(-n + 2) .tip {
		bottom: auto;
		top: calc(100% + 8px);
	}
	.note {
		margin-top: 16px;
		max-width: 46rem;
	}
	.retry {
		border: 0;
		background: none;
		color: var(--link);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: inherit;
	}
</style>
