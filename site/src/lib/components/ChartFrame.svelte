<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, caption, alt = '', image = false, columns, rows, children, extra, controls }: {
		title: string;
		caption: string;
		/** text alternative, used when the chart is a picture (SVG) */
		alt?: string;
		image?: boolean;
		columns: string[];
		rows: (string | number)[][];
		children: Snippet;
		extra?: Snippet;
		/** buttons that belong to the chart but are not part of the picture */
		controls?: Snippet;
	} = $props();
	let asTable = $state(false);
</script>

<figure class="chart">
	<div class="head">
		<h2 class="h3">{title}</h2>
		<button class="btn" type="button" aria-pressed={asTable} onclick={() => (asTable = !asTable)}>View as table</button>
	</div>
	{#if asTable}
		<div class="table-scroll fade-in">
			<table class="plain-table">
				<thead><tr>{#each columns as c, i (c)}<th scope="col" class:num={i > 0}>{c}</th>{/each}</tr></thead>
				<tbody>
					{#each rows as r, ri (ri)}
						<tr>{#each r as v, i (i)}{#if i === 0}<th scope="row">{v}</th>{:else}<td class="num">{v}</td>{/if}{/each}</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else if image}
		{@render controls?.()}
		<div role="img" aria-label={alt || title}>{@render children()}</div>
	{:else}
		{@render children()}
	{/if}
	<figcaption class="caption">{caption} {@render extra?.()}</figcaption>
</figure>

<style>
	.chart {
		margin: 0 0 56px;
	}
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
		margin-bottom: 16px;
	}
	h2 {
		max-width: 40rem;
	}
	.btn {
		flex: none;
	}
	figcaption {
		margin-top: 12px;
		max-width: 52rem;
	}
	.plain-table th[scope='row'] {
		color: var(--text);
		font-weight: 400;
		white-space: normal;
	}
</style>
