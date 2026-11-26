<script lang="ts">
	import { base } from '$app/paths';
	import { PUBLIC_SITE_URL, REPO_URL } from '$lib/env';
	import Seo from '$lib/components/Seo.svelte';
	let { data } = $props();
</script>

<Seo title="How to cite" description="How to cite the C-LED database and the sources of its evidence rows." />
<div class="wrap page prose">
	<p class="eyebrow">Citation</p>
	<h1>How to cite</h1>

	<div class="todo">
		<strong>TODO.</strong> A formal citation for the database (authors, title, year, persistent identifier) has not been provided yet. This page will carry it once it exists. No DOI has been assigned to the database.
	</div>

	<h2>Until then</h2>
	<p>Refer to the database by its name, the version you used and where you obtained it:</p>
	<ul>
		<li>Name: C-LED Database (Clinical Laboratory Error Database)</li>
		{#if data.version}<li>Version: {data.version}{#if data.released} ({data.released}){/if}; see the <a href="{base}/changelog/">changelog</a></li>{/if}
		{#if PUBLIC_SITE_URL}<li>Website: <a href="{PUBLIC_SITE_URL}/">{PUBLIC_SITE_URL}/</a></li>{/if}
		{#if REPO_URL}<li>Repository: <a href={REPO_URL} rel="noopener">{REPO_URL}</a></li>{/if}
		<li>The date you accessed it</li>
	</ul>

	<h2>Cite the original studies</h2>
	<p>
		Every evidence row comes from a published source. When you rely on a specific result, cite that source as well: each row carries its citation, and a DOI or PubMed ID where one is recorded. Open a row and use <em>Copy citation</em>, or <em>Copy permalink</em> to point to the exact row.
	</p>
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
</style>
