/** Helpers for the two x scales of the effect charts: symmetric log, and linear clipped. */

export function symlog(x: number, constant = 1): number {
	return Math.sign(x) * Math.log1p(Math.abs(x) / constant);
}

/** Readable tick values for a symlog axis: 0 and signed powers of ten inside the domain. */
export function symlogTicks(min: number, max: number): number[] {
	if (!(min <= max)) return [0];
	const ticks = new Set<number>();
	if (min <= 0 && max >= 0) ticks.add(0);
	const top = Math.max(Math.abs(min), Math.abs(max));
	for (let p = 1; p <= top * 1.0000001; p *= 10) {
		if (p <= max && p >= min) ticks.add(p);
		if (-p >= min && -p <= max) ticks.add(-p);
	}
	return [...ticks].sort((a, b) => a - b);
}

/** Linear-interpolated quantile of an ascending array. */
export function quantile(sorted: number[], p: number): number {
	if (!sorted.length) return NaN;
	const i = (sorted.length - 1) * Math.min(1, Math.max(0, p));
	const lo = Math.floor(i);
	const hi = Math.ceil(i);
	return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

function niceCeil(v: number): number {
	if (!(v > 0)) return 1;
	const mag = 10 ** Math.floor(Math.log10(v));
	for (const m of [1, 2, 5, 10]) if (m * mag >= v) return m * mag;
	return 10 * mag;
}

/**
 * Data-driven bound of the clipped linear axis: the 95th percentile of |value|, rounded up
 * to a round number. `floor` keeps the reference band (the APS) on the axis.
 */
export function clipBound(values: number[], floor = 0, p = 0.95): number {
	const abs = values.filter((v) => Number.isFinite(v)).map(Math.abs).sort((a, b) => a - b);
	const q = abs.length ? quantile(abs, p) : 0;
	return niceCeil(Math.max(q, floor * 1.5, 1));
}

export interface Clipped {
	value: number;
	/** -1 clipped at the lower edge, 1 at the upper edge, 0 drawn at its true position */
	clipped: -1 | 0 | 1;
}

/** Points beyond the bound sit at the edge and are flagged; no point is ever dropped. */
export function clipValue(v: number, bound: number): Clipped {
	if (v > bound) return { value: bound, clipped: 1 };
	if (v < -bound) return { value: -bound, clipped: -1 };
	return { value: v, clipped: 0 };
}

export function countBeyond(values: number[], bound: number): number {
	let n = 0;
	for (const v of values) if (Math.abs(v) > bound) n += 1;
	return n;
}

/** Deterministic 0..1 jitter from a row id, so a dot keeps its place between renders. */
export function jitter(id: string): number {
	let h = 2166136261;
	for (let i = 0; i < id.length; i++) {
		h ^= id.charCodeAt(i);
		h = Math.imul(h, 16777619);
	}
	return ((h >>> 0) % 10000) / 10000;
}
