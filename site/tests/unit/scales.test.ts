import { describe, expect, it } from 'vitest';
import { clipBound, clipValue, countBeyond, jitter, quantile, symlog, symlogTicks } from '../../src/lib/scales';

describe('symlog helpers', () => {
	it('is odd, zero at zero and monotonic', () => {
		expect(symlog(0)).toBe(0);
		expect(symlog(-50)).toBeCloseTo(-symlog(50));
		expect(symlog(66533.3)).toBeGreaterThan(symlog(14100));
		expect(symlog(0.5)).toBeGreaterThan(0);
	});
	it('gives readable ticks across extreme ranges', () => {
		expect(symlogTicks(-100, 66533.3)).toEqual([-100, -10, -1, 0, 1, 10, 100, 1000, 10000]);
		expect(symlogTicks(-3736.4, 4625)).toEqual([-1000, -100, -10, -1, 0, 1, 10, 100, 1000]);
		expect(symlogTicks(-1.8, 2.88)).toEqual([-1, 0, 1]);
		expect(symlogTicks(2, 50)).toEqual([10]);
		expect(symlogTicks(5, 1)).toEqual([0]);
	});
});

describe('clipping helpers', () => {
	it('computes quantiles by linear interpolation', () => {
		expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3);
		expect(quantile([0, 10], 0.25)).toBe(2.5);
		expect(quantile([], 0.5)).toBeNaN();
	});
	it('derives a round bound from the data and keeps the APS band on the axis', () => {
		const values = [...Array.from({ length: 99 }, (_, i) => i - 49), 14100];
		const bound = clipBound(values);
		expect(bound).toBeGreaterThanOrEqual(49);
		expect(bound).toBeLessThan(14100);
		expect(clipBound([0.1, -0.2], 13.6)).toBeGreaterThanOrEqual(13.6 * 1.5);
		expect(clipBound([])).toBe(1);
	});
	it('places values beyond the bound at the edge and flags them; nothing is dropped', () => {
		expect(clipValue(14100, 100)).toEqual({ value: 100, clipped: 1 });
		expect(clipValue(-3736.4, 100)).toEqual({ value: -100, clipped: -1 });
		expect(clipValue(100, 100)).toEqual({ value: 100, clipped: 0 });
		expect(clipValue(-12, 100)).toEqual({ value: -12, clipped: 0 });
		const values = [1, -5, 250, -900, 14100];
		expect(values.map((v) => clipValue(v, 100)).length).toBe(values.length);
		expect(countBeyond(values, 100)).toBe(3);
	});
	it('jitter is deterministic and within 0..1', () => {
		const j = jitter('tn.troponin_hemolysis_interference.0058');
		expect(j).toBe(jitter('tn.troponin_hemolysis_interference.0058'));
		expect(j).toBeGreaterThanOrEqual(0);
		expect(j).toBeLessThan(1);
	});
});
