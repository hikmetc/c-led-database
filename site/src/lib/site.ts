/** Lookups derived from the small registry files. Nothing here names a specific analyte. */
import type { Analyte, Interferent, Manifest, SiteData } from './types';
import { analyteIds } from './manifest';
import { humanize } from './format';

export interface AnalyteView extends Analyte {
	rows: number;
	interferents: Interferent[];
}
export interface ConceptView {
	concept: string;
	label: string;
	rows: number;
	/** analyte_id -> interferents of that analyte under this concept */
	byAnalyte: Map<string, Interferent[]>;
}
export interface SiteIndex {
	manifest: Manifest;
	analytes: AnalyteView[];
	analyteById: Map<string, AnalyteView>;
	interferentById: Map<string, Interferent & { analyte_id: string }>;
	concepts: ConceptView[];
	conceptById: Map<string, ConceptView>;
}

/**
 * The manifest decides which analytes exist; analytes.json and interferents.json describe
 * them. An analyte in the manifest without a registry record still gets a page.
 */
export function buildIndex(data: SiteData): SiteIndex | null {
	const manifest = data.manifest;
	if (!manifest) return null;
	const byId = new Map(data.analytes.map((a) => [a.analyte_id, a]));
	const analytes: AnalyteView[] = [];
	const folderToId = new Map<string, string>();
	for (const id of analyteIds(manifest)) {
		const file = manifest.files.slim[id];
		const rec = byId.get(id);
		const a: AnalyteView = {
			analyte_id: id,
			analyte_folder: rec?.analyte_folder ?? file.analyte_folder ?? id,
			component: rec?.component ?? id,
			system: rec?.system ?? '',
			kind_of_property: rec?.kind_of_property ?? '',
			unit: rec?.unit ?? '',
			aps_percent: rec?.aps_percent ?? NaN,
			aps_type: rec?.aps_type ?? '',
			aps_note: rec?.aps_note ?? '',
			synonyms: rec?.synonyms ?? '',
			interferent_count: rec?.interferent_count ?? 0,
			evidence_tables: rec?.evidence_tables ?? 0,
			evidence_rows: rec?.evidence_rows ?? file.rows,
			rows: file.rows,
			interferents: []
		};
		analytes.push(a);
		folderToId.set(a.analyte_folder, id);
	}
	const analyteById = new Map(analytes.map((a) => [a.analyte_id, a]));
	const interferentById: SiteIndex['interferentById'] = new Map();
	const conceptById = new Map<string, ConceptView>();
	for (const i of data.interferents) {
		if (!(i.evidence_rows > 0)) continue; // a catch-all cause no row uses has no page
		const analyteId = folderToId.get(i.analyte_folder);
		if (!analyteId) continue;
		analyteById.get(analyteId)!.interferents.push(i);
		interferentById.set(i.interferent_id, { ...i, analyte_id: analyteId });
		let c = conceptById.get(i.concept);
		if (!c) {
			c = { concept: i.concept, label: humanize(i.concept), rows: 0, byAnalyte: new Map() };
			conceptById.set(i.concept, c);
		}
		c.rows += i.evidence_rows;
		const list = c.byAnalyte.get(analyteId) ?? [];
		list.push(i);
		c.byAnalyte.set(analyteId, list);
	}
	for (const a of analytes) a.interferents.sort((x, y) => y.evidence_rows - x.evidence_rows);
	const concepts = [...conceptById.values()].sort(
		(a, b) => b.byAnalyte.size - a.byAnalyte.size || b.rows - a.rows || a.concept.localeCompare(b.concept)
	);
	return { manifest, analytes, analyteById, interferentById, concepts, conceptById };
}

export function analyteTitle(a: { component: string; system: string }): string {
	return a.system ? `${a.component} (${a.system})` : a.component;
}
