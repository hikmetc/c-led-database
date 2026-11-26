import fs from 'node:fs';
import { describe, expect, it } from 'vitest';

// WCAG contrast of the design tokens in both themes: text 4.5:1, graphics 3:1.
const css = fs.readFileSync('src/app.css', 'utf8');
function block(selector: string): Record<string, string> {
	const start = css.indexOf(selector + ' {');
	const body = css.slice(start, css.indexOf('}', start));
	const out: Record<string, string> = {};
	for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2];
	return out;
}
const lum = (hex: string) => {
	const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
	return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const contrast = (a: string, b: string) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);

const themes = { light: block(':root'), dark: block(":root[data-theme='dark']") };

describe.each(Object.entries(themes))('%s theme contrast', (_name, t) => {
	it('has every token', () => {
		for (const k of ['bg', 'bg-2', 'text', 'text-2', 'accent', 'on-accent', 'link', 'exceeds', 'exceeds-text', 'within', 'up', 'down', 'control']) expect(t[k], k).toMatch(/^#/);
	});
	it.each(['text', 'text-2', 'link', 'exceeds-text'])('text token %s reaches 4.5:1 on both backgrounds', (k) => {
		expect(contrast(t[k], t.bg)).toBeGreaterThanOrEqual(4.5);
		expect(contrast(t[k], t['bg-2'])).toBeGreaterThanOrEqual(4.5);
	});
	it.each(['exceeds', 'within', 'up', 'down', 'control', 'accent'])('graphic token %s reaches 3:1 on both backgrounds', (k) => {
		expect(contrast(t[k], t.bg)).toBeGreaterThanOrEqual(3);
		expect(contrast(t[k], t['bg-2'])).toBeGreaterThanOrEqual(3);
	});
	it('button and matrix text reach 4.5:1 on their fills', () => {
		expect(contrast(t['on-accent'], t.accent)).toBeGreaterThanOrEqual(4.5);
		for (const i of [0, 1, 2, 3, 4]) expect(contrast(t[`m${i}-t`], t[`m${i}`]), `m${i}`).toBeGreaterThanOrEqual(4.5);
	});
});

it('the system-preference dark block matches the manual dark theme', () => {
	const start = css.indexOf(":root:not([data-theme='light']) {");
	const body = css.slice(start, css.indexOf('}', start));
	for (const [k, v] of Object.entries(themes.dark)) expect(body).toContain(`--${k}: ${v};`);
});
