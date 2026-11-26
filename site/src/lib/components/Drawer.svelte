<script lang="ts">
	import { afterNavigate } from '$app/navigation';
	import { drawerRow } from '$lib/stores';
	import RowView from './RowView.svelte';

	let dialog = $state<HTMLDialogElement | undefined>();
	let opener: HTMLElement | null = null;

	$effect(() => {
		if (!dialog) return;
		if ($drawerRow && !dialog.open) {
			opener = document.activeElement as HTMLElement | null;
			dialog.showModal(); // native modal: focus is trapped and Esc closes
		} else if (!$drawerRow && dialog.open) dialog.close();
	});
	afterNavigate(() => drawerRow.set(null));

	function onClose() {
		drawerRow.set(null);
		opener?.focus?.();
		opener = null;
	}
	function onBackdrop(e: MouseEvent) {
		if (e.target === dialog) dialog?.close();
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog bind:this={dialog} onclose={onClose} onclick={onBackdrop} aria-label="Evidence row" data-testid="drawer">
	{#if $drawerRow}
		<div class="panel">
			<button class="close btn" type="button" onclick={() => dialog?.close()} aria-label="Close">Close</button>
			{#key $drawerRow.id}
				<RowView rowId={$drawerRow.id} aps={$drawerRow.aps} heading="h2" />
			{/key}
		</div>
	{/if}
</dialog>

<style>
	dialog {
		position: fixed;
		inset: 0 0 0 auto;
		width: min(720px, 100vw);
		max-width: none;
		height: 100dvh;
		max-height: none;
		margin: 0;
		padding: 0;
		border: 0;
		border-left: 1px solid var(--hairline);
		background: var(--bg);
		color: var(--text);
		overflow-y: auto;
	}
	dialog[open] {
		animation: slide 280ms var(--ease);
	}
	dialog::backdrop {
		background: rgba(0, 0, 0, 0.32);
	}
	@keyframes slide {
		from {
			transform: translateX(32px);
			opacity: 0;
		}
	}
	.panel {
		padding: 24px clamp(20px, 4vw, 40px) 48px;
	}
	.close {
		float: right;
		margin-left: 12px;
	}
</style>
