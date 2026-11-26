import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import fs from 'node:fs';

// CLED_VARIANT builds the same code against a different copy of the data (used by the
// growth test, which adds a fake analyte to the data and changes no code).
const variant = process.env.CLED_VARIANT;
const root = variant ? `.variants/${variant}/` : '';
const assets = `${root}static`;

/** Every page that can be known at build time, derived from the data files only. */
function entries() {
	const out = ['*'];
	const dir = `${assets}/data`;
	if (!fs.existsSync(`${dir}/parquet/manifest.json`)) return out;
	const read = (f) => JSON.parse(fs.readFileSync(`${dir}/${f}`, 'utf8'));
	const manifest = read('parquet/manifest.json');
	for (const id of Object.keys(manifest.files?.slim ?? {})) out.push(`/analyte/${id}/`);
	const concepts = new Set();
	for (const i of read('interferents.json')) {
		if (!(i.evidence_rows > 0)) continue;
		out.push(`/interferent/${i.interferent_id}/`);
		concepts.add(i.concept);
	}
	for (const c of concepts) out.push(`/concept/${c}/`);
	return out;
}

/** @type {import('@sveltejs/kit').Config} */
export default {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({ pages: `${root}build`, assets: `${root}build`, fallback: '404.html', strict: true }),
		outDir: `${root}.svelte-kit`,
		files: { assets },
		paths: { base: process.env.BASE_PATH ?? '' },
		// small stylesheets go into the HTML, so no stylesheet request blocks first paint
		inlineStyleThreshold: 60000,
		prerender: { entries: entries(), handleHttpError: 'fail', handleMissingId: 'warn' }
	}
};
