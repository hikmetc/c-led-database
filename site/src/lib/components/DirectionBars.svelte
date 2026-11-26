<script lang="ts">
	import * as f from '$lib/format';

	export interface DirectionRow {
		key: string;
		label: string;
		total: number;
		counts: Record<string, number>;
	}
	/** `order` lists the direction values found in the data, in display order. */
	let { items, order }: { items: DirectionRow[]; order: string[] } = $props();
	const KNOWN = ['up', 'down', 'none', 'not_reported'];
	const cls = (d: string) => (KNOWN.includes(d) ? d : 'other');
</script>

<ul class="legend" aria-label="Legend">
	{#each order as d (d)}<li><span class="sw {cls(d)}"></span>{f.directionLabel(d)}</li>{/each}
</ul>
<ul class="rows">
	{#each items as it (it.key)}
		<li>
			<div class="label"><span>{it.label}</span><span class="muted n">{f.int(it.total)} {it.total === 1 ? 'row' : 'rows'}</span></div>
			<div class="stack">
				{#each order as d (d)}
					{@const n = it.counts[d] ?? 0}
					{#if n > 0}
						<span class="seg {cls(d)}" style="flex-grow:{n}" title="{f.directionLabel(d)}: {f.int(n)} of {f.int(it.total)}"><span class="visually-hidden">{f.directionLabel(d)} {f.int(n)}; </span></span>
					{/if}
				{/each}
			</div>
		</li>
	{/each}
</ul>

<style>
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 20px;
		font-size: 0.8125rem;
		color: var(--text-2);
		margin-bottom: 16px;
	}
	.legend li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.sw {
		width: 18px;
		height: 12px;
		border-radius: 3px;
	}
	.rows {
		display: grid;
		gap: 12px;
	}
	.label {
		display: flex;
		justify-content: space-between;
		gap: 16px;
		font-size: 0.9375rem;
		margin-bottom: 5px;
	}
	.n {
		flex: none;
		font-size: 0.8125rem;
	}
	.stack {
		display: flex;
		gap: 2px;
		height: 12px;
	}
	.seg {
		flex-basis: 3px;
		min-width: 3px;
		border-radius: 3px;
		transition: flex-grow var(--dur) var(--ease);
	}
	/* Each direction differs by pattern as well as by colour. */
	.up {
		background: var(--up);
	}
	.down {
		background: repeating-linear-gradient(135deg, var(--down) 0 4px, transparent 4px 6px);
		box-shadow: inset 0 0 0 1.5px var(--down);
	}
	.none {
		background: var(--within);
		opacity: 0.55;
	}
	.not_reported {
		background: transparent;
		box-shadow: inset 0 0 0 1.5px var(--control);
	}
	.other {
		background: repeating-linear-gradient(90deg, var(--control) 0 2px, transparent 2px 5px);
	}
</style>
