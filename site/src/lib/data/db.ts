/**
 * One DuckDB-WASM instance for the whole session, created lazily (after first paint) in a
 * Web Worker. Single-threaded bundles only: GitHub Pages cannot send COOP/COEP headers.
 * Parquet files are registered by absolute URL so DuckDB reads only the row groups it needs
 * over HTTP range requests; if such a read fails the whole file is fetched instead.
 */
import { writable } from 'svelte/store';
import { base } from '$app/paths';

export type DbStatus = 'idle' | 'loading' | 'ready' | 'error';
export const dbStatus = writable<DbStatus>('idle');
/** Files that had to be downloaded whole because a range read failed. */
export const wholeFileFallbacks = writable<string[]>([]);

type Row = Record<string, unknown>;
interface Engine {
	run(sql: string, params: unknown[]): Promise<Row[]>;
	registerUrl(name: string, url: string): Promise<void>;
	registerBuffer(name: string, data: Uint8Array): Promise<void>;
}

let enginePromise: Promise<Engine> | null = null;
const registered = new Map<string, Promise<'url' | 'buffer'>>();

export function dataUrl(path: string): string {
	return new URL(`${base}/data/${path}`, location.origin).href;
}

function engine(): Promise<Engine> {
	if (!enginePromise) {
		dbStatus.set('loading');
		enginePromise = import('./engine')
			.then((m) => m.createEngine())
			.then((e) => {
				dbStatus.set('ready');
				return e;
			})
			.catch((err) => {
				dbStatus.set('error');
				enginePromise = null;
				registered.clear();
				throw err;
			});
	}
	return enginePromise;
}

/** Start loading DuckDB without waiting for it (called once the page has painted). */
export function warmUp(): void {
	engine().catch(() => {});
}

// One operation at a time: registrations and queries never interleave, so a file is never
// re-registered underneath a running query.
let tail: Promise<unknown> = Promise.resolve();
function serial<T>(job: () => Promise<T>): Promise<T> {
	const next = tail.then(job, job);
	tail = next.catch(() => {});
	return next;
}

function ensureRegistered(e: Engine, name: string): Promise<'url' | 'buffer'> {
	let p = registered.get(name);
	if (!p) {
		p = e.registerUrl(name, dataUrl(name)).then(() => 'url' as const);
		registered.set(name, p);
	}
	return p;
}

/** Download a file whole and register its bytes. Happens at most once per file. */
function fetchWhole(e: Engine, name: string): Promise<'url' | 'buffer'> {
	const p = (async () => {
		const res = await fetch(dataUrl(name));
		if (!res.ok) throw new Error(`Could not download ${name} (HTTP ${res.status})`);
		await e.registerBuffer(name, new Uint8Array(await res.arrayBuffer()));
		wholeFileFallbacks.update((l) => (l.includes(name) ? l : [...l, name]));
		return 'buffer' as const;
	})();
	registered.set(name, p);
	p.catch(() => registered.delete(name));
	return p;
}

/**
 * Run a query. `files` are the Parquet paths (relative to data/) the SQL reads with
 * read_parquet('<path>'). Values always travel as parameters, never inside the SQL text.
 */
export async function query<T = Row>(sql: string, params: unknown[] = [], files: string[] = []): Promise<T[]> {
	const e = await engine();
	return serial(async () => {
		const modes = await Promise.all(files.map((f) => ensureRegistered(e, f)));
		try {
			return (await e.run(sql, params)) as T[];
		} catch (err) {
			const viaUrl = files.filter((_, i) => modes[i] === 'url');
			if (!viaUrl.length) throw err;
			for (const f of viaUrl) await fetchWhole(e, f);
			return (await e.run(sql, params)) as T[];
		}
	});
}

/** SQL string literal for a file path taken from the manifest. */
export function lit(path: string): string {
	return `'${path.replace(/'/g, "''")}'`;
}
