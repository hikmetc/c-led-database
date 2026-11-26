import { describe, expect, it } from 'vitest';
import { activeFilterCount, decodeState, defaultState, encodeState, type ViewState } from '../../src/lib/urlstate';
import { buildWhere } from '../../src/lib/data/where';
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

describe('WHERE builder', () => {
	it('keeps every value out of the SQL text', () => {
		const state = decodeState(new URLSearchParams("platform=x'; DROP TABLE t; --&direction=up&direction=down"));
		const w = buildWhere(state.filters, { interferent_id: 'tn.hemolysis' });
		expect(w.sql).toBe('WHERE interferent_id = ? AND platform IN (?) AND direction IN (?, ?)');
		expect(w.params).toEqual(['tn.hemolysis', "x'; DROP TABLE t; --", 'up', 'down']);
		expect(buildWhere(defaultState().filters)).toEqual({ sql: '', params: [] });
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
