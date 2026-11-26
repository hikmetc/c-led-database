/** Instant typeahead over analytes, interferents and concepts (a few hundred records). */
import type { SiteIndex } from './site';

export interface Suggestion {
	id: string;
	kind: 'Analyte' | 'Interferent' | 'Concept';
	title: string;
	subtitle: string;
	href: string;
}

export function searchDocuments(index: SiteIndex): (Suggestion & { text: string })[] {
	const docs: (Suggestion & { text: string })[] = [];
	for (const a of index.analytes)
		docs.push({
			id: `a:${a.analyte_id}`, kind: 'Analyte', title: a.component, subtitle: a.system,
			href: `/analyte/${a.analyte_id}/`, text: `${a.synonyms} ${a.system} ${a.analyte_id}`
		});
	for (const c of index.concepts)
		docs.push({
			id: `c:${c.concept}`, kind: 'Concept', title: c.label,
			subtitle: `${c.byAnalyte.size} ${c.byAnalyte.size === 1 ? 'analyte' : 'analytes'}`,
			href: `/concept/${c.concept}/`, text: c.concept.replace(/_/g, ' ')
		});
	for (const i of index.interferentById.values())
		docs.push({
			id: `i:${i.interferent_id}`, kind: 'Interferent', title: i.interferent_canonical,
			subtitle: index.analyteById.get(i.analyte_id)?.component ?? '',
			href: `/interferent/${i.interferent_id}/`, text: `${i.concept.replace(/_/g, ' ')} ${i.interferent_key.replace(/_/g, ' ')}`
		});
	return docs;
}

type Searcher = (q: string, limit?: number) => Suggestion[];
let cache: { index: SiteIndex; searcher: Promise<Searcher> } | null = null;

export function getSearcher(index: SiteIndex): Promise<Searcher> {
	if (cache?.index === index) return cache.searcher;
	const searcher = import('minisearch').then(({ default: MiniSearch }) => {
		const docs = searchDocuments(index);
		const byId = new Map(docs.map((d) => [d.id, d]));
		const mini = new MiniSearch({ fields: ['title', 'text', 'subtitle'], storeFields: [] });
		mini.addAll(docs);
		const rank = { Analyte: 0, Concept: 1, Interferent: 2 } as const;
		return (q: string, limit = 50) => {
			const hits = mini.search(q, { prefix: true, fuzzy: 0.15, boost: { title: 3, text: 1.5 }, combineWith: 'AND' });
			return hits
				.map((h) => ({ doc: byId.get(h.id as string)!, score: h.score }))
				.sort((a, b) => rank[a.doc.kind] - rank[b.doc.kind] || b.score - a.score)
				.slice(0, limit)
				.map(({ doc }) => ({ id: doc.id, kind: doc.kind, title: doc.title, subtitle: doc.subtitle, href: doc.href }));
		};
	});
	cache = { index, searcher };
	return searcher;
}

/** Split text around case-insensitive matches of the query words, for highlighting. */
export function highlightParts(text: string, q: string): { text: string; hit: boolean }[] {
	const words = q.trim().split(/\s+/).filter((w) => w.length > 1).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
	if (!words.length || !text) return [{ text, hit: false }];
	const re = new RegExp(`(${words.join('|')})`, 'gi');
	return text
		.split(re)
		.map((p, i) => ({ text: p, hit: i % 2 === 1 }))
		.filter((p) => p.text !== '');
}
