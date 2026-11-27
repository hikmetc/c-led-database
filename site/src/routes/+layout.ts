import { dataHref } from '$lib/data/href';
import { validateManifest } from '$lib/manifest';
import type { SiteData } from '$lib/types';

export const prerender = true;
export const trailingSlash = 'always';

/**
 * The small registry files of the web deploy set. Prerendered pages carry them inline, so a
 * page is readable before any JavaScript has loaded.
 */
export const load = async ({ fetch }): Promise<SiteData> => {
	const get = async (path: string) => {
		const res = await fetch(dataHref(path));
		if (!res.ok) throw new Error(`Could not load ${path} (HTTP ${res.status})`);
		return res.json();
	};
	const [rawManifest, analytes, interferents, stats, dictionary] = await Promise.all([
		get('parquet/manifest.json'),
		get('analytes.json'),
		get('interferents.json'),
		get('stats.json'),
		get('data_dictionary.json')
	]);
	const checked = validateManifest(rawManifest);
	return {
		manifest: checked.ok ? checked.manifest : null,
		manifestError: checked.ok ? null : checked.error,
		analytes,
		interferents,
		stats,
		dictionary
	};
};
