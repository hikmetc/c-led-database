<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { afterNavigate, goto } from '$app/navigation';
	import { getSite } from '$lib/context';
	import { getSearcher, highlightParts, type Suggestion } from '$lib/search';
	import { searchRows, SEARCH_PAGE, type SearchHit } from '$lib/data/queries';
	import { drawerRow } from '$lib/stores';
	import * as f from '$lib/format';
	import Seo from '$lib/components/Seo.svelte';
	import SearchBox from '$lib/components/SearchBox.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';

	const site = getSite();
	let q = $state('');
	let input = $state('');
	let pageNo = $state(0);
	let citations = $state(false);
	let entities = $state<Suggestion[]>([]);
	let hits = $state<SearchHit[]>([]);
	let total = $state(0);
	let status = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	let error = $state('');
	let attempt = $state(0);

	function readUrl() {
		const p = new URL(location.href).searchParams;
		q = (p.get('q') ?? '').trim();
		input = q;
		pageNo = Math.max(0, (Number(p.get('page')) || 1) - 1);
		citations = p.get('cite') === '1';
	}
	onMount(readUrl);
	afterNavigate(readUrl);

	function go(next: { q?: string; page?: number; cite?: boolean }) {
		const p = new URLSearchParams();
		const query = next.q ?? q;
		if (query) p.set('q', query);
		const pg = next.page ?? 0;
		if (pg > 0) p.set('page', String(pg + 1));
		if (next.cite ?? citations) p.set('cite', '1');
		goto(`${base}/search/?${p}`, { keepFocus: true, noScroll: next.page === undefined });
	}

	$effect(() => {
		const query = q;
		if (!site.index || !query) {
			entities = [];
			return;
		}
		getSearcher(site.index).then((s) => {
			if (query === q) entities = s(query, 60);
		});
	});
	$effect(() => {
		const manifest = site.data.manifest;
		const query = q;
		const pg = pageNo;
		const cite = citations;
		void attempt;
		if (!manifest || query.length < 2) {
			hits = [];
			total = 0;
			status = 'idle';
			return;
		}
		let cancelled = false;
		status = 'loading';
		searchRows(manifest, query, pg, cite)
			.then((r) => {
				if (cancelled) return;
				hits = r.rows;
				total = r.total;
				status = 'ready';
			})
			.catch((e) => {
				if (cancelled) return;
				error = e?.message ?? String(e);
				status = 'error';
			});
		return () => {
			cancelled = true;
		};
	});

	const kinds = ['Analyte', 'Concept', 'Interferent'] as const;
	const plural = { Analyte: 'Analytes', Concept: 'Concepts', Interferent: 'Interferents' };
	const pages = $derived(Math.max(1, Math.ceil(total / SEARCH_PAGE)));
	const live = $derived(!q ? '' : status === 'ready' ? `${entities.length} entries and ${f.int(total)} evidence rows match "${q}".` : status === 'loading' ? 'Searching…' : '');
</script>

<Seo title={q ? `Search: ${q}` : 'Search'} description="Search the EFLM Laboratory Error Database for analytes, interferents, concepts and evidence rows." />

{#snippet mark(text: string | null)}
	{#each highlightParts(f.isNotReported(text) ? f.NOT_REPORTED : (text ?? ''), q) as part, i (i)}{#if part.hit}<mark>{part.text}</mark>{:else}{part.text}{/if}{/each}
{/snippet}

<div class="wrap page">
	<h1>Search</h1>
	<SearchBox large bind:value={input} onsubmit={(v) => go({ q: v, page: 0 })} />
	<p class="live caption" role="status" aria-live="polite" data-testid="search-summary">{live}</p>

	{#if q}
		{#each kinds as kind (kind)}
			{@const list = entities.filter((e) => e.kind === kind)}
			{#if list.length}
				<section aria-labelledby="h-{kind}" data-testid="group-{kind.toLowerCase()}">
					<h2 id="h-{kind}">{plural[kind]} <span class="muted">{list.length}</span></h2>
					<ul class="ents">
						{#each list as e (e.id)}
							<li><a href="{base}{e.href}">{@render mark(e.title)}</a>{#if e.subtitle}<span class="caption"> · {e.subtitle}</span>{/if}</li>
						{/each}
					</ul>
				</section>
			{/if}
		{/each}

		<section aria-labelledby="h-rows" data-testid="group-rows">
			<h2 id="h-rows">Evidence rows {#if status === 'ready'}<span class="muted">{f.int(total)}</span>{/if}</h2>
			<label class="cite caption">
				<input type="checkbox" checked={citations} onchange={(e) => go({ cite: e.currentTarget.checked, page: 0 })} />
				Also search citations and full references (reads the detail files of every analyte)
			</label>
			{#if q.length < 2}
				<StateBlock kind="empty" message="Type at least two characters to search the evidence rows." />
			{:else if status === 'error'}
				<StateBlock kind="error" message={error} onretry={() => (attempt += 1)} />
			{:else if status === 'loading' || status === 'idle'}
				<StateBlock kind="loading" message="Searching evidence rows" height={280} />
			{:else if !hits.length}
				<StateBlock kind="empty" message="No evidence row mentions this in its interferent, platform, analyzer, sample type, DOI or PubMed ID." />
			{:else}
				<ol class="hits">
					{#each hits as r (r.row_id)}
						<li>
							<button type="button" class="hit" onclick={() => drawerRow.set({ id: r.row_id })}>
								<span class="t">{@render mark(r.interferent_canonical)} <span class="muted">on {site.index?.analyteById.get(r.analyte_id)?.component ?? r.analyte_id}</span></span>
								<span class="d">{@render mark(r.interferent_verbatim)}</span>
								<span class="d">{@render mark(r.platform)} · {@render mark(r.analyzer)}</span>
								{#if r.citation}<span class="d">{@render mark(r.citation)}</span>{/if}
								<span class="m caption">
									<span>{f.pct(r.pct_change)}</span>
									<span>{f.directionLabel(r.direction)}</span>
									{#if r.doi}<span>DOI {@render mark(r.doi)}</span>{/if}
									{#if r.pmid}<span>PMID {@render mark(r.pmid)}</span>{/if}
								</span>
							</button>
						</li>
					{/each}
				</ol>
				{#if pages > 1}
					<nav class="pager" aria-label="Result pages">
						<button class="btn" type="button" disabled={pageNo === 0} onclick={() => go({ page: pageNo - 1 })}>Previous</button>
						<span class="caption">Page {pageNo + 1} of {f.int(pages)}</span>
						<button class="btn" type="button" disabled={pageNo >= pages - 1} onclick={() => go({ page: pageNo + 1 })}>Next</button>
					</nav>
				{/if}
			{/if}
		</section>
	{:else}
		<p class="lede hint">Search by analyte, interferent, concept, platform, analyzer, DOI or PubMed ID.</p>
	{/if}
</div>

<style>
	.page {
		padding-top: clamp(40px, 6vw, 72px);
		padding-bottom: var(--section);
	}
	h1 {
		margin-bottom: 24px;
	}
	.live {
		min-height: 1.4em;
		margin: 12px 0 0;
	}
	section {
		margin-top: 48px;
	}
	h2 {
		font-size: 1.3125rem;
		margin-bottom: 12px;
	}
	h2 .muted {
		font-weight: 400;
	}
	.ents {
		list-style: none;
		margin: 0;
		padding: 0;
		columns: 2 320px;
		column-gap: 32px;
	}
	.ents li {
		padding: 5px 0;
		break-inside: avoid;
	}
	.cite {
		display: flex;
		gap: 8px;
		align-items: center;
		margin-bottom: 16px;
	}
	.cite input {
		accent-color: var(--accent);
	}
	.hits {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: 1px solid var(--hairline);
	}
	.hit {
		display: grid;
		gap: 3px;
		width: 100%;
		padding: 14px 8px;
		border: 0;
		border-bottom: 1px solid var(--hairline);
		background: none;
		text-align: left;
		cursor: pointer;
	}
	.hit:hover {
		background: var(--bg-2);
	}
	.t {
		font-weight: 600;
	}
	.t .muted {
		font-weight: 400;
	}
	.d {
		font-size: 0.875rem;
		color: var(--text-2);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.m {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 16px;
		margin-top: 2px;
	}
	mark {
		background: none;
		color: inherit;
		font-weight: 700;
		box-shadow: inset 0 -2px 0 var(--accent);
	}
	.pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 16px;
		margin-top: 24px;
	}
	.hint {
		margin-top: 32px;
	}
</style>
