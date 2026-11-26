/** Absolute public URL of the deployed site (no trailing slash); empty in local builds. */
export const PUBLIC_SITE_URL: string = (import.meta.env.VITE_SITE_URL ?? '').replace(/\/$/, '');
export const REPO_URL: string = import.meta.env.VITE_REPO_URL ?? '';

const SITE_PATH = PUBLIC_SITE_URL ? new URL(PUBLIC_SITE_URL).pathname.replace(/\/$/, '') : '';
/**
 * A page path without the deployment base path (`/analyte/k/`). `base` from $app/paths is
 * relative while prerendering, so the absolute base is taken from the site URL instead.
 */
export function sitePath(pathname: string, runtimeBase = ''): string {
	for (const b of [SITE_PATH, runtimeBase]) if (b && b.startsWith('/') && pathname.startsWith(b + '/')) return pathname.slice(b.length);
	return pathname;
}
