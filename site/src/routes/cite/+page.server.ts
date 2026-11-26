import fs from 'node:fs';
import path from 'node:path';

export const load = () => {
	const md = fs.readFileSync(path.resolve(process.cwd(), '..', 'CHANGELOG.md'), 'utf8');
	const m = md.match(/^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})/m);
	return { version: m?.[1] ?? null, released: m?.[2] ?? null };
};
