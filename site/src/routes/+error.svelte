<script lang="ts">
	import { page } from '$app/state';
	import NotFound from '$lib/components/NotFound.svelte';
</script>

{#if page.status === 404}
	<NotFound />
{:else}
	<section class="wrap" style="padding: 96px var(--pad)">
		<h1>Something went wrong.</h1>
		<p class="lede">{page.error?.message ?? 'Unexpected error.'}</p>
		<button class="btn" type="button" onclick={() => location.reload()}>Try again</button>
	</section>
{/if}
