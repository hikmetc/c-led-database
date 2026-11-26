// Copy the web deploy set, and only the web deploy set, into static/data/.
//   build/parquet/**  build/analytes.json  build/interferents.json  build/stats.json
// plus meta/data_dictionary.json (column definitions shown in the row view).
// Never copies cled.sqlite, evidence*, slim/ JSON shards or any CSV.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repo = path.resolve(site, '..');
const src = path.resolve(process.env.CLED_DATA_SRC ?? path.join(repo, 'build'));
const dest = path.resolve(process.env.CLED_DATA_DEST ?? path.join(site, 'static', 'data'));

const manifestPath = path.join(src, 'parquet', 'manifest.json');
if (!fs.existsSync(manifestPath)) {
	console.error(
		`copy-data: ${manifestPath} not found.\n` +
			'Build the data layer first, from the repository root:\n' +
			'  pip install -r requirements.txt\n' +
			'  CLED_REQUIRE_PARQUET=1 CLED_DISTRIBUTION=1 python3 scripts/build_all.py'
	);
	process.exit(1);
}

fs.rmSync(dest, { recursive: true, force: true });
fs.mkdirSync(dest, { recursive: true });

let files = 0;
let bytes = 0;
function copy(from, to) {
	fs.mkdirSync(path.dirname(to), { recursive: true });
	fs.copyFileSync(from, to);
	files += 1;
	bytes += fs.statSync(to).size;
}

for (const name of ['analytes.json', 'interferents.json', 'stats.json']) {
	copy(path.join(src, name), path.join(dest, name));
}
(function walk(dir) {
	for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
		const p = path.join(dir, e.name);
		if (e.isDirectory()) walk(p);
		else if (e.name === 'manifest.json' || e.name.endsWith('.parquet'))
			copy(p, path.join(dest, 'parquet', path.relative(path.join(src, 'parquet'), p)));
	}
})(path.join(src, 'parquet'));

const dict = process.env.CLED_DICTIONARY ?? path.join(repo, 'meta', 'data_dictionary.json');
copy(dict, path.join(dest, 'data_dictionary.json'));

console.log(`copy-data: ${files} files, ${(bytes / 1e6).toFixed(2)} MB -> ${path.relative(site, dest)}`);
