import { getContext, setContext } from 'svelte';
import type { SiteIndex } from './site';
import type { SiteData } from './types';

const KEY = Symbol('cled');
export interface SiteContext {
	readonly data: SiteData;
	readonly index: SiteIndex | null;
}
export function setSite(ctx: SiteContext) {
	setContext(KEY, ctx);
}
export function getSite(): SiteContext {
	return getContext<SiteContext>(KEY);
}
