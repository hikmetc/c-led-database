import type { Manifest, SlimRow } from '../types';
import type { Filters } from '../urlstate';
import { analyteIdOfRow } from '../rowid';
import { lit, query } from './db';
import { buildWhere, FILTER_COLUMNS } from './where';

const VIEW_COLUMNS = [
	'row_id', 'analyte_id', 'interferent_id', 'interferent_canonical', 'concept', 'interferent_verbatim',
	'platform', 'analyzer', 'sample_type', 'direction', 'pct_change', 'plottable', 'aps_percent',
	'aps_verdict', 'doi', 'pmid', 'reference_status'
].join(', ');

function slimFile(manifest: Manifest, analyteId: string): string {
	const f = manifest.files.slim[analyteId];
	if (!f) throw new Error(`Unknown analyte "${analyteId}"`);
	return f.path;
}

/** Evidence rows of one analyte (analyte page, interferent page). */
export function analyteRows(manifest: Manifest, analyteId: string, filters: Filters, fixed: Record<string, string> = {}) {
	const file = slimFile(manifest, analyteId);
	const w = buildWhere(filters, fixed);
	return query<SlimRow>(
		`SELECT ${VIEW_COLUMNS} FROM read_parquet(${lit(file)}) ${w.sql} ORDER BY interferent_id, row_id`,
		w.params,
		[file]
	);
}

export interface FacetOption {
	value: string;
	n: number;
}
/** Every value of every facet for an analyte, with counts, in one query. */
export async function analyteFacets(manifest: Manifest, analyteId: string, fixed: Record<string, string> = {}) {
	const file = slimFile(manifest, analyteId);
	const w = buildWhere({ interferent: [], concept: [], platform: [], analyzer: [], sample: [], direction: [], ref: [] }, fixed);
	const selects = Object.entries(FILTER_COLUMNS).map(
		([key, col]) =>
			`SELECT '${key}' AS facet, ${col} AS value, count(*) AS n FROM read_parquet(${lit(file)}) ${w.sql} GROUP BY ${col}`
	);
	const rows = await query<{ facet: string; value: string | null; n: number }>(
		selects.join(' UNION ALL '),
		selects.flatMap(() => w.params),
		[file]
	);
	const out: Record<string, FacetOption[]> = {};
	for (const key of Object.keys(FILTER_COLUMNS)) out[key] = [];
	for (const r of rows) if (r.value !== null) out[r.facet].push({ value: r.value, n: r.n });
	for (const list of Object.values(out)) list.sort((a, b) => b.n - a.n || a.value.localeCompare(b.value));
	return out;
}

export interface MatrixCell {
	concept: string;
	analyte_id: string;
	n: number;
	plottable: number;
	exceeds: number;
}
/** Concept x analyte: rows, plottable rows, and plottable rows beyond the default APS. */
export function matrixCells(manifest: Manifest) {
	const file = manifest.files.slim_all.path;
	return query<MatrixCell>(
		`SELECT concept, analyte_id, count(*) AS n,
		        count(*) FILTER (WHERE plottable) AS plottable,
		        count(*) FILTER (WHERE plottable AND abs(pct_change) > aps_percent) AS exceeds
		 FROM read_parquet(${lit(file)}) GROUP BY concept, analyte_id`,
		[],
		[file]
	);
}

/** One concept across all analytes. */
export function conceptRows(manifest: Manifest, concept: string) {
	const file = manifest.files.slim_all.path;
	return query<SlimRow>(
		`SELECT ${VIEW_COLUMNS} FROM read_parquet(${lit(file)}) WHERE concept = ? ORDER BY analyte_id, interferent_id, row_id`,
		[concept],
		[file]
	);
}

export const SEARCH_PAGE = 25;
const SLIM_SEARCH_COLUMNS = ['interferent_canonical', 'interferent_verbatim', 'platform', 'analyzer', 'sample_type', 'doi', 'pmid', 'row_id'];
const DETAIL_SEARCH_COLUMNS = ['citation', 'full_reference_from_pdf', 'reference_full_resolved'];

function likePattern(q: string): string {
	return `%${q.replace(/[\\%_]/g, (c) => '\\' + c)}%`;
}

export interface SearchHit extends SlimRow {
	citation?: string | null;
}
/**
 * Evidence rows matching a phrase. By default the short text columns of slim_all are
 * searched; `withCitations` also reads the citation columns of every detail file.
 */
export async function searchRows(manifest: Manifest, q: string, page: number, withCitations: boolean) {
	const file = manifest.files.slim_all.path;
	const pat = likePattern(q);
	const slimCond = SLIM_SEARCH_COLUMNS.map((c) => `s.${c} ILIKE ? ESCAPE '\\'`).join(' OR ');
	let from = `read_parquet(${lit(file)}) s`;
	let cond = slimCond;
	let params: unknown[] = SLIM_SEARCH_COLUMNS.map(() => pat);
	let files = [file];
	let extra = '';
	if (withCitations) {
		const details = Object.values(manifest.files.detail).map((f) => f.path);
		from += ` JOIN read_parquet([${details.map(lit).join(', ')}]) d ON d.row_id = s.row_id`;
		cond += ' OR ' + DETAIL_SEARCH_COLUMNS.map((c) => `d.${c} ILIKE ? ESCAPE '\\'`).join(' OR ');
		params = [...params, ...DETAIL_SEARCH_COLUMNS.map(() => pat)];
		files = [...files, ...details];
		extra = ', d.citation AS citation';
	}
	const cols = VIEW_COLUMNS.split(', ').map((c) => `s.${c}`).join(', ');
	const [count] = await query<{ n: number }>(`SELECT count(*) AS n FROM ${from} WHERE ${cond}`, params, files);
	const rows = await query<SearchHit>(
		`SELECT ${cols}${extra} FROM ${from} WHERE ${cond} ORDER BY s.analyte_id, s.interferent_id, s.row_id LIMIT ${SEARCH_PAGE} OFFSET ${Math.max(0, page) * SEARCH_PAGE}`,
		params,
		files
	);
	return { total: count?.n ?? 0, rows };
}

export interface RowDetail {
	detail: Record<string, string | null>;
	slim: Record<string, unknown> | null;
}
/** One evidence row: every source column from detail/<analyte>.parquet, verbatim. */
export async function rowDetail(manifest: Manifest, rowId: string): Promise<RowDetail | null> {
	const analyteId = analyteIdOfRow(rowId);
	if (!analyteId || !manifest.files.detail[analyteId]) return null;
	const detailFile = manifest.files.detail[analyteId].path;
	const slim = slimFile(manifest, analyteId);
	const [d, s] = await Promise.all([
		query<Record<string, string | null>>(`SELECT * FROM read_parquet(${lit(detailFile)}) WHERE row_id = ?`, [rowId], [detailFile]),
		query<Record<string, unknown>>(`SELECT * FROM read_parquet(${lit(slim)}) WHERE row_id = ?`, [rowId], [slim])
	]);
	if (!d.length) return null;
	return { detail: d[0], slim: s[0] ?? null };
}

/** Every slim column of the current selection, for the CSV download. */
export function exportRows(manifest: Manifest, analyteId: string, filters: Filters, fixed: Record<string, string>, aps: number) {
	const file = slimFile(manifest, analyteId);
	const w = buildWhere(filters, fixed);
	const a = Number(aps);
	return query<Record<string, unknown>>(
		`SELECT *, ${a} AS active_aps_percent,
		        CASE WHEN pct_change IS NULL THEN 'not_computable'
		             WHEN abs(pct_change) > ${a} THEN 'exceeds' ELSE 'within' END AS verdict_at_active_aps
		 FROM read_parquet(${lit(file)}) ${w.sql} ORDER BY interferent_id, row_id`,
		w.params,
		[file]
	);
}
