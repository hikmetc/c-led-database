import { base } from '$app/paths';
import { version } from '$app/environment';

/**
 * Address of a file of the web deploy set. The build's version is part of it, so a browser
 * never mixes a page of one deployment with cached data of an earlier one: after every
 * deployment the data has a new address. (GitHub Pages lets browsers cache a file for ten
 * minutes; without this, a returning visitor could see new pages with old data.)
 */
export function dataHref(path: string): string {
	return `${base}/data/${path}?v=${encodeURIComponent(version)}`;
}
