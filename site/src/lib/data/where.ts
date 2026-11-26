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

/** A parameterised WHERE clause; user-chosen values never enter the SQL text. */
export function buildWhere(filters: Filters, fixed: Record<string, string> = {}): { sql: string; params: string[] } {
	const parts: string[] = [];
	const params: string[] = [];
	for (const [col, v] of Object.entries(fixed)) {
		parts.push(`${col} = ?`);
		params.push(v);
	}
	for (const key of FILTER_KEYS) {
		const values = filters[key];
		if (!values.length) continue;
		parts.push(`${FILTER_COLUMNS[key]} IN (${values.map(() => '?').join(', ')})`);
		params.push(...values);
	}
	return { sql: parts.length ? `WHERE ${parts.join(' AND ')}` : '', params };
}
