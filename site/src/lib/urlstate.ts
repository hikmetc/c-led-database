/** Filter and view state kept in the URL so every view can be shared. */
export const FILTER_KEYS = ['interferent', 'concept', 'platform', 'analyzer', 'sample', 'direction', 'ref'] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];
export type Filters = Record<FilterKey, string[]>;

export interface ViewState {
	/** null = the analyte's default APS */
	aps: number | null;
	scale: 'symlog' | 'linear';
	filters: Filters;
}

export function emptyFilters(): Filters {
	return { interferent: [], concept: [], platform: [], analyzer: [], sample: [], direction: [], ref: [] };
}

export function defaultState(): ViewState {
	return { aps: null, scale: 'symlog', filters: emptyFilters() };
}

export function decodeState(params: URLSearchParams): ViewState {
	const state = defaultState();
	const aps = params.get('aps');
	if (aps !== null && aps.trim() !== '') {
		const n = Number(aps);
		if (Number.isFinite(n) && n > 0) state.aps = n;
	}
	if (params.get('scale') === 'linear') state.scale = 'linear';
	for (const key of FILTER_KEYS) {
		state.filters[key] = [...new Set(params.getAll(key).filter((v) => v !== ''))];
	}
	return state;
}

/** Writes only what differs from the defaults; keeps unrelated parameters of `base`. */
export function encodeState(state: ViewState, base?: URLSearchParams): URLSearchParams {
	const out = new URLSearchParams(base);
	for (const key of ['aps', 'scale', ...FILTER_KEYS]) out.delete(key);
	if (state.aps !== null) out.set('aps', String(state.aps));
	if (state.scale === 'linear') out.set('scale', 'linear');
	for (const key of FILTER_KEYS) for (const v of state.filters[key]) out.append(key, v);
	return out;
}

export function activeFilterCount(filters: Filters): number {
	return FILTER_KEYS.reduce((n, k) => n + filters[k].length, 0);
}
