<script lang="ts">
	import * as f from '$lib/format';

	export interface Ranked {
		key: string;
		label: string;
		href?: string;
		rows: number;
		plottable: number;
		exceeds: number;
		share: number | null;
	}
	let { items }: { items: Ranked[] } = $props();
</script>

<ol class="bars">
	{#each items as it (it.key)}
		<li>
			<div class="label">
				{#if it.href}<a href={it.href}>{it.label}</a>{:else}<span>{it.label}</span>{/if}
				<span class="val">
					{#if it.share === null}
						<span class="muted">no numeric values · {f.int(it.rows)} {it.rows === 1 ? 'row' : 'rows'}</span>
					{:else}
						<strong>{f.share(it.share)}</strong> <span class="muted">{f.int(it.exceeds)} of {f.int(it.plottable)}</span>
					{/if}
				</span>
			</div>
			<div class="track" aria-hidden="true">{#if it.share !== null}<div class="fill" style="width:{Math.max(it.share * 100, it.exceeds ? 0.6 : 0)}%"></div>{/if}</div>
		</li>
	{/each}
</ol>

<style>
	.bars {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 14px;
	}
	.label {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 16px;
		font-size: 0.9375rem;
		margin-bottom: 5px;
	}
	.label a {
		color: var(--text);
	}
	.val {
		flex: none;
		font-size: 0.8125rem;
	}
	.track {
		height: 8px;
		border-radius: 4px;
		background: var(--bg-2);
		box-shadow: inset 0 0 0 1px var(--hairline);
		overflow: hidden;
	}
	.fill {
		height: 100%;
		background: var(--exceeds);
		border-radius: 4px;
		transition: width var(--dur) var(--ease);
	}
</style>
