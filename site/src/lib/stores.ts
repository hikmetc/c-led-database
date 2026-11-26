import { writable } from 'svelte/store';

/** The evidence row shown in the right-side drawer (with the APS active where it was opened). */
export const drawerRow = writable<{ id: string; aps?: number } | null>(null);
