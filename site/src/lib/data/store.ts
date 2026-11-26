/**
 * Reads the Parquet files of the web deploy set in the browser with a small pure-JavaScript
 * reader (no WebAssembly engine to download first), so the first chart needs only the data.
 *
 * Small files are fetched whole, in one request. Files above RANGE_MIN_BYTES are read over
 * HTTP range requests: the footer first, then only the columns and row groups that are needed.
 * If a range read fails, the whole file is fetched instead. Decoded tables are kept in memory,
 * so filters, sorting and charts never wait for the network again.
 */
import { writable } from 'svelte/store';
import { base } from '$app/paths';

export type Row = Record<string, unknown>;
/** Files that were downloaded whole because a range read failed. */
export const wholeFileFallbacks = writable<string[]>([]);

export const RANGE_MIN_BYTES = 4_000_000;
function rangeMinBytes(): number {
	const override = (globalThis as { __CLED_RANGE_MIN_BYTES?: unknown }).__CLED_RANGE_MIN_BYTES; // set by tests
	return typeof override === 'number' ? override : RANGE_MIN_BYTES;
}

export function dataUrl(path: string): string {
	return new URL(`${base}/data/${path}`, location.origin).href;
}

type AsyncBuffer = { byteLength: number; slice(start: number, end?: number): ArrayBuffer | Promise<ArrayBuffer> };
let libPromise: ReturnType<typeof loadLib> | null = null;
async function loadLib() {
	const [hp, fzstd] = await Promise.all([import('hyparquet'), import('fzstd')]);
	// the Parquet layer is zstd-compressed
	const compressors = { ZSTD: (input: Uint8Array) => fzstd.decompress(input) };
	return { hp, compressors };
}
function lib() {
	return (libPromise ??= loadLib().catch((e) => {
		libPromise = null;
		throw e;
	}));
}

const buffers = new Map<string, Promise<AsyncBuffer>>();
async function fetchWhole(path: string): Promise<AsyncBuffer> {
	const res = await fetch(dataUrl(path));
	if (!res.ok) throw new Error(`Could not download ${path} (HTTP ${res.status})`);
	return await res.arrayBuffer();
}
/** A handle on a file: its bytes when it is small, a range-request reader when it is large. */
function open(path: string, bytes: number | undefined): Promise<AsyncBuffer> {
	let p = buffers.get(path);
	if (!p) {
		p = (async () => {
			if (bytes === undefined || bytes < rangeMinBytes()) return fetchWhole(path);
			const { hp } = await lib();
			return hp.cachedAsyncBuffer(await hp.asyncBufferFromUrl({ url: dataUrl(path), byteLength: bytes }));
		})();
		buffers.set(path, p);
		p.catch(() => buffers.delete(path));
	}
	return p;
}

function clean(rows: Row[]): Row[] {
	// a missing value is null, never undefined and never zero
	for (const r of rows) for (const k in r) if (r[k] === undefined) r[k] = null;
	return rows;
}

async function withFallback<T>(path: string, bytes: number | undefined, job: (file: AsyncBuffer) => Promise<T>): Promise<T> {
	const file = await open(path, bytes);
	try {
		return await job(file);
	} catch (err) {
		if (file instanceof ArrayBuffer) throw err; // already the whole file: a real error
		const whole = fetchWhole(path);
		buffers.set(path, whole);
		whole.catch(() => buffers.delete(path));
		const result = await job(await whole);
		wholeFileFallbacks.update((l) => (l.includes(path) ? l : [...l, path]));
		return result;
	}
}

const tables = new Map<string, Promise<Row[]>>();
/** Every row of a file (optionally only some columns), decoded once and then kept. */
export function readTable<T = Row>(path: string, bytes?: number, columns?: string[]): Promise<T[]> {
	const key = columns ? `${path}|${columns.join(',')}` : path;
	let p = tables.get(key);
	if (!p) {
		p = (async () => {
			const { hp, compressors } = await lib();
			return withFallback(path, bytes, async (file) => clean(await hp.parquetReadObjects({ file, columns, compressors })));
		})();
		tables.set(key, p);
		p.catch(() => tables.delete(key));
	}
	return p as Promise<T[]>;
}

/**
 * One row of a file sorted by `column`. For a large file only the row group whose statistics
 * can hold the value is read; a small file is simply decoded once and searched.
 */
export async function readRow(path: string, bytes: number | undefined, column: string, value: string): Promise<Row | null> {
	if (tables.has(path) || bytes === undefined || bytes < rangeMinBytes()) {
		const rows = await readTable(path, bytes);
		return rows.find((r) => r[column] === value) ?? null;
	}
	const { hp, compressors } = await lib();
	return withFallback(path, bytes, async (file) => {
		const meta = await hp.parquetMetadataAsync(file);
		let start = 0;
		for (const group of meta.row_groups) {
			const n = Number(group.num_rows);
			const stats = group.columns.find((c) => c.meta_data?.path_in_schema.join('.') === column)?.meta_data?.statistics;
			const lo = stats?.min_value;
			const hi = stats?.max_value;
			const mayHold = typeof lo !== 'string' || typeof hi !== 'string' || (value >= lo && value <= hi);
			if (mayHold) {
				const rows = clean(await hp.parquetReadObjects({ file, metadata: meta, rowStart: start, rowEnd: start + n, compressors }));
				const hit = rows.find((r) => r[column] === value);
				if (hit) return hit;
			}
			start += n;
		}
		return null;
	});
}

/** Start loading the reader and a file without waiting (called as soon as a page mounts). */
export function warm(path: string, bytes?: number): void {
	readTable(path, bytes).catch(() => {});
}
