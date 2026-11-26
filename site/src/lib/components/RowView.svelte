<script lang="ts">
	import { base } from '$app/paths';
	import { getSite } from '$lib/context';
	import { rowDetail, type RowDetail } from '$lib/data/queries';
	import { judge } from '$lib/aps';
	import { analyteIdOfRow } from '$lib/rowid';
	import * as f from '$lib/format';
	import StateBlock from './StateBlock.svelte';

	let { rowId, aps, heading = 'h1' }: { rowId: string; aps?: number; heading?: 'h1' | 'h2' } = $props();
	const site = getSite();
	let result = $state<RowDetail | null>(null);
	let status = $state<'loading' | 'ready' | 'missing' | 'error'>('loading');
	let error = $state('');
	let copied = $state('');
	let attempt = $state(0);

	$effect(() => {
		const id = rowId;
		void attempt;
		const manifest = site.data.manifest;
		if (!manifest) return;
		status = 'loading';
		let cancelled = false;
		rowDetail(manifest, id)
			.then((r) => {
				if (cancelled) return;
				result = r;
				status = r ? 'ready' : 'missing';
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

	const analyte = $derived(site.index?.analyteById.get(analyteIdOfRow(rowId) ?? '') ?? null);
	const slim = $derived(result?.slim ?? null);
	const detail = $derived(result?.detail ?? null);
	const interferent = $derived(slim ? site.index?.interferentById.get(String(slim.interferent_id)) : null);
	const pctChange = $derived(typeof slim?.pct_change === 'number' ? (slim.pct_change as number) : null);
	const defaultAps = $derived(typeof slim?.aps_percent === 'number' ? (slim.aps_percent as number) : (analyte?.aps_percent ?? NaN));
	const activeAps = $derived(aps ?? defaultAps);
	const verdict = $derived(judge(pctChange, activeAps));
	const doi = $derived(slim?.doi ? String(slim.doi) : null);
	const pmid = $derived(slim?.pmid ? String(slim.pmid) : null);
	const permalink = $derived(`${base}/row/${rowId}/`);

	function citationText(): string {
		if (!detail) return '';
		const parts: string[] = [];
		const ref = [detail.full_reference_from_pdf, detail.reference_full_resolved, detail.citation].find((v) => !f.isNotReported(v));
		if (ref) parts.push(String(ref));
		if (doi) parts.push(f.doiUrl(doi));
		else if (pmid) parts.push(`PMID ${pmid}`);
		return parts.join(' ');
	}
	async function copy(what: 'citation' | 'permalink') {
		const text = what === 'citation' ? citationText() : new URL(permalink, location.origin).href;
		try {
			await navigator.clipboard.writeText(text);
			copied = what === 'citation' ? 'Citation copied' : 'Link copied';
		} catch {
			copied = 'Copying is not available in this browser';
		}
		setTimeout(() => (copied = ''), 2500);
	}
</script>

<article class="row" data-testid="row-view">
	<p class="eyebrow">Evidence row</p>
	<svelte:element this={heading} class="title">
		{interferent?.interferent_canonical ?? 'Evidence row'}
		{#if analyte}<span class="on">on {analyte.component}</span>{/if}
	</svelte:element>
	<p class="mono id" data-testid="row-id">{rowId}</p>

	{#if !site.data.manifest}
		<StateBlock kind="error" message="The data manifest could not be read." />
	{:else if status === 'loading'}
		<StateBlock kind="loading" message="Loading the evidence row" height={420} />
	{:else if status === 'error'}
		<StateBlock kind="error" message={error} onretry={() => (attempt += 1)} />
	{:else if status === 'missing'}
		<StateBlock kind="empty" message="No evidence row has this identifier. Row identifiers change if rows are inserted in the middle of a source table." />
	{:else if detail}
		<div class="facts fade-in">
			<div>
				<span class="caption">Change</span>
				<strong class:muted={pctChange === null}>{f.pct(pctChange)}</strong>
			</div>
			<div>
				<span class="caption">Direction</span>
				<strong>{f.directionLabel(slim?.direction as string)}</strong>
			</div>
			<div>
				<span class="caption">Against APS {Number.isFinite(activeAps) ? f.aps(activeAps) : ''}{aps !== undefined && aps !== defaultAps ? ' (custom)' : ''}</span>
				{#if verdict === 'not_computable'}
					<strong class="muted">Not computable</strong>
					<span class="caption">Recorded verdict: {f.verdictLabel(slim?.aps_verdict as string)}</span>
				{:else}
					<strong class:ex={verdict === 'exceeds'}>{verdict === 'exceeds' ? '◆ Exceeds' : '○ Within'}</strong>
				{/if}
			</div>
		</div>

		<div class="actions">
			{#if doi}<a class="btn" href={f.doiUrl(doi)} rel="noopener" data-testid="doi-link">DOI <span class="mono">{doi}</span></a>{/if}
			{#if pmid}<a class="btn" href={f.pmidUrl(pmid)} rel="noopener" data-testid="pmid-link">PubMed <span class="mono">{pmid}</span></a>{/if}
			{#if !doi && !pmid}<span class="caption">No DOI or PubMed ID is recorded for this source; see the full reference below.</span>{/if}
			<button class="btn" type="button" onclick={() => copy('citation')}>Copy citation</button>
			<button class="btn" type="button" onclick={() => copy('permalink')}>Copy permalink</button>
			<span class="caption" role="status" aria-live="polite">{copied}</span>
		</div>
		<p class="caption links">
			{#if analyte}<a href="{base}/analyte/{analyte.analyte_id}/">{analyte.component}</a>{/if}
			{#if interferent} · <a href="{base}/interferent/{interferent.interferent_id}/">{interferent.interferent_canonical}</a> · <a href="{base}/concept/{interferent.concept}/">{f.humanize(interferent.concept)} across analytes</a>{/if}
			{#if heading === 'h2'} · <a href={permalink}>Open as a page</a>{/if}
		</p>

		<svelte:element this={heading === 'h1' ? 'h2' : 'h3'} class="sub h3">Source columns, verbatim</svelte:element>
		<dl>
			{#each site.data.dictionary as d (d.parquet_column)}
				{@const v = detail[d.parquet_column]}
				<div>
					<dt title={d.definition}><span>{d.column}</span></dt>
					<dd class:muted={f.isNotReported(v)}>{v === null || v === undefined || v === '' ? 'not reported in the information source' : v}</dd>
				</div>
			{/each}
			{#if !f.isNotReported(detail.reference_full_resolved) && detail.reference_full_resolved !== detail.full_reference_from_pdf}
				<div>
					<dt title="Full reference used by the build when the source table does not carry one."><span>Full reference (resolved by the build)</span></dt>
					<dd>{detail.reference_full_resolved}</dd>
				</div>
			{/if}
		</dl>
		{#if slim}
			<p class="caption">
				Source table <span class="mono">{slim.source_file}</span>, row {slim.source_row}. Reference status: {f.refStatusLabel(slim.reference_status as string)}{slim.reference_origin === 'enriched' ? ' (identifier recovered outside the source table)' : ''}.
			</p>
		{/if}
	{/if}
</article>

<style>
	.title {
		font-size: clamp(1.5rem, 1.3rem + 1vw, 2rem);
		margin-bottom: 8px;
	}
	.on {
		color: var(--text-2);
		font-weight: 400;
	}
	.id {
		color: var(--text-2);
		overflow-wrap: anywhere;
		margin-bottom: 24px;
	}
	.facts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: 16px;
		padding: 20px;
		background: var(--bg-2);
		border-radius: var(--radius);
		margin-bottom: 20px;
	}
	.facts div {
		display: grid;
		gap: 2px;
	}
	.facts strong {
		font-size: 1.3125rem;
		font-weight: 600;
	}
	.ex {
		color: var(--exceeds-text);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		margin-bottom: 12px;
	}
	.actions .mono {
		overflow-wrap: anywhere;
	}
	.links {
		margin-bottom: 28px;
	}
	.sub {
		margin-bottom: 8px;
	}
	dl {
		margin: 0 0 16px;
	}
	dl > div {
		display: grid;
		grid-template-columns: minmax(140px, 220px) 1fr;
		gap: 4px 20px;
		padding: 10px 0;
		border-top: 1px solid var(--hairline);
		font-size: 0.9375rem;
	}
	dt {
		color: var(--text-2);
	}
	dt span {
		border-bottom: 1px dotted var(--control);
		cursor: help;
	}
	dd {
		margin: 0;
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}
	@media (max-width: 560px) {
		dl > div {
			grid-template-columns: 1fr;
		}
	}
</style>
