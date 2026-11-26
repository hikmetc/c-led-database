// Build the site a second time against data that contains one extra, fake analyte.
// No file under src/ is touched: the growth test proves a new analyte needs no code change.
//   output: .variants/growth/build   (served by scripts/serve-static.mjs in the e2e run)
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repo = path.resolve(site, '..');
const variant = path.join(site, '.variants', 'growth');
const stat = path.join(variant, 'static');
const venvPy = path.join(repo, '.venv', 'bin', 'python3');
const python = process.env.PYTHON ?? (fs.existsSync(venvPy) ? venvPy : 'python3');
const run = (cmd, args, env = {}) => execFileSync(cmd, args, { cwd: site, stdio: 'inherit', env: { ...process.env, ...env } });

fs.rmSync(variant, { recursive: true, force: true });
fs.mkdirSync(stat, { recursive: true });
for (const e of fs.readdirSync(path.join(site, 'static'))) {
	if (e === 'data') continue;
	fs.cpSync(path.join(site, 'static', e), path.join(stat, e), { recursive: true });
}
const fixture = path.join(variant, 'fixture');
run(python, ['tests/fixtures/make_growth_data.py', path.join(repo, 'build'), fixture]);
run('node', ['scripts/copy-data.mjs'], { CLED_DATA_SRC: fixture, CLED_DATA_DEST: path.join(stat, 'data') });
run('npx', ['vite', 'build'], { CLED_VARIANT: 'growth', BASE_PATH: '' });
