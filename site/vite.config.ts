import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit()],
	// DuckDB-WASM ships prebuilt workers and .wasm files; they are referenced by URL and
	// served from this site (no CDN), so nothing here needs pre-bundling.
	optimizeDeps: { exclude: ['@duckdb/duckdb-wasm'] },
	build: {
		target: 'es2022',
		chunkSizeWarningLimit: 900,
		// fewer, larger chunks: dozens of tiny requests are slower than a handful
		rollupOptions: { output: { experimentalMinChunkSize: 24_000 } }
	},
	test: { include: ['tests/unit/**/*.test.ts'], environment: 'node' }
});
