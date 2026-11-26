// Put the DuckDB-WASM Parquet extension under static/duckdb-ext/ so the site serves it itself.
// Files are checksum-pinned in duckdb-extensions.json; a mismatch stops the build.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pin = JSON.parse(fs.readFileSync(path.join(site, 'duckdb-extensions.json'), 'utf8'));
const destRoot = path.resolve(process.env.CLED_EXT_DEST ?? path.join(site, 'static', 'duckdb-ext'));
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

for (const f of pin.files) {
	const dest = path.join(destRoot, pin.version, f.path);
	if (fs.existsSync(dest) && sha(fs.readFileSync(dest)) === f.sha256) continue;
	const url = `${pin.source}/${pin.version}/${f.path}`;
	const res = await fetch(url);
	if (!res.ok) throw new Error(`fetch-duckdb-ext: ${url} -> HTTP ${res.status}`);
	const buf = Buffer.from(await res.arrayBuffer());
	if (sha(buf) !== f.sha256) throw new Error(`fetch-duckdb-ext: checksum mismatch for ${url}; refusing to use it`);
	fs.mkdirSync(path.dirname(dest), { recursive: true });
	fs.writeFileSync(dest, buf);
	console.log(`fetch-duckdb-ext: ${f.path} (${(buf.length / 1e6).toFixed(2)} MB)`);
}
// drop extensions of an older pinned version
for (const d of fs.existsSync(destRoot) ? fs.readdirSync(destRoot) : []) if (d !== pin.version) fs.rmSync(path.join(destRoot, d), { recursive: true, force: true });
