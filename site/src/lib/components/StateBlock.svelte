<script lang="ts">
	let { kind, message = '', onretry, height = 240 }: { kind: 'loading' | 'error' | 'empty'; message?: string; onretry?: () => void; height?: number } = $props();
</script>

{#if kind === 'loading'}
	<div class="skeleton" style="height:{height}px" role="status" aria-label={message || 'Loading data'}></div>
{:else}
	<div class="state" role={kind === 'error' ? 'alert' : 'status'}>
		<p class="t">{kind === 'error' ? 'The data could not be loaded.' : 'Nothing matches this selection.'}</p>
		{#if message}<p class="caption">{message}</p>{/if}
		{#if kind === 'error' && onretry}<button class="btn" type="button" onclick={onretry}>Try again</button>{/if}
	</div>
{/if}

<style>
	.state {
		border: 1px dashed var(--control);
		border-radius: var(--radius);
		padding: 40px 24px;
		text-align: center;
	}
	.t {
		font-weight: 600;
		margin: 0 0 4px;
	}
	.caption {
		margin: 0 0 12px;
	}
</style>
