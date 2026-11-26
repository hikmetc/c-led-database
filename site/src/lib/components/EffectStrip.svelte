<script lang="ts">
	import PlotFigure from './PlotFigure.svelte';
	import { clipBound, jitter, symlogTicks } from '$lib/scales';

	export interface StripPoint {
		id: string;
		group: string;
		pct: number;
		tip: string;
	}
	export interface StripGroup {
		key: string;
		label: string;
		aps: number;
	}
	let { points, groups, scale, onselect, beyond = $bindable(0) }: {
		points: StripPoint[];
		groups: StripGroup[];
		scale: 'symlog' | 'linear';
		onselect?: (id: string) => void;
		/** number of values drawn at the axis edge (linear scale only) */
		beyond?: number;
	} = $props();

	const layout = $derived.by(() => {
		const values = points.map((p) => p.pct);
		const maxAps = Math.max(1, ...groups.map((g) => g.aps).filter(Number.isFinite));
		let lo = Math.min(-maxAps * 1.5, ...values);
		let hi = Math.max(maxAps * 1.5, ...values);
		if (scale === 'linear') {
			const bound = clipBound(values, maxAps);
			lo = Math.max(lo, -bound);
			hi = Math.min(hi, bound);
		}
		const apsOf = new Map(groups.map((g) => [g.key, g.aps]));
		let n = 0;
		const data = points.map((p) => {
			const clipped = p.pct > hi ? 1 : p.pct < lo ? -1 : 0;
			if (clipped) n += 1;
			return { ...p, x: clipped > 0 ? hi : clipped < 0 ? lo : p.pct, y: jitter(p.id), clipped, exceeds: Math.abs(p.pct) > (apsOf.get(p.group) ?? Infinity) };
		});
		return { data, lo, hi, n };
	});
	$effect(() => {
		beyond = layout.n;
	});

	const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
	function build(Plot: typeof import('@observablehq/plot'), width: number) {
		const { data, lo, hi } = layout;
		const single = groups.length === 1;
		const rowH = single ? 150 : 56;
		const maxChars = Math.max(18, Math.floor(width / 6.6));
		const short = (s: string) => (s.length > maxChars ? s.slice(0, maxChars - 1) + '…' : s);
		const within = data.filter((d) => !d.exceeds && !d.clipped);
		const exceeds = data.filter((d) => d.exceeds && !d.clipped);
		const clipped = data.filter((d) => d.clipped);
		return {
			width,
			height: 30 + groups.length * rowH + 44,
			marginTop: 30,
			marginBottom: 44,
			marginLeft: 10,
			marginRight: 14,
			style: { background: 'transparent', color: 'var(--text-2)', fontFamily: 'inherit', fontSize: '12px', overflow: 'visible' },
			x: {
				type: scale === 'symlog' ? 'symlog' : 'linear',
				...(scale === 'symlog' ? { constant: 1, ticks: symlogTicks(lo, hi) } : { ticks: Math.max(4, Math.floor(width / 110)) }),
				domain: [lo, hi],
				tickFormat: (d: number) => (d > 0 ? '+' : d < 0 ? '−' : '') + fmt.format(Math.abs(d)),
				label: scale === 'symlog' ? 'Change in measured value, % (symmetric log scale)' : 'Change in measured value, % (linear scale, clipped)',
				labelAnchor: 'center',
				tickSize: 4
			},
			y: { axis: null, domain: [-0.25, 1.25] },
			fy: { domain: groups.map((g) => g.key), axis: null, padding: single ? 0 : 0.42 },
			marks: [
				Plot.rect(groups.filter((g) => Number.isFinite(g.aps)), { x1: (g: any) => Math.max(lo, -g.aps), x2: (g: any) => Math.min(hi, g.aps), fy: 'key', fill: 'var(--band)' }),
				Plot.ruleX([0], { stroke: 'var(--control)', strokeOpacity: 0.6 }),
				Plot.dot(within, { x: 'x', y: 'y', fy: 'group', r: 2.4, fill: 'none', stroke: 'var(--within)', strokeWidth: 1.1 }),
				Plot.dot(exceeds, { x: 'x', y: 'y', fy: 'group', r: 3, symbol: 'diamond', fill: 'var(--exceeds)', fillOpacity: 0.85 }),
				Plot.dot(clipped, { x: 'x', y: 'y', fy: 'group', r: 4.5, symbol: 'triangle', rotate: (d: any) => (d.clipped > 0 ? 90 : -90), fill: 'var(--exceeds)', stroke: 'var(--text)', strokeWidth: 1 }),
				Plot.text(groups, { fy: 'key', text: (g: any) => short(g.label), frameAnchor: 'top-left', dy: -13, dx: -2, fontSize: 12.5, fill: 'var(--text)', textAnchor: 'start' }),
				Plot.tip(data, Plot.pointer({ x: 'x', y: 'y', fy: 'group', title: 'tip', maxRadius: 28, fill: 'var(--bg)', stroke: 'var(--control)', textPadding: 10, lineWidth: 24 }))
			]
		};
	}
</script>

<PlotFigure {build} onpick={onselect ? (d) => onselect(d.id) : undefined} />
