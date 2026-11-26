import { expect, test } from '@playwright/test';

// Runs against a build of the unchanged site code whose data holds one extra, fake analyte
// (tests/fixtures/make_growth_data.py). Adding an analyte must need no code change.
const NAME = 'Zzfixturate';
const dir = '.variants/growth/static/data';
import { readJson, int } from './helpers';

test('a new analyte appears in the navigation, the home cards and the matrix', async ({ page }) => {
	const real = readJson('parquet/manifest.json');
	const grown = readJson('parquet/manifest.json', dir);
	expect(Object.keys(grown.files.slim).length).toBe(Object.keys(real.files.slim).length + 1);

	await page.goto('');
	await page.getByRole('navigation', { name: 'Main' }).locator('summary').click();
	await expect(page.getByTestId('analyte-menu').getByRole('link', { name: NAME })).toBeVisible();
	await expect(page.getByTestId('analyte-cards').getByRole('heading', { name: NAME })).toBeVisible();
	await expect(page.getByTestId('kpis')).toContainText(int(grown.row_count));

	const matrix = page.getByTestId('matrix');
	await expect(matrix).toHaveAttribute('data-status', 'ready', { timeout: 45_000 });
	await expect(matrix.locator('thead th.col')).toHaveCount(Object.keys(grown.files.slim).length);
	await expect(matrix.locator('thead').getByRole('link', { name: NAME })).toBeVisible();
	// its own new concept got a row, and it joined the shared hemolysis row
	await expect(matrix.getByRole('rowheader', { name: 'Fixture concept' })).toBeVisible();
	await expect(matrix.getByRole('link', { name: new RegExp(`^Hemolysis on ${NAME}: 20 evidence rows; \\d+ of \\d+ numeric`) })).toBeVisible();
});

test('the new analyte has a working, prerendered page with the right numbers', async ({ page }) => {
	const res = await page.goto('analyte/zz/');
	expect(res!.status()).toBe(200); // prerendered, not the SPA fallback
	await expect(page.getByRole('heading', { level: 1, name: NAME })).toBeVisible();
	await expect(page.getByTestId('analyte-rows')).toHaveText('40');
	await expect(page.getByTestId('default-aps')).toHaveText('10 %');
	await expect(page.getByTestId('evidence-table')).toBeVisible({ timeout: 45_000 });
	await expect(page.getByTestId('result-summary')).toContainText('40 evidence rows');
	await expect(page.getByTestId('result-summary')).toContainText('of 32 numeric results'); // 8 of 40 rows carry no value
	const rowId = await page.locator('.idbtn').first().getAttribute('title');
	expect(rowId).toMatch(/^zz\.fixture_table\.\d{4}$/);
	await page.locator('.idbtn').first().click();
	await expect(page.getByTestId('drawer').locator('dl')).toBeVisible({ timeout: 45_000 });
});

test('its interferent and concept pages exist too', async ({ page }) => {
	expect((await page.goto('interferent/zz.fixture_cause/'))!.status()).toBe(200);
	await expect(page.getByRole('heading', { level: 1, name: 'Fixture-only cause' })).toBeVisible();
	expect((await page.goto('concept/fixture_concept/'))!.status()).toBe(200);
	await expect(page.getByRole('heading', { level: 1, name: 'Fixture concept' })).toBeVisible();
});
