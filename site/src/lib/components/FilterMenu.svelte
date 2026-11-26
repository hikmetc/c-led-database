<script lang="ts">
	import * as f from '$lib/format';

	export interface Option {
		value: string;
		label: string;
		n: number;
	}
	let { label, options, selected, onchange }: { label: string; options: Option[]; selected: string[]; onchange: (values: string[]) => void } = $props();
	const LIMIT = 80;
	let root = $state<HTMLDetailsElement | undefined>();
	let q = $state('');
	const matches = $derived.by(() => {
		const needle = q.trim().toLowerCase();
		const list = needle ? options.filter((o) => o.label.toLowerCase().includes(needle)) : options;
		// chosen values stay visible so they can always be unticked
		const chosen = list.filter((o) => selected.includes(o.value));
		const rest = list.filter((o) => !selected.includes(o.value));
		return { shown: [...chosen, ...rest].slice(0, LIMIT), total: list.length };
	});

	function toggle(v: string) {
		onchange(selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v]);
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && root?.open) {
			e.stopPropagation();
			root.open = false;
			root.querySelector('summary')?.focus();
		}
	}
	function onDocClick(e: MouseEvent) {
		if (root?.open && !root.contains(e.target as Node)) root.open = false;
	}
</script>

<svelte:document onclick={onDocClick} />

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<details bind:this={root} onkeydown={onKey} class:on={selected.length > 0} data-testid="filter-{label.toLowerCase().replace(/\W+/g, '-')}">
	<summary>{label}{#if selected.length}<span class="count">{selected.length}</span>{/if}</summary>
	<div class="pop">
		{#if options.length > 8}
			<input type="search" bind:value={q} placeholder="Find in {label.toLowerCase()}" aria-label="Find in {label.toLowerCase()}" />
		{/if}
		<fieldset>
			<legend class="visually-hidden">{label}</legend>
			{#each matches.shown as o (o.value)}
				<label title={o.label}>
					<input type="checkbox" checked={selected.includes(o.value)} onchange={() => toggle(o.value)} />
					<span class="l">{o.label}</span>
					<span class="muted">{f.int(o.n)}</span>
				</label>
			{:else}
				<p class="caption">No value matches.</p>
			{/each}
		</fieldset>
		{#if matches.total > matches.shown.length}
			<p class="caption more">Showing {matches.shown.length} of {f.int(matches.total)} values. Type to narrow the list.</p>
		{/if}
	</div>
</details>

<style>
	details {
		position: relative;
	}
	summary {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 34px;
		padding: 4px 14px;
		border: 1px solid var(--control);
		border-radius: 980px;
		font-size: 0.8125rem;
		cursor: pointer;
		list-style: none;
		white-space: nowrap;
		user-select: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	details.on summary {
		border-color: var(--text);
		box-shadow: inset 0 0 0 1px var(--text);
	}
	.count {
		display: inline-grid;
		place-items: center;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 9px;
		background: var(--text);
		color: var(--bg);
		font-size: 0.6875rem;
		font-weight: 600;
	}
	.pop {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 35;
		width: min(380px, calc(100vw - 2 * var(--pad)));
		max-height: min(420px, 60vh);
		overflow-y: auto;
		padding: 10px;
		background: var(--bg);
		border: 1px solid var(--hairline);
		border-radius: 14px;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14);
	}
	input[type='search'] {
		width: 100%;
		height: 36px;
		padding: 0 10px;
		margin-bottom: 6px;
		border: 1px solid var(--control);
		border-radius: 9px;
		background: var(--bg);
		font-size: 0.875rem;
	}
	fieldset {
		border: 0;
		margin: 0;
		padding: 0;
		display: grid;
	}
	label {
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: start;
		gap: 10px;
		padding: 7px 6px;
		border-radius: 8px;
		font-size: 0.8125rem;
		cursor: pointer;
	}
	label:hover {
		background: var(--bg-2);
	}
	label input {
		margin-top: 2px;
		accent-color: var(--accent);
	}
	.l {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.more {
		margin: 8px 6px 2px;
	}
</style>
