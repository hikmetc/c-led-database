<script lang="ts">
	import { APS_MAX, APS_MIN, APS_STEP, clampAps } from '$lib/aps';
	import * as f from '$lib/format';

	let { value, defaultAps, max, onchange }: { value: number; defaultAps: number; max: number; onchange: (v: number | null) => void } = $props();
	const uid = $props.id();
	const isDefault = $derived(value === defaultAps);

	function set(raw: string) {
		const n = Number(raw);
		if (!Number.isFinite(n) || n <= 0) return;
		const v = clampAps(n);
		onchange(v === defaultAps ? null : v);
	}
</script>

<div class="aps" data-testid="aps-control">
	<label for="{uid}-n" class="name">APS</label>
	<input
		id="{uid}-r"
		type="range"
		min={APS_MIN}
		max={Math.max(max, value)}
		step={APS_STEP}
		{value}
		oninput={(e) => set(e.currentTarget.value)}
		aria-label="Analytical performance specification, percent (slider)"
	/>
	<span class="field">
		<input id="{uid}-n" type="number" min={APS_MIN} max={APS_MAX} step={APS_STEP} {value} onchange={(e) => set(e.currentTarget.value)} inputmode="decimal" data-testid="aps-input" />
		<span aria-hidden="true">%</span>
	</span>
	<span class="state caption" data-testid="aps-state">
		{#if isDefault}
			Default APS
		{:else}
			Custom (default {f.aps(defaultAps)})
			<button type="button" class="reset" onclick={() => onchange(null)}>Reset</button>
		{/if}
	</span>
</div>

<style>
	.aps {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 8px 12px;
	}
	.name {
		font-weight: 600;
		font-size: 0.875rem;
	}
	input[type='range'] {
		width: clamp(110px, 22vw, 220px);
		accent-color: var(--accent);
	}
	.field {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 0.875rem;
	}
	input[type='number'] {
		width: 76px;
		height: 34px;
		padding: 0 8px;
		border: 1px solid var(--control);
		border-radius: 9px;
		background: var(--bg);
		font-size: 0.9375rem;
	}
	.reset {
		border: 0;
		background: none;
		color: var(--link);
		cursor: pointer;
		padding: 2px 4px;
		font-size: inherit;
	}
	.reset:hover {
		text-decoration: underline;
	}
</style>
