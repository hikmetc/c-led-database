<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';
	import { getSite } from '$lib/context';
	import { SITE_NAME, SITE_STAGE, sitePath } from '$lib/env';
	import ThemeToggle from './ThemeToggle.svelte';

	const site = getSite();
	let menu = $state<HTMLDetailsElement | undefined>();
	const links = [
		{ href: '/methods/', label: 'Methods' },
		{ href: '/data-dictionary/', label: 'Dictionary' },
		{ href: '/downloads/', label: 'Downloads' },
		{ href: '/about/', label: 'About' }
	];
	const path = $derived(sitePath(page.url.pathname, base));
	afterNavigate(() => {
		if (menu) menu.open = false;
	});
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && menu?.open) {
			menu.open = false;
			menu.querySelector('summary')?.focus();
		}
	}
	function onDocClick(e: MouseEvent) {
		if (menu?.open && !menu.contains(e.target as Node)) menu.open = false;
	}
</script>

<svelte:document onclick={onDocClick} />

<header class="nav">
	<nav class="wrap inner" aria-label="Main">
		<a class="brand" href="{base}/"><span class="name">{SITE_NAME}</span><span class="stage">{SITE_STAGE}</span></a>
		<ul>
			<li>
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<details bind:this={menu} onkeydown={onKey}>
					<summary>Analytes</summary>
					<div class="menu" data-testid="analyte-menu">
						{#each site.index?.analytes ?? [] as a (a.analyte_id)}
							<a href="{base}/analyte/{a.analyte_id}/" aria-current={path === `/analyte/${a.analyte_id}/` ? 'page' : undefined}>
								<span>{a.component}</span>
								<span class="caption">{a.system}</span>
							</a>
						{/each}
					</div>
				</details>
			</li>
			{#each links as l (l.href)}
				<li><a href="{base}{l.href}" aria-current={path === l.href ? 'page' : undefined}>{l.label}</a></li>
			{/each}
		</ul>
		<div class="tools">
			<a class="icon" href="{base}/search/" aria-label="Search">
				<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.75" fill="none" stroke="currentColor" stroke-width="1.6" /><path d="M13 13l4.5 4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
			</a>
			<ThemeToggle />
		</div>
	</nav>
</header>

<style>
	.nav {
		position: sticky;
		top: 0;
		z-index: 40;
		background: var(--nav-bg);
		-webkit-backdrop-filter: saturate(180%) blur(20px);
		backdrop-filter: saturate(180%) blur(20px);
		border-bottom: 1px solid var(--hairline);
	}
	.inner {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 52px;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 8px;
		flex: none;
		font-weight: 600;
		font-size: 1rem;
		letter-spacing: -0.01em;
		line-height: 1.15;
		color: var(--text);
		margin-right: 12px;
	}
	.brand:hover {
		text-decoration: none;
	}
	.stage {
		padding: 2px 8px;
		border: 1px solid var(--control);
		border-radius: 980px;
		font-size: 0.6875rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-2);
		white-space: nowrap;
	}
	.tools {
		margin-left: auto;
	}
	/* narrow screens: name and tools on the first row, the links on a second, scrollable row */
	@media (max-width: 760px) {
		.inner {
			flex-wrap: wrap;
			row-gap: 0;
		}
		.brand {
			flex: 0 0 100%;
			font-size: 0.9375rem;
			min-height: 44px;
			margin-right: 0;
		}
		ul {
			flex: 1 1 0;
			margin-left: -10px;
		}
	}
	ul {
		display: flex;
		align-items: center;
		gap: 4px;
		list-style: none;
		margin: 0;
		padding: 0;
		flex: 1;
		min-width: 0;
		overflow-x: auto;
		scrollbar-width: none;
	}
	ul::-webkit-scrollbar {
		display: none;
	}
	li > a,
	summary {
		display: block;
		padding: 8px 10px;
		font-size: 0.8125rem;
		color: var(--text);
		white-space: nowrap;
		cursor: pointer;
		border-radius: 8px;
		opacity: 0.86;
	}
	li > a:hover,
	summary:hover {
		opacity: 1;
		text-decoration: none;
	}
	li > a[aria-current='page'] {
		opacity: 1;
		font-weight: 600;
	}
	summary {
		list-style: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	summary::after {
		content: '';
		display: inline-block;
		width: 6px;
		height: 6px;
		margin-left: 6px;
		border-right: 1.5px solid currentColor;
		border-bottom: 1.5px solid currentColor;
		transform: translateY(-2px) rotate(45deg);
	}
	.menu {
		position: absolute;
		top: 100%;
		left: var(--pad);
		z-index: 50;
		display: grid;
		gap: 2px;
		min-width: min(320px, calc(100vw - 2 * var(--pad)));
		max-height: 70vh;
		overflow-y: auto;
		padding: 8px;
		background: var(--bg);
		border: 1px solid var(--hairline);
		border-radius: 14px;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
	}
	.menu a {
		display: flex;
		justify-content: space-between;
		gap: 16px;
		padding: 8px 10px;
		border-radius: 8px;
		color: var(--text);
		font-size: 0.875rem;
	}
	.menu a:hover,
	.menu a[aria-current='page'] {
		background: var(--bg-2);
		text-decoration: none;
	}
	.inner {
		position: relative;
	}
	.tools {
		display: flex;
		align-items: center;
		gap: 4px;
	}
	.icon {
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		color: var(--text);
		border-radius: 50%;
	}
	.icon:hover {
		background: var(--bg-2);
	}
</style>
