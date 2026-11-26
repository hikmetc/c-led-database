<script lang="ts">
	import { onMount } from 'svelte';

	let { value, label, suffix = '' }: { value: number; label: string; suffix?: string } = $props();
	const fmt = new Intl.NumberFormat('en-US');
	// svelte-ignore state_referenced_locally
	let shown = $state(value);
	onMount(() => {
		// one subtle count-up; skipped entirely under reduced motion
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		const from = Math.round(value * 0.85);
		const t0 = performance.now();
		const dur = 700;
		let raf = 0;
		const tick = (t: number) => {
			const p = Math.min(1, (t - t0) / dur);
			shown = Math.round(from + (value - from) * (1 - (1 - p) ** 3));
			if (p < 1) raf = requestAnimationFrame(tick);
		};
		raf = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(raf);
	});
</script>

<div class="kpi">
	<dd><span aria-hidden="true">{fmt.format(shown)}{suffix}</span><span class="visually-hidden">{fmt.format(value)}{suffix}</span></dd>
	<dt>{label}</dt>
</div>

<style>
	.kpi {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	dd {
		margin: 0;
		font-size: clamp(1.75rem, 1.3rem + 2vw, 2.75rem);
		font-weight: 600;
		letter-spacing: -0.02em;
		line-height: 1.05;
	}
	dt {
		color: var(--text-2);
		font-size: 0.875rem;
	}
</style>
