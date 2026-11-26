<script lang="ts">
	import { onMount } from 'svelte';

	type PlotModule = typeof import('@observablehq/plot');
	let { build, onpick, minWidth = 0 }: { build: (Plot: PlotModule, width: number) => unknown; onpick?: (datum: any) => void; minWidth?: number } = $props();
	let host = $state<HTMLDivElement | undefined>();
	let Plot = $state<PlotModule | null>(null);
	let width = $state(0);
	let failed = $state(false);

	onMount(() => {
		import('@observablehq/plot').then((m) => (Plot = m)).catch(() => (failed = true));
		const ro = new ResizeObserver((entries) => {
			const w = Math.round(entries[0].contentRect.width);
			if (w && Math.abs(w - width) > 1) width = w;
		});
		if (host) ro.observe(host);
		return () => ro.disconnect();
	});

	$effect(() => {
		if (!Plot || !host || !width) return;
		const options = build(Plot, Math.max(width, minWidth)) as any; // read here, so changes are tracked
		const plot = Plot;
		const target = host;
		// draw in the next frame; a newer request replaces one that has not been drawn yet
		const frame = requestAnimationFrame(() => draw(plot, target, options));
		return () => cancelAnimationFrame(frame);
	});

	let first = true;
	function draw(Plot: PlotModule, host: HTMLDivElement, options: any) {
		const el = Plot.plot(options) as (SVGElement | HTMLElement) & { value?: unknown };
		if (first) el.classList.add('fade-in'); // later redraws swap in place, without a flash
		first = false;
		// the surrounding element carries the text alternative; the SVG internals are not announced
		el.setAttribute('aria-hidden', 'true');
		if (onpick) {
			el.addEventListener('click', () => {
				if (el.value) onpick(el.value);
			});
			(el as HTMLElement).style.cursor = 'pointer';
		}
		host.replaceChildren(el);
	}
</script>

<div class="plot" bind:this={host} class:scroll={minWidth > 0}>
	{#if failed}<p class="caption">The chart library could not be loaded. Use "View as table".</p>{:else}<div class="skeleton" style="height:240px"></div>{/if}
</div>

<style>
	.plot {
		width: 100%;
		min-height: 120px;
	}
	.plot.scroll {
		overflow-x: auto;
	}
	.plot :global(svg) {
		display: block;
		max-width: none;
	}
</style>
