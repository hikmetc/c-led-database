import fs from 'node:fs';
import path from 'node:path';

export const load = () => {
	const md = fs.readFileSync(path.resolve(process.cwd(), '..', 'CHANGELOG.md'), 'utf8');
	const m = md.match(/^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})/m);
	// DOIs issued by Zenodo for archived releases; the file is absent until one exists
	const zenodoPath = path.resolve(process.cwd(), '..', 'meta', 'zenodo.json');
	const zenodo = fs.existsSync(zenodoPath) ? JSON.parse(fs.readFileSync(zenodoPath, 'utf8')) : {};
	const version = m?.[1] ?? null;
	return {
		version,
		released: m?.[2] ?? null,
		conceptDoi: (zenodo.concept_doi as string | undefined) ?? null,
		versionDoi: (version && (zenodo.versions?.[version] as string | undefined)) || null
	};
};
