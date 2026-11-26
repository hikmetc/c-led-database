import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit()],
	build: {
		target: 'es2022',
		chunkSizeWarningLimit: 900,
		// fewer, larger chunks: dozens of tiny requests are slower than a handful
		rollupOptions: { output: { experimentalMinChunkSize: 24_000 } }
	},
	test: { include: ['tests/unit/**/*.test.ts'], environment: 'node' }
});
