/** The analyte of a row_id is the text before the first dot (see STRUCTURE.md, section 6). */
export function analyteIdOfRow(rowId: string): string | null {
	if (typeof rowId !== 'string') return null;
	const i = rowId.indexOf('.');
	if (i <= 0 || i === rowId.length - 1) return null;
	return rowId.slice(0, i);
}

/** The analyte of an interferent_id (`<analyte_id>.<key>`). */
export function analyteIdOfInterferent(interferentId: string): string | null {
	return analyteIdOfRow(interferentId);
}
