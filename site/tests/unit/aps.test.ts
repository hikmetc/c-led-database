import { describe, expect, it } from 'vitest';
import { clampAps, judge, resolveAps, sliderMax, summarize } from '../../src/lib/aps';

describe('custom-APS recomputation', () => {
	it('never judges a missing value, and never treats it as zero', () => {
		expect(judge(null, 5)).toBe('not_computable');
		expect(judge(undefined, 5)).toBe('not_computable');
		expect(judge(NaN, 5)).toBe('not_computable');
		expect(judge(0, 5)).toBe('within'); // a real zero is a value
	});
	it('uses the absolute value, so negative changes count', () => {
		expect(judge(-6, 5)).toBe('exceeds');
		expect(judge(-4.9, 5)).toBe('within');
		expect(judge(6, 5)).toBe('exceeds');
	});
	it('is strict: a change exactly equal to the APS does not exceed it', () => {
		expect(judge(5, 5)).toBe('within');
		expect(judge(-5, 5)).toBe('within');
		expect(judge(13.6, 13.6)).toBe('within');
		expect(judge(13.61, 13.6)).toBe('exceeds');
	});
	it('handles extreme values', () => {
		expect(judge(66533.3, 13.6)).toBe('exceeds');
		expect(judge(-3736.4, 1000)).toBe('exceeds');
		expect(judge(Infinity, 5)).toBe('not_computable');
	});
	it('summarises a selection without counting missing values as plottable', () => {
		const s = summarize([{ pct_change: 10 }, { pct_change: -10 }, { pct_change: 1 }, { pct_change: null }, { pct_change: 5 }], 5);
		expect(s).toEqual({ rows: 5, plottable: 4, notPlottable: 1, exceeds: 2, within: 2, share: 0.5 });
		expect(summarize([{ pct_change: null }], 5).share).toBeNull();
	});
	it('changing the APS changes the counts', () => {
		const rows = [1, 3, 7, 20, -40].map((pct_change) => ({ pct_change }));
		expect(summarize(rows, 2).exceeds).toBe(4);
		expect(summarize(rows, 10).exceeds).toBe(2);
		expect(summarize(rows, 50).exceeds).toBe(0);
	});
	it('snaps to 0.1 % steps and keeps within range', () => {
		expect(clampAps(5.04)).toBe(5);
		expect(clampAps(5.05)).toBe(5.1);
		expect(clampAps(0)).toBe(0.1);
		expect(clampAps(1e9)).toBe(1000);
	});
	it('reads ?aps= and falls back to the default for anything unusable', () => {
		expect(resolveAps(null, 3)).toEqual({ value: 3, isDefault: true });
		expect(resolveAps('', 3)).toEqual({ value: 3, isDefault: true });
		expect(resolveAps('abc', 3)).toEqual({ value: 3, isDefault: true });
		expect(resolveAps('-2', 3)).toEqual({ value: 3, isDefault: true });
		expect(resolveAps('5', 3)).toEqual({ value: 5, isDefault: false });
		expect(resolveAps('3', 3)).toEqual({ value: 3, isDefault: true });
	});
	it('derives the slider range from the data', () => {
		expect(sliderMax(0.4, [1, 2, 3, 4])).toBe(5);
		expect(sliderMax(13.6, [10, 20, 80, 90])).toBe(100);
		expect(sliderMax(3, [])).toBe(10);
		expect(sliderMax(3, [5000, 6000, 7000])).toBe(200);
	});
});
