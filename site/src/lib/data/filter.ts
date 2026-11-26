import { FILTER_KEYS, type FilterKey, type Filters } from '../urlstate';

/** URL filter key -> slim Parquet column. Facets use ids and normalised fields only. */
export const FILTER_COLUMNS: Record<FilterKey, string> = {
	interferent: 'interferent_id',
	concept: 'concept',
	platform: 'platform',
	analyzer: 'analyzer',
	sample: 'sample_type',
	direction: 'direction',
	ref: 'reference_status'
};

type AnyRow = Record<string, unknown>;

/** Rows that satisfy every active filter (values of one filter are alternatives). */
export function applyFilters<T extends object>(rows: T[], filters: Filters, fixed: Record<string, string> = {}): T[] {
	const tests: [string, Set<unknown>][] = Object.entries(fixed).map(([col, v]) => [col, new Set([v])]);
	for (const key of FILTER_KEYS) if (filters[key].length) tests.push([FILTER_COLUMNS[key], new Set(filters[key])]);
	if (!tests.length) return rows;
	return rows.filter((r) => tests.every(([col, allowed]) => allowed.has((r as AnyRow)[col])));
}

export interface FacetOption {
	value: string;
	n: number;
}
/** Every value of every facet with its row count, most frequent first. */
export function facetCounts(rows: object[]): Record<FilterKey, FacetOption[]> {
	const out = {} as Record<FilterKey, FacetOption[]>;
	for (const key of FILTER_KEYS) {
		const counts = new Map<string, number>();
		const col = FILTER_COLUMNS[key];
		for (const r of rows) {
			const v = (r as AnyRow)[col];
			if (typeof v === 'string') counts.set(v, (counts.get(v) ?? 0) + 1);
		}
		out[key] = [...counts].map(([value, n]) => ({ value, n })).sort((a, b) => b.n - a.n || a.value.localeCompare(b.value));
	}
	return out;
}

/** Case-insensitive "contains" over some columns; used by the evidence search. */
export function textMatches(row: object, columns: string[], needle: string): boolean {
	for (const c of columns) {
		const v = (row as AnyRow)[c];
		if (typeof v === 'string' && v.toLowerCase().includes(needle)) return true;
	}
	return false;
}
