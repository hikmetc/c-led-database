export const NOT_REPORTED = 'Not reported';

const intFmt = new Intl.NumberFormat('en-US');
export function int(n: number): string {
	return intFmt.format(n);
}

/** Signed percent for display. The stored value is never altered; this only formats it. */
export function pct(v: number | null | undefined): string {
	if (typeof v !== 'number' || !Number.isFinite(v)) return NOT_REPORTED;
	const abs = Math.abs(v);
	const digits = abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
	const s = new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(abs);
	return `${v > 0 ? '+' : v < 0 ? '−' : ''}${s} %`;
}

export function aps(v: number): string {
	return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(v)} %`;
}

export function share(v: number | null): string {
	if (v === null || !Number.isFinite(v)) return 'n/a';
	return `${Math.round(v * 100)} %`;
}

export function bytes(n: number): string {
	if (n >= 1e6) return `${(n / 1e6).toFixed(2)} MB`;
	return `${Math.max(1, Math.round(n / 1e3))} kB`;
}

/** `iv_fluid_contamination` -> `IV fluid contamination`. A generic rule, not a vocabulary. */
export function humanize(id: string): string {
	const words = id.split('_').filter(Boolean);
	return words
		.map((w, i) => {
			if (/\d/.test(w) || w.length <= 2) return w.toUpperCase();
			return i === 0 ? w[0].toUpperCase() + w.slice(1) : w;
		})
		.join(' ');
}

const DIRECTION_LABELS: Record<string, string> = {
	up: 'Increase',
	down: 'Decrease',
	none: 'No effect',
	not_reported: NOT_REPORTED
};
export function directionLabel(v: string | null | undefined): string {
	if (!v) return NOT_REPORTED;
	return DIRECTION_LABELS[v] ?? humanize(v);
}

const REF_LABELS: Record<string, string> = {
	doi: 'DOI',
	pmid: 'PubMed ID only',
	reference_only: 'Full reference only',
	citation_only: 'Citation only',
	unidentified: 'Unidentified'
};
export function refStatusLabel(v: string | null | undefined): string {
	if (!v) return NOT_REPORTED;
	return REF_LABELS[v] ?? humanize(v);
}

const VERDICT_LABELS: Record<string, string> = {
	exceeds: 'Exceeds APS',
	within: 'Within APS',
	not_computable: 'Not computable',
	not_reported: NOT_REPORTED,
	other: 'Other'
};
export function verdictLabel(v: string | null | undefined): string {
	if (!v) return NOT_REPORTED;
	return VERDICT_LABELS[v] ?? humanize(v);
}

/** The phrase the sources use for a missing value; such values are shown muted. */
export function isNotReported(v: unknown): boolean {
	if (v === null || v === undefined) return true;
	const s = String(v).trim().toLowerCase();
	return s === '' || s === 'not reported in the information source' || s === 'not reported' || s === 'not_reported';
}

export function doiUrl(doi: string): string {
	return `https://doi.org/${doi}`;
}
export function pmidUrl(pmid: string): string {
	return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
}

/** RFC 4180 CSV. */
export function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
	const cell = (v: unknown) => {
		if (v === null || v === undefined) return '';
		const s = String(v);
		return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
	};
	const lines = [columns.map(cell).join(',')];
	for (const r of rows) lines.push(columns.map((c) => cell(r[c])).join(','));
	return lines.join('\r\n') + '\r\n';
}
