import fs from 'node:fs';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { analyteIds, exceedCounts, explorerReady, int, manifest, readJson, totalRows } from './helpers';

const ids = analyteIds();
const first = ids[0];

test('home renders the KPIs and the concept x analyte matrix', async ({ page }) => {
	const stats = readJson('stats.json');
	const interferents = readJson('interferents.json').filter((i: any) => i.evidence_rows > 0);
	await page.goto('');
	await expect(page.getByRole('heading', { level: 1, name: 'C-LED' })).toBeVisible();
	const kpis = page.getByTestId('kpis');
	await expect(kpis).toContainText(int(stats.generated_rows));
	await expect(kpis).toContainText(int(interferents.length));
	await expect(kpis).toContainText(int(stats.references));
	const matrix = page.getByTestId('matrix');
	await expect(matrix).toHaveAttribute('data-status', 'ready', { timeout: 45_000 });
	const pairs = new Set(interferents.map((i: any) => `${i.concept}|${i.analyte_folder}`));
	await expect(matrix.locator('a[data-pos]')).toHaveCount(pairs.size);
	await expect(matrix.locator('thead th.col')).toHaveCount(ids.length);
	// a filled cell carries a share once DuckDB has answered, and never a fake zero for "no numeric results"
	await expect(matrix.locator('a[data-pos] .s').first()).toHaveText(/^(\d+%|–)$/);
	await expect(page.getByTestId('analyte-cards').locator('li')).toHaveCount(ids.length);
});

for (const id of ids) {
	test(`analyte ${id}: page works and its numbers equal the manifest`, async ({ page }) => {
		const rows = manifest().files.slim[id].rows;
		await page.goto(`analyte/${id}/`);
		await expect(page.getByTestId('analyte-rows')).toHaveText(int(rows));
		await explorerReady(page);
		expect(await totalRows(page)).toBe(rows);
		await expect(page.getByRole('table', { name: 'Evidence rows' })).toHaveAttribute('aria-rowcount', String(rows + 1));
		const [, plottable] = await exceedCounts(page);
		const stats = readJson('stats.json');
		expect(plottable).toBe(stats.plottable_by_analyte[manifest().files.slim[id].analyte_folder]);
	});
}

test('changing the APS changes the exceed counts and the URL', async ({ page }) => {
	await page.goto(`analyte/${first}/`);
	await explorerReady(page);
	await expect(page.getByTestId('aps-state')).toContainText('Default APS');
	const [before, plottable] = await exceedCounts(page);
	const input = page.getByTestId('aps-input');
	await input.fill('1000');
	await input.press('Enter');
	await expect(page).toHaveURL(/[?&]aps=1000\b/);
	await expect(page.getByTestId('aps-state')).toContainText('Custom');
	await expect.poll(async () => (await exceedCounts(page))[0]).toBeLessThan(before);
	expect((await exceedCounts(page))[1]).toBe(plottable); // the APS never changes what is plottable
	// the URL is shareable: a fresh load restores the same state
	const url = page.url();
	await page.goto(url);
	await explorerReady(page);
	await expect(page.getByTestId('aps-input')).toHaveValue('1000');
	await page.getByRole('button', { name: 'Reset' }).click();
	await expect(page).not.toHaveURL(/aps=/);
	await expect.poll(async () => (await exceedCounts(page))[0]).toBe(before);
});

test('rows without a numeric value are listed as "Not reported", never as zero', async ({ page }) => {
	await page.goto(`analyte/${first}/`);
	await explorerReady(page);
	const [, plottable] = await exceedCounts(page);
	const all = await totalRows(page);
	test.skip(all === plottable, 'every row of this analyte is plottable');
	await page.getByTestId('only-not-plottable').click();
	const table = page.getByRole('table', { name: 'Evidence rows' });
	await expect(table).toHaveAttribute('aria-rowcount', String(all - plottable + 1));
	const cells = table.locator('.c-pct_change');
	for (const text of await cells.allTextContents()) expect(text.trim()).toBe('Not reported');
	await expect(table.locator('.c-verdict').first()).toHaveText('Not computable');
});

test('every plottable row is drawn in both scales; clipped values are flagged, not dropped', async ({ page }) => {
	const summary = readJson('stats.json').pct_change_summary;
	const folderOf = (id: string) => manifest().files.slim[id].analyte_folder;
	// the analyte with the most extreme value, chosen from the data
	const id = [...ids].sort((a, b) => (summary[folderOf(b)]?.max ?? 0) - (summary[folderOf(a)]?.max ?? 0))[0];
	await page.goto(`analyte/${id}/`);
	await explorerReady(page);
	const [, plottable] = await exceedCounts(page);
	const marks = page.locator('.plot svg g[aria-label="dot"] :is(circle, path)');
	await expect(marks).toHaveCount(plottable);
	await page.getByRole('button', { name: 'Linear, clipped' }).click();
	await expect(page).toHaveURL(/scale=linear/);
	await expect(marks).toHaveCount(plottable);
	await expect(page.getByTestId('beyond-note')).toContainText(/\d+ values? beyond axis/);
});

test('a row permalink opens the right detail row with DOI and PubMed links', async ({ page }) => {
	// Which analytes hold rows with a DOI or with a PubMed ID only is a property of the data,
	// so the rows are looked up through the site itself.
	async function firstRowWith(ref: 'doi' | 'pmid', link: 'DOI' | 'PMID') {
		for (const id of ids) {
			await page.goto(`analyte/${id}/?ref=${ref}`);
			await expect(page.getByTestId('evidence-table').or(page.locator('div.state'))).toBeVisible({ timeout: 45_000 });
			if (!(await page.getByTestId('evidence-table').isVisible())) continue;
			const row = page.locator('[role="row"]').filter({ has: page.getByRole('link', { name: link }) }).first();
			const rowId = (await row.locator('.idbtn').getAttribute('title'))!;
			expect(rowId.startsWith(`${id}.`)).toBe(true);
			return { rowId, href: (await row.getByRole('link', { name: link }).getAttribute('href'))! };
		}
		throw new Error(`no analyte has a row with reference status ${ref}`);
	}
	const pm = await firstRowWith('pmid', 'PMID');
	expect(pm.href).toMatch(/^https:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/\d+\/$/);
	await page.goto(`row/${pm.rowId}/`);
	await expect(page.getByTestId('row-view').getByTestId('pmid-link')).toHaveAttribute('href', pm.href, { timeout: 45_000 });

	const { rowId, href: doiHref } = await firstRowWith('doi', 'DOI');
	expect(doiHref).toMatch(/^https:\/\/doi\.org\/10\./);
	await page.goto(`row/${rowId}/`);
	const view = page.getByTestId('row-view');
	await expect(view.getByTestId('row-id')).toHaveText(rowId);
	await expect(view.getByTestId('doi-link')).toHaveAttribute('href', doiHref, { timeout: 45_000 });
	// every data-dictionary column is shown, in order, under its dictionary name
	const dictionary = readJson('data_dictionary.json');
	await expect(view.locator('dl dt')).toHaveCount(dictionary.length, { timeout: 15_000 }).catch(async () => {
		expect(await view.locator('dl dt').count()).toBe(dictionary.length + 1); // plus the resolved reference
	});
	expect((await view.locator('dl dt').allTextContents()).slice(0, dictionary.length).map((t) => t.trim())).toEqual(dictionary.map((d: any) => d.column));
});

test('an unknown row id says so instead of showing a wrong row', async ({ page }) => {
	await page.goto(`row/${first}.no_such_table.9999/`);
	await expect(page.getByText('No evidence row has this identifier')).toBeVisible({ timeout: 45_000 });
});

test('search finds "hemolysis" from the home page', async ({ page }) => {
	await page.goto('');
	const box = page.getByRole('combobox', { name: 'Search the database' });
	await box.fill('hemolysis');
	await expect(page.getByRole('option').first()).toBeVisible();
	await box.press('Enter');
	await expect(page).toHaveURL(/search\/\?q=hemolysis/);
	await expect(page.getByTestId('group-concept')).toContainText('Hemolysis');
	await expect(page.getByTestId('group-interferent').locator('li').first()).toBeVisible();
	await expect(page.getByTestId('group-rows').locator('.hit').first()).toBeVisible({ timeout: 45_000 });
	await expect(page.getByTestId('group-rows').locator('mark').first()).toHaveText(/hemolysis/i);
	await expect(page.getByTestId('search-summary')).toContainText('evidence rows match');
	// rows are paginated
	await page.getByRole('button', { name: 'Next' }).click();
	await expect(page).toHaveURL(/page=2/);
	await expect(page.getByText(/Page 2 of/)).toBeVisible();
});

test('the matrix and the drawer work with the keyboard alone', async ({ page }) => {
	await page.goto('');
	const matrix = page.getByTestId('matrix');
	await expect(matrix).toHaveAttribute('data-status', 'ready', { timeout: 45_000 });
	// one tab stop for the whole grid
	await expect(matrix.locator('a[data-pos][tabindex="0"]')).toHaveCount(1);
	await matrix.locator('a[data-pos][tabindex="0"]').focus();
	const start = await page.evaluate(() => (document.activeElement as HTMLElement).dataset.pos);
	await page.keyboard.press('ArrowDown');
	const down = await page.evaluate(() => (document.activeElement as HTMLElement).dataset.pos);
	expect(down).not.toBe(start);
	expect(down!.split(':')[1]).toBe(start!.split(':')[1]); // same column
	await page.keyboard.press('ArrowUp');
	expect(await page.evaluate(() => (document.activeElement as HTMLElement).dataset.pos)).toBe(start);
	await expect(page.locator(':focus .tip')).toBeVisible(); // the tooltip shows on focus
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(/\/(interferent|concept)\//);

	await page.goto(`analyte/${first}/`);
	await explorerReady(page);
	const opener = page.locator('.idbtn').first();
	await opener.focus();
	await page.keyboard.press('Enter');
	const drawer = page.getByTestId('drawer');
	await expect(drawer).toBeVisible();
	await expect(drawer.getByTestId('row-id')).toBeVisible();
	for (let i = 0; i < 12; i++) {
		await page.keyboard.press('Tab');
		expect(await page.evaluate(() => !!document.activeElement?.closest('dialog') || document.activeElement === document.body)).toBe(true); // focus stays trapped
	}
	await page.keyboard.press('Escape');
	await expect(drawer).toBeHidden();
	await expect(opener).toBeFocused();
});

test('the filtered selection downloads as CSV', async ({ page }) => {
	await page.goto(`analyte/${first}/?direction=up`);
	await explorerReady(page);
	const n = await totalRows(page);
	const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('download-csv').click()]);
	const text = fs.readFileSync((await download.path())!, 'utf8');
	const lines = text.trimEnd().split('\r\n');
	expect(lines[0].split(',')).toEqual(expect.arrayContaining(['row_id', 'pct_change', 'active_aps_percent', 'verdict_at_active_aps']));
	expect(text.match(/(^|\r\n)[a-z0-9]+\.[^,\r\n]+\.\d{4},/g)?.length).toBe(n);
});

test('a filter narrows the rows, is announced, and lives in the URL', async ({ page }) => {
	await page.goto(`analyte/${first}/`);
	await explorerReady(page);
	const all = await totalRows(page);
	await page.getByTestId('filter-direction').locator('summary').click();
	await page.getByTestId('filter-direction').getByRole('checkbox').first().check();
	await expect(page).toHaveURL(/direction=/);
	await expect.poll(() => totalRows(page)).toBeLessThan(all);
	await expect(page.getByTestId('result-summary')).toHaveAttribute('aria-live', 'polite');
	await page.getByRole('button', { name: 'Clear all' }).click();
	await expect.poll(() => totalRows(page)).toBe(all);
});

test('if range requests fail, the whole file is fetched and the page still works', async ({ page }) => {
	let ranged = 0;
	await page.route('**/data/parquet/**/*.parquet', (route) => {
		if (route.request().headers()['range']) {
			ranged += 1;
			return route.fulfill({ status: 500, body: 'range not supported' });
		}
		return route.continue();
	});
	await page.goto(`analyte/${first}/`);
	await explorerReady(page);
	expect(await totalRows(page)).toBe(manifest().files.slim[first].rows);
	expect(ranged).toBeGreaterThan(0);
});

test('an unknown schema_version shows an error banner instead of data', async ({ page }) => {
	await page.route('**/data/parquet/manifest.json', async (route) => {
		const res = await route.fetch();
		await route.fulfill({ response: res, json: { ...(await res.json()), schema_version: '9.0' } });
	});
	// row permalinks are rendered in the browser, so they read the manifest at run time
	await page.goto(`row/${first}.any.0001/`);
	await expect(page.getByRole('alert').filter({ hasText: 'schema version 9.0' })).toBeVisible();
	await expect(page.getByTestId('row-view').locator('dl')).toHaveCount(0);
});

test('the site requests nothing outside the web deploy set, and nothing from third parties', async ({ page, baseURL }) => {
	const urls = new Set<string>();
	page.on('request', (r) => urls.add(r.url()));
	await page.goto('');
	await expect(page.getByTestId('matrix')).toHaveAttribute('data-status', 'ready', { timeout: 45_000 });
	await page.goto(`analyte/${first}/`);
	await explorerReady(page);
	await page.locator('.idbtn').first().click();
	await expect(page.getByTestId('drawer').locator('dl')).toBeVisible({ timeout: 45_000 });
	await page.goto('search/?q=serum&cite=1');
	await expect(page.getByTestId('group-rows').locator('.hit').first()).toBeVisible({ timeout: 45_000 });

	const root = new URL(baseURL!);
	const allowedData = [/^data\/parquet\/manifest\.json$/, /^data\/parquet\/slim_all\.parquet$/, /^data\/parquet\/(slim|detail)\/[^/]+\.parquet$/, /^data\/(analytes|interferents|stats|data_dictionary)\.json$/];
	const offenders: string[] = [];
	let parquet = 0;
	for (const u of urls) {
		if (u.startsWith('data:') || u.startsWith('blob:')) continue;
		const url = new URL(u);
		if (url.origin !== root.origin || !url.pathname.startsWith(root.pathname)) {
			offenders.push(u);
			continue;
		}
		const rel = url.pathname.slice(root.pathname.length);
		if (/\.(pdf|sqlite|csv|xlsx)$/i.test(rel)) offenders.push(u);
		if (rel.startsWith('data/')) {
			if (!allowedData.some((re) => re.test(rel))) offenders.push(u);
			if (rel.endsWith('.parquet')) parquet += 1;
		}
	}
	expect(offenders).toEqual([]);
	expect(parquet).toBeGreaterThan(0);
});

const AXE_PAGES: [string, string][] = [
	['home', ''],
	['analyte', `analyte/${first}/`],
	['search', 'search/?q=hemolysis'],
	['about', 'about/'],
	['methods', 'methods/'],
	['data dictionary', 'data-dictionary/'],
	['downloads', 'downloads/'],
	['cite', 'cite/'],
	['changelog', 'changelog/']
];
for (const scheme of ['light', 'dark'] as const) {
	for (const [name, route] of AXE_PAGES) {
		test(`axe: ${name} has no violations (${scheme})`, async ({ page }) => {
			await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
			await page.goto(route);
			if (name === 'home') await expect(page.getByTestId('matrix')).toHaveAttribute('data-status', 'ready', { timeout: 45_000 });
			if (name === 'analyte') await explorerReady(page);
			if (name === 'search') await expect(page.getByTestId('group-rows').locator('.hit').first()).toBeVisible({ timeout: 45_000 });
			const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
			expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 4).join(' | ')}`)).toEqual([]);
		});
	}
}

test('axe: interferent, concept, row page and the open drawer have no violations', async ({ page }) => {
	const interferent = readJson('interferents.json').find((i: any) => i.evidence_rows > 20);
	const check = async (label: string) => {
		const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
		expect(results.violations.map((v) => `${label} ${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 4).join(' | ')}`)).toEqual([]);
	};
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await page.goto(`interferent/${interferent.interferent_id}/`);
	await explorerReady(page);
	await expect(page.getByTestId('concept-link')).toBeVisible();
	await check('interferent');
	const rowId = (await page.locator('.idbtn').first().getAttribute('title'))!;
	await page.locator('.idbtn').first().click();
	await expect(page.getByTestId('drawer').locator('dl')).toBeVisible({ timeout: 45_000 });
	await check('drawer');
	await page.goto(`concept/${interferent.concept}/`);
	await expect(page.locator('.plot svg, .state').first()).toBeVisible({ timeout: 45_000 });
	await check('concept');
	await page.goto(`row/${rowId}/`);
	await expect(page.getByTestId('row-view').locator('dl')).toBeVisible({ timeout: 45_000 });
	await check('row');
});

test('at 375 px nothing overflows sideways and the table becomes cards', async ({ page }) => {
	await page.setViewportSize({ width: 375, height: 812 });
	for (const route of ['', `analyte/${first}/`, 'methods/', 'downloads/']) {
		await page.goto(route);
		if (route.startsWith('analyte')) {
			await explorerReady(page);
			await expect(page.locator('.scroller.cards')).toBeVisible();
		}
		expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), route).toBeLessThanOrEqual(0);
	}
});

test('unknown pages show the custom 404 with search', async ({ page }) => {
	await page.goto('analyte/does-not-exist/');
	await expect(page.getByRole('heading', { level: 1 })).toContainText('not in the database');
	await expect(page.getByRole('combobox', { name: 'Search the database' })).toBeVisible();
});

test('the theme toggle switches theme and survives a reload', async ({ page }) => {
	await page.goto('about/');
	await page.getByTestId('theme-toggle').click();
	const theme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
	expect(['light', 'dark']).toContain(theme);
	await page.reload();
	expect(await page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBe(theme);
});
