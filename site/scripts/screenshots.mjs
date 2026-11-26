// Screenshots of a running copy of the site, plus a log of every request it makes.
//   node scripts/screenshots.mjs <base-url> [out-dir]
// PW_CHANNEL=chrome uses an installed Chrome; HEADED=1 opens a visible window.
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const baseUrl = (process.argv[2] ?? 'http://localhost:4173/').replace(/\/?$/, '/');
const out = path.resolve(process.argv[3] ?? 'screenshots');
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ headless: !process.env.HEADED, ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) });
const requests = new Set();
const problems = [];

async function shot(name, route, { width = 1440, height = 900, dark = false, wait } = {}) {
	const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: dark ? 'dark' : 'light', deviceScaleFactor: 2 });
	const page = await ctx.newPage();
	page.on('request', (r) => requests.add(r.url()));
	page.on('console', (m) => m.type() === 'error' && problems.push(`${name}: console ${m.text()}`));
	page.on('pageerror', (e) => problems.push(`${name}: ${e.message}`));
	page.on('requestfailed', (r) => problems.push(`${name}: failed ${r.url()} ${r.failure()?.errorText}`));
	await page.goto(baseUrl + route, { waitUntil: 'networkidle' });
	if (wait) await page.waitForSelector(wait, { timeout: 45000 }).catch((e) => problems.push(`${name}: ${e.message.split('\n')[0]}`));
	await page.waitForTimeout(900);
	await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: !!process.env.FULL });
	await ctx.close();
}

const manifest = await (await fetch(baseUrl + 'data/parquet/manifest.json')).json();
const analyte = process.env.ANALYTE ?? Object.keys(manifest.files.slim)[0];
await shot('home-light', '', { wait: '[data-testid="matrix"][data-status="ready"]' });
await shot('home-dark', '', { dark: true, wait: '[data-testid="matrix"][data-status="ready"]' });
await shot('analyte-light', `analyte/${analyte}/`, { wait: '[data-testid="evidence-table"]' });
await shot('analyte-dark', `analyte/${analyte}/`, { dark: true, wait: '[data-testid="evidence-table"]' });
await shot('home-mobile', '', { width: 375, height: 812, wait: '[data-testid="matrix"][data-status="ready"]' });
await shot('analyte-mobile', `analyte/${analyte}/`, { width: 375, height: 812, wait: '[data-testid="evidence-table"]' });
await browser.close();

const origin = new URL(baseUrl).origin;
const list = [...requests].sort();
fs.writeFileSync(path.join(out, 'requests.txt'), list.join('\n') + '\n');
const thirdParty = list.filter((u) => !u.startsWith(origin) && !u.startsWith('data:') && !u.startsWith('blob:'));
const forbidden = list.filter((u) => /\.(pdf|sqlite|csv)(\?|$)/i.test(u) || /\/(evidence|slim)\/[^/]*\.json/.test(u) || /evidence_slim\.json/.test(u));
console.log(`requests: ${list.length}; third-party: ${thirdParty.length}; PDF/SQLite/CSV/JSON-shard: ${forbidden.length}`);
for (const u of [...thirdParty, ...forbidden]) console.log('  !', u);
for (const p of problems) console.log('  problem:', p);
console.log('screenshots in', out);
