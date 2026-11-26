// Loaded on demand only. The DuckDB-WASM bundles are served by this site, not by a CDN.
import * as duckdb from '@duckdb/duckdb-wasm';
import mvpWasm from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url';
import mvpWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url';
import ehWasm from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import ehWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';
import { base } from '$app/paths';

type Row = Record<string, unknown>;
const abs = (u: string) => new URL(u, location.href).href;

function plain(v: unknown): unknown {
	if (typeof v === 'bigint') return Number(v);
	return v;
}

export async function createEngine() {
	// No `coi` entry: the threaded build needs SharedArrayBuffer, which needs COOP/COEP.
	const bundle = await duckdb.selectBundle({
		mvp: { mainModule: abs(mvpWasm), mainWorker: abs(mvpWorker) },
		eh: { mainModule: abs(ehWasm), mainWorker: abs(ehWorker) }
	});
	const worker = new Worker(bundle.mainWorker!);
	const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
	await db.instantiate(bundle.mainModule);
	// Read Parquet over HTTP range requests (footer first, then only the row groups a query
	// needs). A full download stays allowed as the fallback for servers without range support.
	await db.open({ path: ':memory:', filesystem: { reliableHeadRequests: true, allowFullHTTPReads: true, forceFullHTTPReads: false } });
	const conn = await db.connect();
	// The Parquet reader is an extension. Load it from this site, never from a third party.
	const repo = new URL(`${base}/duckdb-ext`, location.origin).href.replace(/'/g, "''");
	await conn.query(`SET custom_extension_repository = '${repo}'`);

	return {
		async run(sql: string, params: unknown[]): Promise<Row[]> {
			let table;
			if (params.length) {
				const stmt = await conn.prepare(sql);
				try {
					table = await stmt.query(...params);
				} finally {
					await stmt.close();
				}
			} else {
				table = await conn.query(sql);
			}
			const names = table.schema.fields.map((f) => f.name);
			const out: Row[] = [];
			for (const r of table) {
				const o: Row = {};
				for (const n of names) o[n] = plain((r as Row)[n]);
				out.push(o);
			}
			return out;
		},
		async registerUrl(name: string, url: string) {
			await db.registerFileURL(name, url, duckdb.DuckDBDataProtocol.HTTP, false);
		},
		async registerBuffer(name: string, data: Uint8Array) {
			try {
				await db.dropFile(name);
			} catch {
				/* not registered yet */
			}
			await db.registerFileBuffer(name, data);
		}
	};
}
