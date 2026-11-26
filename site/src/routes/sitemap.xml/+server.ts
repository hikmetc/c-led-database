import { base } from '$app/paths';
import { validateManifest, analyteIds } from '$lib/manifest';
import type { Interferent } from '$lib/types';

export const prerender = true;
export const trailingSlash = 'never';

const STATIC = ['/', '/search/', '/about/', '/methods/', '/data-dictionary/', '/cite/', '/changelog/', '/downloads/'];

export const GET = async ({ fetch }) => {
	const site = (import.meta.env.VITE_SITE_URL ?? '').replace(/\/$/, '');
	const paths = [...STATIC];
	const man = validateManifest(await (await fetch(`${base}/data/parquet/manifest.json`)).json());
	if (man.ok) for (const id of analyteIds(man.manifest)) paths.push(`/analyte/${id}/`);
	const interferents: Interferent[] = await (await fetch(`${base}/data/interferents.json`)).json();
	const concepts = new Set<string>();
	for (const i of interferents) {
		if (!(i.evidence_rows > 0)) continue;
		paths.push(`/interferent/${i.interferent_id}/`);
		concepts.add(i.concept);
	}
	for (const c of concepts) paths.push(`/concept/${c}/`);
	const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
	const body =
		'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
		paths.map((p) => `  <url><loc>${esc((site || base) + p)}</loc></url>`).join('\n') +
		'\n</urlset>\n';
	return new Response(body, { headers: { 'content-type': 'application/xml' } });
};
