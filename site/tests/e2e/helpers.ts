import fs from 'node:fs';
import { expect, type Page } from '@playwright/test';

export const DATA = process.env.CLED_E2E_DATA ?? 'static/data';
export const readJson = (rel: string, dir = DATA) => JSON.parse(fs.readFileSync(`${dir}/${rel}`, 'utf8'));
export const manifest = () => readJson('parquet/manifest.json');
export const analyteIds = () => Object.keys(manifest().files.slim) as string[];
export const int = (n: number) => new Intl.NumberFormat('en-US').format(n);

/** The explorer has loaded its rows from DuckDB. */
export async function explorerReady(page: Page) {
	await expect(page.getByTestId('evidence-table')).toBeVisible({ timeout: 45_000 });
	await expect(page.getByTestId('result-summary')).toContainText('evidence row');
}

/** "177 of 181 numeric results exceed ..." -> [177, 181] */
export async function exceedCounts(page: Page): Promise<[number, number]> {
	const text = (await page.getByTestId('result-summary').textContent()) ?? '';
	const m = text.replace(/,/g, '').match(/(\d+) of (\d+) numeric results/);
	if (!m) throw new Error(`no counts in: ${text}`);
	return [Number(m[1]), Number(m[2])];
}

export async function totalRows(page: Page): Promise<number> {
	const text = (await page.getByTestId('result-summary').textContent()) ?? '';
	return Number(text.replace(/,/g, '').match(/^(\d+) evidence/)![1]);
}
