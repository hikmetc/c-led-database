<script lang="ts">
	import { onMount } from 'svelte';

	let dark = $state(false);
	onMount(() => {
		const attr = document.documentElement.getAttribute('data-theme');
		dark = attr ? attr === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
	});
	function toggle() {
		dark = !dark;
		const value = dark ? 'dark' : 'light';
		document.documentElement.setAttribute('data-theme', value);
		try {
			localStorage.setItem('cled-theme', value);
		} catch {
			/* storage unavailable: the choice lasts for this page only */
		}
	}
</script>

<button class="icon" type="button" onclick={toggle} aria-pressed={dark} aria-label="Dark theme" data-testid="theme-toggle">
	{#if dark}
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="10" cy="10" r="3.6" fill="currentColor" /><g stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" /></g></svg>
	{:else}
		<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M16.5 12.2A7 7 0 0 1 7.8 3.5a7 7 0 1 0 8.7 8.7z" fill="currentColor" /></svg>
	{/if}
</button>

<style>
	.icon {
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		border: 0;
		background: none;
		border-radius: 50%;
		cursor: pointer;
	}
	.icon:hover {
		background: var(--bg-2);
	}
</style>
