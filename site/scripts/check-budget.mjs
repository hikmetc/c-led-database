// Checks on the built site (default: build/), run in CI before deployment:
//   - initial JavaScript of a page (entry + preloaded chunks, gzip) is at most 150 kB;
//     the DuckDB-WASM worker and .wasm files load later and are not part of it
//   - the whole site stays under GitHub Pages' limits: 900 MB in total, 100 MB per file
//   - only the web deploy set is published under data/
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const root = path.resolve(process.argv[2] ?? 'build');
const JS_BUDGET = 150_000;
const SITE_LIMIT = 900e6;
const FILE_LIMIT = 100e6;
const problems = [];

const files = [];
(function walk(dir) {
	for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
		const p = path.join(dir, e.name);
		if (e.isDirectory()) walk(p);
		else files.push({ path: p, rel: path.relative(root, p).split(path.sep).join('/'), size: fs.statSync(p).size });
	}
})(root);

const total = files.reduce((s, f) => s + f.size, 0);
if (total > SITE_LIMIT) problems.push(`site is ${(total / 1e6).toFixed(0)} MB; the limit is 900 MB`);
for (const f of files) if (f.size > FILE_LIMIT) problems.push(`${f.rel} is ${(f.size / 1e6).toFixed(0)} MB; the limit is 100 MB per file`);

const allowed = [/^data\/parquet\/manifest\.json$/, /^data\/parquet\/slim_all\.parquet$/, /^data\/parquet\/(slim|detail)\/[^/]+\.parquet$/, /^data\/(analytes|interferents|stats|data_dictionary)\.json$/];
for (const f of files) {
	if (f.rel.startsWith('data/') && !allowed.some((re) => re.test(f.rel))) problems.push(`${f.rel} is not part of the web deploy set`);
	if (/\.(pdf|sqlite|csv|xlsx|numbers)$/i.test(f.rel)) problems.push(`${f.rel} must never be published`);
}

function initialJs(htmlRel) {
	const html = fs.readFileSync(path.join(root, htmlRel), 'utf8');
	const dir = path.posix.dirname(htmlRel);
	const refs = new Set();
	for (const m of html.matchAll(/(?:href|import\()\s*=?\s*["'(]+([^"')]+\.js)["')]/g)) refs.add(m[1]);
	let bytes = 0;
	for (const r of refs) {
		const rel = r.startsWith('/') ? r.replace(/^\/[^_]*(?=_app\/)/, '') : path.posix.normalize(path.posix.join(dir, r));
		const file = path.join(root, rel);
		if (fs.existsSync(file)) bytes += zlib.gzipSync(fs.readFileSync(file)).length;
	}
	return { bytes, n: refs.size };
}
const pages = ['index.html'];
const analyteDir = path.join(root, 'analyte');
if (fs.existsSync(analyteDir)) {
	const first = fs.readdirSync(analyteDir).sort()[0];
	if (first) pages.push(`analyte/${first}/index.html`);
}
for (const p of pages) {
	const { bytes, n } = initialJs(p);
	console.log(`initial JS of ${p}: ${(bytes / 1000).toFixed(1)} kB gzip in ${n} files (budget ${JS_BUDGET / 1000} kB)`);
	if (n === 0) problems.push(`${p}: found no scripts to measure`);
	if (bytes > JS_BUDGET) problems.push(`${p}: initial JS is ${(bytes / 1000).toFixed(1)} kB gzip, over the 150 kB budget`);
}
const data = files.filter((f) => f.rel.startsWith('data/'));
console.log(`site: ${files.length} files, ${(total / 1e6).toFixed(1)} MB; web deploy set under data/: ${data.length} files, ${(data.reduce((s, f) => s + f.size, 0) / 1e6).toFixed(2)} MB; largest file ${(Math.max(...files.map((f) => f.size)) / 1e6).toFixed(1)} MB`);
for (const p of problems) console.error('FAIL:', p);
process.exit(problems.length ? 1 : 0);
