import fs from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';

// Rendered at build time from the repository's CHANGELOG.md; no Markdown code reaches the browser.
export const load = () => {
	const file = path.resolve(process.cwd(), '..', 'CHANGELOG.md');
	const md = fs.readFileSync(file, 'utf8').replace(/^# .*\n/, '');
	return { html: marked.parse(md, { async: false, gfm: true }) as string };
};
