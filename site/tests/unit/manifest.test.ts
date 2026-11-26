import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyteIds, validateManifest } from '../../src/lib/manifest';
import { analyteIdOfInterferent, analyteIdOfRow } from '../../src/lib/rowid';
import { buildIndex } from '../../src/lib/site';

const file = (rows = 3) => ({ path: 'parquet/slim/x.parquet', rows, bytes: 10 });
const good = () => ({
	schema_version: '1.0',
	row_count: 6,
	slim_columns: [],
	detail_columns: [],
	files: { slim_all: { path: 'parquet/slim_all.parquet', rows: 6, bytes: 1 }, slim: { a: file(), b: file() }, detail: { a: file(), b: file() } }
});

describe('manifest validation', () => {
	it('accepts a well-formed manifest and lists its analytes in order', () => {
		const r = validateManifest(good());
		expect(r.ok).toBe(true);
		if (r.ok) expect(analyteIds(r.manifest)).toEqual(['a', 'b']);
	});
	it('accepts a later minor version of a known major', () => {
		expect(validateManifest({ ...good(), schema_version: '1.7' }).ok).toBe(true);
	});
	it('rejects an unknown schema version instead of guessing', () => {
		const r = validateManifest({ ...good(), schema_version: '2.0' });
		expect(r.ok).toBe(false);
		if (!r.ok) expect(r.error).toMatch(/schema version 2\.0/);
	});
	it('rejects a missing schema version and malformed input', () => {
		expect(validateManifest({ ...good(), schema_version: undefined }).ok).toBe(false);
		expect(validateManifest(null).ok).toBe(false);
		expect(validateManifest([]).ok).toBe(false);
		expect(validateManifest({ schema_version: '1.0', row_count: 1 }).ok).toBe(false);
	});
	it('rejects an analyte with a slim file but no detail file', () => {
		const m = good();
		delete (m.files.detail as Record<string, unknown>).b;
		const r = validateManifest(m);
		expect(r.ok).toBe(false);
		if (!r.ok) expect(r.error).toMatch(/detail\/b/);
	});
});

describe('row_id and interferent_id parsing', () => {
	it('takes the text before the first dot', () => {
		expect(analyteIdOfRow('tn.troponin_hemolysis_interference.0058')).toBe('tn');
		expect(analyteIdOfRow('cohb.carboxyhemoglobin_blood-ph_20261026-1304_APS1_extraction_table.0002')).toBe('cohb');
		expect(analyteIdOfRow('k.a.b.c.0001')).toBe('k');
		expect(analyteIdOfInterferent('pco2.air_bubble_30min')).toBe('pco2');
	});
	it('returns null for anything that is not an id', () => {
		expect(analyteIdOfRow('')).toBeNull();
		expect(analyteIdOfRow('nodot')).toBeNull();
		expect(analyteIdOfRow('.leading')).toBeNull();
		expect(analyteIdOfRow('trailing.')).toBeNull();
		expect(analyteIdOfRow(undefined as unknown as string)).toBeNull();
	});
});

describe('site index', () => {
	it('is driven by the manifest: an analyte without a registry record still appears', () => {
		const r = validateManifest(good());
		if (!r.ok) throw new Error('fixture');
		const index = buildIndex({
			manifest: r.manifest,
			manifestError: null,
			analytes: [{ analyte_id: 'a', analyte_folder: 'a_serum', component: 'A', system: 'Serum', kind_of_property: '', unit: '', aps_percent: 2, aps_type: '', aps_note: '', synonyms: '', interferent_count: 1, evidence_tables: 1, evidence_rows: 3 }],
			interferents: [
				{ interferent_id: 'a.hemolysis', analyte_folder: 'a_serum', interferent_key: 'hemolysis', interferent_canonical: 'Hemolysis', concept: 'hemolysis', evidence_rows: 3, wording_variants: 1 },
				{ interferent_id: 'a.unused', analyte_folder: 'a_serum', interferent_key: 'unused', interferent_canonical: 'Unused', concept: 'other', evidence_rows: 0, wording_variants: 0 }
			],
			stats: null,
			dictionary: []
		})!;
		expect(index.analytes.map((a) => a.analyte_id)).toEqual(['a', 'b']);
		expect(index.analyteById.get('b')!.component).toBe('b');
		expect(index.interferentById.has('a.unused')).toBe(false); // a cause no row uses has no page
		expect(index.concepts.map((c) => c.concept)).toEqual(['hemolysis']);
	});

	const real = 'static/data/parquet/manifest.json';
	it.skipIf(!fs.existsSync(real))('the real manifest validates and its counts agree', () => {
		const r = validateManifest(JSON.parse(fs.readFileSync(real, 'utf8')));
		expect(r.ok).toBe(true);
		if (!r.ok) return;
		const m = r.manifest;
		const sum = (o: Record<string, { rows: number }>) => Object.values(o).reduce((s, f) => s + f.rows, 0);
		expect(sum(m.files.slim)).toBe(m.row_count);
		expect(sum(m.files.detail)).toBe(m.row_count);
		expect(m.files.slim_all.rows).toBe(m.row_count);
	});
});
