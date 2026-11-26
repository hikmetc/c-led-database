import type { Manifest } from './types';

/** Major versions of the Parquet layer this site knows how to read. */
export const KNOWN_SCHEMA_MAJORS = ['1'];

export type ManifestResult =
	| { ok: true; manifest: Manifest }
	| { ok: false; error: string };

function isObject(v: unknown): v is Record<string, unknown> {
	return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function checkFile(v: unknown, what: string): string | null {
	if (!isObject(v)) return `${what} is missing`;
	if (typeof v.path !== 'string' || !v.path.endsWith('.parquet')) return `${what} has no Parquet path`;
	if (typeof v.rows !== 'number' || !Number.isFinite(v.rows) || v.rows < 0) return `${what} has no row count`;
	return null;
}

/** Validate parquet/manifest.json. An unknown schema version is an error, never a guess. */
export function validateManifest(raw: unknown): ManifestResult {
	if (!isObject(raw)) return { ok: false, error: 'The data manifest is not a JSON object.' };
	const version = raw.schema_version;
	if (typeof version !== 'string' || version.trim() === '')
		return { ok: false, error: 'The data manifest carries no schema_version.' };
	const major = version.split('.')[0];
	if (!KNOWN_SCHEMA_MAJORS.includes(major))
		return {
			ok: false,
			error: `The data uses schema version ${version}, which this version of the site does not know (it reads ${KNOWN_SCHEMA_MAJORS.map((m) => m + '.x').join(', ')}).`
		};
	if (typeof raw.row_count !== 'number') return { ok: false, error: 'The data manifest has no row_count.' };
	const files = raw.files;
	if (!isObject(files)) return { ok: false, error: 'The data manifest lists no files.' };
	const problems: string[] = [];
	const p = checkFile(files.slim_all, 'slim_all');
	if (p) problems.push(p);
	if (!isObject(files.slim) || !isObject(files.detail)) problems.push('slim or detail file list is missing');
	else {
		for (const [id, f] of Object.entries(files.slim)) {
			const e = checkFile(f, `slim/${id}`);
			if (e) problems.push(e);
			if (!(id in files.detail)) problems.push(`detail/${id} is missing`);
		}
		for (const [id, f] of Object.entries(files.detail)) {
			const e = checkFile(f, `detail/${id}`);
			if (e) problems.push(e);
			if (!(id in files.slim)) problems.push(`slim/${id} is missing`);
		}
	}
	if (problems.length) return { ok: false, error: `The data manifest is incomplete: ${problems.join('; ')}.` };
	return { ok: true, manifest: raw as unknown as Manifest };
}

/** Analyte ids, in manifest order. The manifest is the only list of analytes the site uses. */
export function analyteIds(manifest: Manifest): string[] {
	return Object.keys(manifest.files.slim);
}
