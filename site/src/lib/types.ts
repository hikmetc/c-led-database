export interface ManifestFile {
	path: string;
	rows: number;
	bytes: number;
	analyte_folder?: string;
	sorted_by?: string[];
}
export interface ManifestColumn {
	name: string;
	type: string;
}
export interface Manifest {
	schema_version: string;
	compression?: string;
	row_count: number;
	slim_columns: ManifestColumn[];
	detail_columns: ManifestColumn[];
	files: {
		slim_all: ManifestFile;
		slim: Record<string, ManifestFile>;
		detail: Record<string, ManifestFile>;
	};
}
export interface Analyte {
	analyte_id: string;
	analyte_folder: string;
	component: string;
	system: string;
	kind_of_property: string;
	unit: string;
	aps_percent: number;
	aps_type: string;
	aps_note: string;
	synonyms: string;
	interferent_count: number;
	evidence_tables: number;
	evidence_rows: number;
}
export interface Interferent {
	interferent_id: string;
	analyte_folder: string;
	interferent_key: string;
	interferent_canonical: string;
	concept: string;
	evidence_rows: number;
	wording_variants: number;
}
export interface Stats {
	generated_rows: number;
	by_analyte: Record<string, number>;
	plottable_by_analyte: Record<string, number>;
	by_direction: Record<string, number>;
	by_verdict: Record<string, number>;
	by_concept: Record<string, number>;
	/** Present from build 0.4.0 on; the KPI that needs them is hidden when they are absent. */
	references?: number;
	by_reference_status?: Record<string, number>;
	pct_change_summary?: Record<string, { n: number; min: number; max: number; median: number }>;
}
export interface DictionaryEntry {
	position: number;
	column: string;
	parquet_column: string;
	type: string;
	values: string;
	definition: string;
}
/** One evidence row of a slim Parquet file (only the columns the views use). */
export interface SlimRow {
	row_id: string;
	analyte_id: string;
	interferent_id: string;
	interferent_canonical: string;
	concept: string;
	interferent_verbatim: string | null;
	platform: string | null;
	analyzer: string | null;
	sample_type: string | null;
	direction: string | null;
	pct_change: number | null;
	plottable: boolean;
	aps_percent: number;
	aps_verdict: string | null;
	doi: string | null;
	pmid: string | null;
	reference_status: string | null;
}
export interface SiteData {
	manifest: Manifest | null;
	manifestError: string | null;
	analytes: Analyte[];
	interferents: Interferent[];
	stats: Stats | null;
	dictionary: DictionaryEntry[];
}
