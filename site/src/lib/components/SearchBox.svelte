<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { getSite } from '$lib/context';
	import { getSearcher, type Suggestion } from '$lib/search';

	let { value = $bindable(''), large = false, autofocus = false, onsubmit }: { value?: string; large?: boolean; autofocus?: boolean; onsubmit?: (q: string) => void } = $props();
	const site = getSite();
	const uid = $props.id();
	let suggestions = $state<Suggestion[]>([]);
	let open = $state(false);
	let active = $state(-1);
	let seq = 0;

	async function update() {
		const q = value.trim();
		const mine = ++seq;
		if (q.length < 2 || !site.index) {
			suggestions = [];
			open = false;
			return;
		}
		const search = await getSearcher(site.index);
		if (mine !== seq) return;
		suggestions = search(q, 8);
		active = -1;
		open = true;
	}
	function submit() {
		const q = value.trim();
		open = false;
		if (onsubmit) onsubmit(q);
		else if (q) goto(`${base}/search/?q=${encodeURIComponent(q)}`);
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'ArrowDown' && suggestions.length) {
			e.preventDefault();
			open = true;
			active = (active + 1) % suggestions.length;
		} else if (e.key === 'ArrowUp' && suggestions.length) {
			e.preventDefault();
			active = active <= 0 ? suggestions.length - 1 : active - 1;
		} else if (e.key === 'Enter') {
			e.preventDefault();
			if (open && active >= 0) {
				open = false;
				goto(base + suggestions[active].href);
			} else submit();
		} else if (e.key === 'Escape') open = false;
	}
</script>

<form class="search" class:large role="search" onsubmit={(e) => { e.preventDefault(); submit(); }}>
	<svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.75" fill="none" stroke="currentColor" stroke-width="1.6" /><path d="M13 13l4.5 4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
	<!-- svelte-ignore a11y_autofocus -->
	<input
		type="search"
		bind:value
		oninput={update}
		onkeydown={onKey}
		onfocus={() => (open = suggestions.length > 0)}
		onblur={() => setTimeout(() => (open = false), 150)}
		placeholder="Search analytes, interferents, concepts"
		aria-label="Search the database"
		role="combobox"
		aria-expanded={open}
		aria-controls="{uid}-list"
		aria-autocomplete="list"
		aria-activedescendant={open && active >= 0 ? `${uid}-opt-${active}` : undefined}
		autocomplete="off"
		spellcheck="false"
		{autofocus}
	/>
	<ul id="{uid}-list" role="listbox" aria-label="Suggestions" hidden={!open || !suggestions.length}>
		{#each suggestions as s, i (s.id)}
			<li id="{uid}-opt-{i}" role="option" aria-selected={i === active} class:active={i === active}>
				<a href="{base}{s.href}" tabindex="-1" onmousedown={(e) => e.preventDefault()}>
					<span class="t">{s.title}</span>
					<span class="caption">{s.kind}{s.subtitle ? ` · ${s.subtitle}` : ''}</span>
				</a>
			</li>
		{/each}
	</ul>
</form>

<style>
	.search {
		position: relative;
		display: flex;
		align-items: center;
		width: 100%;
		max-width: 640px;
	}
	svg {
		position: absolute;
		left: 16px;
		color: var(--text-2);
		pointer-events: none;
	}
	input {
		width: 100%;
		height: 44px;
		padding: 0 16px 0 46px;
		border: 1px solid var(--control);
		border-radius: 14px;
		background: var(--bg);
		font-size: 1rem;
	}
	.large input {
		height: 56px;
		font-size: 1.1875rem;
		border-radius: 18px;
	}
	input::placeholder {
		color: var(--text-2);
		opacity: 1;
	}
	ul {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		right: 0;
		z-index: 30;
		margin: 0;
		padding: 6px;
		list-style: none;
		text-align: left;
		background: var(--bg);
		border: 1px solid var(--hairline);
		border-radius: 14px;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
	}
	li a {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 12px;
		padding: 9px 12px;
		border-radius: 9px;
		color: var(--text);
	}
	li a:hover,
	li.active a {
		background: var(--bg-2);
		text-decoration: none;
	}
	.t {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.caption {
		flex: none;
	}
</style>
