import { defineConfig, devices } from '@playwright/test';

// End-to-end tests run against the built site (`vite preview`) with the real data.
// PW_CHANNEL=chrome uses an installed Chrome instead of Playwright's own Chromium.
const channel = process.env.PW_CHANNEL;
const BASE = process.env.BASE_PATH ?? '';

export default defineConfig({
	testDir: 'tests/e2e',
	timeout: 60_000,
	expect: { timeout: 20_000 },
	fullyParallel: true,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? [['github'], ['list']] : 'list',
	use: { ...devices['Desktop Chrome'], ...(channel ? { channel } : {}), trace: 'retain-on-failure' },
	projects: [
		{ name: 'site', testIgnore: /growth\.spec\.ts/, use: { baseURL: `http://localhost:4173${BASE}/` } },
		{ name: 'growth', testMatch: /growth\.spec\.ts/, use: { baseURL: 'http://localhost:4174/' } }
	],
	webServer: [
		{ command: 'npm run preview -- --port 4173 --strictPort', url: `http://localhost:4173${BASE}/`, reuseExistingServer: !process.env.CI, timeout: 60_000 },
		{ command: 'node scripts/serve-static.mjs .variants/growth/build 4174', url: 'http://localhost:4174/', reuseExistingServer: !process.env.CI, timeout: 60_000 }
	]
});
