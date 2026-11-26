export const prerender = true;
export const trailingSlash = 'never';

export const GET = () => {
	const site = (import.meta.env.VITE_SITE_URL ?? '').replace(/\/$/, '');
	// a Sitemap line must be an absolute URL, which is only known for a deployed build
	const sitemap = site ? `\nSitemap: ${site}/sitemap.xml\n` : '';
	return new Response(`User-agent: *\nAllow: /\n${sitemap}`, { headers: { 'content-type': 'text/plain' } });
};
