/** Custom-APS logic. A row exceeds when abs(pct_change) > APS; a missing value is never zero. */
export type Judgement = 'exceeds' | 'within' | 'not_computable';

export const APS_MIN = 0.1;
export const APS_MAX = 1000;
export const APS_STEP = 0.1;

export function isNumber(v: unknown): v is number {
	return typeof v === 'number' && Number.isFinite(v);
}

export function judge(pctChange: number | null | undefined, aps: number): Judgement {
	if (!isNumber(pctChange) || !isNumber(aps)) return 'not_computable';
	return Math.abs(pctChange) > aps ? 'exceeds' : 'within';
}

/** Snap to the 0.1 % step and keep within the allowed range. */
export function clampAps(v: number): number {
	const snapped = Math.round(v * 10) / 10;
	return Math.min(APS_MAX, Math.max(APS_MIN, snapped));
}

/** Read `?aps=` from a URL. Anything unusable falls back to the analyte's default. */
export function resolveAps(raw: string | null | undefined, defaultAps: number): { value: number; isDefault: boolean } {
	if (raw == null || raw.trim() === '') return { value: defaultAps, isDefault: true };
	const n = Number(raw);
	if (!Number.isFinite(n) || n <= 0) return { value: defaultAps, isDefault: true };
	const value = clampAps(n);
	return { value, isDefault: value === defaultAps };
}

export interface ApsSummary {
	rows: number;
	plottable: number;
	notPlottable: number;
	exceeds: number;
	within: number;
	/** share of plottable rows that exceed; null when nothing is plottable */
	share: number | null;
}

export function summarize(rows: Iterable<{ pct_change: number | null }>, aps: number): ApsSummary {
	let n = 0;
	let exceeds = 0;
	let within = 0;
	for (const r of rows) {
		n += 1;
		const j = judge(r.pct_change, aps);
		if (j === 'exceeds') exceeds += 1;
		else if (j === 'within') within += 1;
	}
	const plottable = exceeds + within;
	return { rows: n, plottable, notPlottable: n - plottable, exceeds, within, share: plottable ? exceeds / plottable : null };
}

/** Upper end of the APS slider: wide enough to cross the bulk of this analyte's effects. */
export function sliderMax(defaultAps: number, absPctChanges: number[]): number {
	const sorted = absPctChanges.filter(isNumber).sort((a, b) => a - b);
	const q75 = sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.75))] : 0;
	const target = Math.max(defaultAps * 3, q75, 5);
	const nice = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200];
	return nice.find((v) => v >= target) ?? 200;
}
