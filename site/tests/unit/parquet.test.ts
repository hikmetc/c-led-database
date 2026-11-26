import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import { parquetMetadataAsync, parquetReadObjects } from 'hyparquet';
import { decompress } from 'fzstd';

// The real Parquet layer, decoded the way the site decodes it.
const dir = 'static/data';
const present = fs.existsSync(`${dir}/parquet/manifest.json`);
const compressors = { ZSTD: (input: Uint8Array) => decompress(input) };
const load = (rel: string) => {
	const b = fs.readFileSync(`${dir}/${rel}`);
	return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};

describe.skipIf(!present)('reading the Parquet layer', () => {
	const manifest = present ? JSON.parse(fs.readFileSync(`${dir}/parquet/manifest.json`, 'utf8')) : null;

	it('every slim file decodes to the row count the manifest gives', async () => {
		let total = 0;
		for (const [id, f] of Object.entries<any>(manifest.files.slim)) {
			const rows = await parquetReadObjects({ file: load(f.path), compressors });
			expect(rows.length, id).toBe(f.rows);
			expect(rows.every((r) => r.analyte_id === id)).toBe(true);
			total += rows.length;
		}
		expect(total).toBe(manifest.row_count);
	});

	it('a missing pct_change is null and such a row is never plottable', async () => {
		const rows = await parquetReadObjects({ file: load(manifest.files.slim_all.path), compressors });
		expect(rows.length).toBe(manifest.row_count);
		const missing = rows.filter((r) => r.pct_change === null || r.pct_change === undefined);
		expect(missing.length).toBeGreaterThan(0);
		expect(missing.every((r) => r.plottable === false)).toBe(true);
		expect(rows.filter((r) => typeof r.pct_change === 'number').every((r) => r.plottable === true && Number.isFinite(r.pct_change))).toBe(true);
		expect(rows.some((r) => r.pct_change === 0)).toBe(true); // a real zero stays a value
	});

	it('detail files are sorted by row_id with statistics, so one row needs one row group', async () => {
		const [id, f] = Object.entries<any>(manifest.files.detail).sort((a: any, b: any) => b[1].rows - a[1].rows)[0];
		const file = load(f.path);
		const meta = await parquetMetadataAsync(file);
		const all = await parquetReadObjects({ file, columns: ['row_id'], compressors });
		const wanted = all[all.length - 1].row_id as string;
		let start = 0;
		let found = 0;
		for (const g of meta.row_groups) {
			const n = Number(g.num_rows);
			const st = g.columns.find((c) => c.meta_data?.path_in_schema.join('.') === 'row_id')!.meta_data!.statistics!;
			expect(typeof st.min_value, id).toBe('string');
			if (wanted >= (st.min_value as string) && wanted <= (st.max_value as string)) {
				const rows = await parquetReadObjects({ file, metadata: meta, rowStart: start, rowEnd: start + n, compressors });
				if (rows.some((r) => r.row_id === wanted)) found += 1;
			}
			start += n;
		}
		expect(found).toBe(1);
	});
});
