<script lang="ts">
	import { base } from '$app/paths';
	import { REPO_URL } from '$lib/env';
	const links = [
		{ href: '/about/', label: 'About' },
		{ href: '/methods/', label: 'Methods' },
		{ href: '/data-dictionary/', label: 'Data dictionary' },
		{ href: '/cite/', label: 'How to cite' },
		{ href: '/changelog/', label: 'Changelog' },
		{ href: '/downloads/', label: 'Downloads' }
	];
</script>

<footer>
	<div class="wrap">
		<p class="caption">
			C-LED, the Clinical Laboratory Error Database. Every evidence row is traceable to a published source by citation, DOI or PubMed ID.
			Full-text articles are not distributed. This site sets no cookies and uses no analytics.
		</p>
		<ul>
			{#each links as l (l.href)}<li><a href="{base}{l.href}">{l.label}</a></li>{/each}
			{#if REPO_URL}<li><a href={REPO_URL} rel="noopener">GitHub</a></li>{/if}
		</ul>
	</div>
</footer>

<style>
	footer {
		border-top: 1px solid var(--hairline);
		background: var(--bg-2);
		padding: 32px 0 48px;
	}
	ul {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 24px;
		list-style: none;
		margin: 16px 0 0;
		padding: 0;
		font-size: 0.8125rem;
	}
	p {
		max-width: 46rem;
		margin: 0;
	}
</style>
