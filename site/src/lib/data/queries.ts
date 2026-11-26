/** The questions the pages ask of the data. Each reads one Parquet file of the deploy set. */
import type { Manifest, SlimRow } from '../types';
import type { Filters } from '../urlstate';
import { analyteIdOfRow } from '../rowid';
import { readRow, readTable, warm, type Row } from './store';
import { applyFilters, facetCounts, textMatches } from './filter';

export type { FacetOption } from './filter';

function slimFile(manifest: Manifest, analyteId: string) {
	const f = manifest.files.slim[analyteId];
	if (!f) throw new Error(`Unknown analyte "${analyteId}"`);
	return f;
}
const byIds = (a: SlimRow, b: SlimRow) => (a.interferent_id < b.interferent_id ? -1 : a.interferent_id > b.interferent_id ? 1 : a.row_id < b.row_id ? -1 : a.row_id > b.row_id ? 1 : 0);

/** Begin downloading an analyte's rows before anything asks for them. */
export function warmAnalyte(manifest: Manifest, analyteId: string): void {
	const f = manifest.files.slim[analyteId];
	if (f) warm(f.path, f.bytes);
}

/** Evidence rows of one analyte (analyte page, interferent page), filtered. */
export async function analyteRows(manifest: Manifest, analyteId: string, filters: Filters, fixed: Record<string, string> = {}) {
	const f = slimFile(manifest, analyteId);
	return applyFilters(await readTable<SlimRow>(f.path, f.bytes), filters, fixed);
}

/** Every value of every facet for an analyte, with counts. */
export async function analyteFacets(manifest: Manifest, analyteId: string, fixed: Record<string, string> = {}) {
	const f = slimFile(manifest, analyteId);
	const none = { interferent: [], concept: [], platform: [], analyzer: [], sample: [], direction: [], ref: [] };
	return facetCounts(applyFilters(await readTable<SlimRow>(f.path, f.bytes), none, fixed));
}

export interface MatrixCell {
	concept: string;
	analyte_id: string;
	n: number;
	plottable: number;
	exceeds: number;
}
/** Concept x analyte: rows, plottable rows, and plottable rows beyond the default APS. */
export async function matrixCells(manifest: Manifest): Promise<MatrixCell[]> {
	const f = manifest.files.slim_all;
	const rows = await readTable<SlimRow>(f.path, f.bytes, ['concept', 'analyte_id', 'pct_change', 'aps_percent']);
	const cells = new Map<string, MatrixCell>();
	for (const r of rows) {
		const key = `${r.concept}|${r.analyte_id}`;
		let c = cells.get(key);
		if (!c) cells.set(key, (c = { concept: r.concept, analyte_id: r.analyte_id, n: 0, plottable: 0, exceeds: 0 }));
		c.n += 1;
		if (typeof r.pct_change === 'number') {
			c.plottable += 1;
			if (Math.abs(r.pct_change) > r.aps_percent) c.exceeds += 1;
		}
	}
	return [...cells.values()];
}

/** One concept across all analytes. */
export async function conceptRows(manifest: Manifest, concept: string) {
	const f = manifest.files.slim_all;
	const rows = await readTable<SlimRow>(f.path, f.bytes);
	return rows.filter((r) => r.concept === concept).sort((a, b) => (a.analyte_id < b.analyte_id ? -1 : a.analyte_id > b.analyte_id ? 1 : byIds(a, b)));
}

export const SEARCH_PAGE = 25;
const SLIM_SEARCH_COLUMNS = ['interferent_canonical', 'interferent_verbatim', 'platform', 'analyzer', 'sample_type', 'doi', 'pmid', 'row_id'];
const DETAIL_SEARCH_COLUMNS = ['citation', 'full_reference_from_pdf', 'reference_full_resolved'];

export interface SearchHit extends SlimRow {
	citation?: string | null;
}
/**
 * Evidence rows matching a phrase. By default the short text columns of slim_all are
 * searched; `withCitations` also reads the citation columns of every detail file.
 */
export async function searchRows(manifest: Manifest, q: string, page: number, withCitations: boolean) {
	const f = manifest.files.slim_all;
	const needle = q.trim().toLowerCase();
	const rows = await readTable<SlimRow>(f.path, f.bytes);
	let citations: Map<string, Row> | null = null;
	if (withCitations) {
		const parts = await Promise.all(Object.values(manifest.files.detail).map((d) => readTable(d.path, d.bytes, ['row_id', ...DETAIL_SEARCH_COLUMNS])));
		citations = new Map();
		for (const part of parts) for (const r of part) citations.set(r.row_id as string, r);
	}
	const hits: SearchHit[] = [];
	for (const r of rows) {
		const extra = citations?.get(r.row_id);
		if (textMatches(r, SLIM_SEARCH_COLUMNS, needle) || (extra && textMatches(extra, DETAIL_SEARCH_COLUMNS, needle)))
			hits.push(extra ? { ...r, citation: extra.citation as string | null } : r);
	}
	const start = Math.max(0, page) * SEARCH_PAGE;
	return { total: hits.length, rows: hits.slice(start, start + SEARCH_PAGE) };
}

export interface RowDetail {
	detail: Record<string, string | null>;
	slim: Record<string, unknown> | null;
}
/** One evidence row: every source column from detail/<analyte>.parquet, verbatim. */
export async function rowDetail(manifest: Manifest, rowId: string): Promise<RowDetail | null> {
	const analyteId = analyteIdOfRow(rowId);
	if (!analyteId || !manifest.files.detail[analyteId]) return null;
	const d = manifest.files.detail[analyteId];
	const s = slimFile(manifest, analyteId);
	const [detail, slimRows] = await Promise.all([readRow(d.path, d.bytes, 'row_id', rowId), readTable(s.path, s.bytes)]);
	if (!detail) return null;
	return { detail: detail as Record<string, string | null>, slim: slimRows.find((r) => r.row_id === rowId) ?? null };
}

/** Every slim column of the current selection, for the CSV download. */
export async function exportRows(manifest: Manifest, analyteId: string, filters: Filters, fixed: Record<string, string>, aps: number): Promise<Row[]> {
	const f = slimFile(manifest, analyteId);
	const rows = applyFilters(await readTable(f.path, f.bytes), filters, fixed);
	return rows.map((r) => ({
		...r,
		active_aps_percent: aps,
		verdict_at_active_aps: typeof r.pct_change !== 'number' ? 'not_computable' : Math.abs(r.pct_change) > aps ? 'exceeds' : 'within'
	}));
}
