import { describe, expect, it } from 'vitest';
import { activeFilterCount, decodeState, defaultState, encodeState, type ViewState } from '../../src/lib/urlstate';
import { applyFilters, facetCounts, textMatches } from '../../src/lib/data/filter';
import { humanize, pct, toCsv, isNotReported } from '../../src/lib/format';
import { highlightParts } from '../../src/lib/search';

describe('URL state', () => {
	it('round-trips a full state', () => {
		const state: ViewState = {
			aps: 5,
			scale: 'linear',
			filters: { interferent: ['tn.hemolysis', 'tn.biotin'], concept: ['hemolysis'], platform: ['Roche Elecsys Troponin T Gen 5 STAT (sandwich)'], analyzer: ["MDA 180 (bioMérieux, Marcy l'Etoile, France)"], sample: ['Serum & plasma = 50%'], direction: ['up', 'not_reported'], ref: ['doi'] }
		};
		const qs = encodeState(state).toString();
		expect(decodeState(new URLSearchParams(qs))).toEqual(state);
	});
	it('the default state is an empty query string', () => {
		expect(encodeState(defaultState()).toString()).toBe('');
		expect(decodeState(new URLSearchParams(''))).toEqual(defaultState());
	});
	it('writes ?aps=5 for a custom APS and nothing for the default', () => {
		expect(encodeState({ ...defaultState(), aps: 5 }).toString()).toBe('aps=5');
		expect(encodeState({ ...defaultState(), aps: 0.4 }).toString()).toBe('aps=0.4');
	});
	it('ignores unusable values and keeps unrelated parameters', () => {
		const s = decodeState(new URLSearchParams('aps=abc&scale=weird&direction=&direction=up&direction=up'));
		expect(s.aps).toBeNull();
		expect(s.scale).toBe('symlog');
		expect(s.filters.direction).toEqual(['up']);
		const out = encodeState({ ...defaultState(), aps: 2 }, new URLSearchParams('utm=x&aps=9'));
		expect(out.get('utm')).toBe('x');
		expect(out.getAll('aps')).toEqual(['2']);
	});
	it('counts active filters', () => {
		expect(activeFilterCount(decodeState(new URLSearchParams('direction=up&ref=doi&ref=pmid')).filters)).toBe(3);
	});
});

describe('filters', () => {
	const rows = [
		{ row_id: 'a.t.0001', interferent_id: 'a.x', concept: 'hemolysis', platform: "O'Neil; 100%", analyzer: 'A1', sample_type: 'Serum', direction: 'up', reference_status: 'doi' },
		{ row_id: 'a.t.0002', interferent_id: 'a.x', concept: 'hemolysis', platform: 'P2', analyzer: 'A1', sample_type: 'Plasma', direction: 'down', reference_status: 'pmid' },
		{ row_id: 'a.t.0003', interferent_id: 'a.y', concept: 'lipemia', platform: 'P2', analyzer: null, sample_type: 'Serum', direction: 'none', reference_status: 'doi' }
	];
	it('combines filters with AND and the values of one filter with OR', () => {
		const f = decodeState(new URLSearchParams('direction=up&direction=down&ref=doi')).filters;
		expect(applyFilters(rows, f).map((r) => r.row_id)).toEqual(['a.t.0001']);
		expect(applyFilters(rows, defaultState().filters)).toBe(rows);
		expect(applyFilters(rows, defaultState().filters, { interferent_id: 'a.y' }).map((r) => r.row_id)).toEqual(['a.t.0003']);
	});
	it('matches values exactly, whatever characters they hold', () => {
		const f = decodeState(new URLSearchParams({ platform: "O'Neil; 100%" })).filters;
		expect(applyFilters(rows, f).length).toBe(1);
		expect(applyFilters(rows, decodeState(new URLSearchParams({ platform: 'P' })).filters).length).toBe(0);
	});
	it('counts facet values and skips nulls', () => {
		const c = facetCounts(rows);
		expect(c.direction).toEqual([{ value: 'down', n: 1 }, { value: 'none', n: 1 }, { value: 'up', n: 1 }]);
		expect(c.platform[0]).toEqual({ value: 'P2', n: 2 });
		expect(c.analyzer).toEqual([{ value: 'A1', n: 2 }]);
	});
	it('searches text case-insensitively', () => {
		expect(textMatches(rows[0], ['platform', 'analyzer'], "o'neil")).toBe(true);
		expect(textMatches(rows[2], ['analyzer'], 'a1')).toBe(false);
	});
});

describe('formatting', () => {
	it('shows a missing percent change as "Not reported", never as zero', () => {
		expect(pct(null)).toBe('Not reported');
		expect(pct(undefined)).toBe('Not reported');
		expect(pct(NaN)).toBe('Not reported');
		expect(pct(0)).toBe('0 %');
		expect(pct(14100)).toBe('+14,100 %');
		expect(pct(-9.4)).toBe('−9.4 %');
	});
	it('recognises the phrases sources use for a missing value', () => {
		expect(isNotReported('not reported in the information source')).toBe(true);
		expect(isNotReported(null)).toBe(true);
		expect(isNotReported('0')).toBe(false);
	});
	it('humanises concept ids by rule, not by vocabulary', () => {
		expect(humanize('hemolysis')).toBe('Hemolysis');
		expect(humanize('iv_fluid_contamination')).toBe('IV fluid contamination');
		expect(humanize('vitamin_b12')).toBe('Vitamin B12');
	});
	it('writes RFC 4180 CSV', () => {
		expect(toCsv(['a', 'b'], [{ a: 'x,y', b: 'say "hi"' }, { a: null, b: 0 }])).toBe('a,b\r\n"x,y","say ""hi"""\r\n,0\r\n');
	});
	it('splits text around matches for highlighting', () => {
		expect(highlightParts('Hemolysis (hemoglobin)', 'hemo')).toEqual([
			{ text: 'Hemo', hit: true }, { text: 'lysis (', hit: false }, { text: 'hemo', hit: true }, { text: 'globin)', hit: false }
		]);
		expect(highlightParts('abc', '')).toEqual([{ text: 'abc', hit: false }]);
	});
});
