# CLAUDE.md — C-LED database

Read this first, then STRUCTURE.md (the authoritative description) and README.md.

## What this repo is
An evidence database of laboratory analytical interference (how an interferent such as
hemolysis, bilirubin or heparin changes the measurement of an analyte), one folder per
analyte, every row traceable to a published source by citation, DOI and/or PMID.

## Invariants (never break these)
1. The evidence CSVs under `<analyte>/database/*.csv` are the single source of truth. Do not
   edit, reorder, reformat or "clean" them. The build only reads them. Changes to data go
   through the process in STRUCTURE.md (registry + CSV + build + validate), and only when
   the user asks for a data change.
2. `build/` is generated and gitignored. Never commit it. CI rebuilds it.
3. No PDFs, ever, in this repo or on the website (`fulltext_pdfs/`, `analyte_level/`,
   `other_formats/` are local-only and gitignored). References are by citation, DOI, PMID.
4. No licence file and no licence text. Do not add one, do not suggest one in commits.
5. English only in data, code, UI and docs. No Turkish terms or classifications.
6. Never invent or "fix" a DOI, PMID, citation, value or analyte name. Missing values are
   null / "not reported in the information source" and are shown as such, never as zero.
7. The website reads the web deploy set and only that: `build/parquet/**`,
   `build/analytes.json`, `build/interferents.json`, `build/stats.json`. Never publish
   `build/cled.sqlite`, `build/evidence*`, `build/slim/`, or any CSV-derived JSON shard.
8. Never hard-code analytes, interferents or file names in the site; read
   `build/parquet/manifest.json`.
9. `scripts/registry.py` is the only place analytes, ids and canonical interferents are
   defined. ids: analyte_id = prefix (e.g. `tn`), interferent_id = `<prefix>.<key>`,
   row_id = `<prefix>.<table stem>.<NNNN>`; the analyte of a row_id is the text before the
   first dot.

## Commands
```bash
pip install -r requirements.txt                       # pyarrow (only build dependency)
CLED_REQUIRE_PARQUET=1 CLED_DISTRIBUTION=1 python3 scripts/build_all.py   # build + validate
python3 scripts/audit_evidence.py .                   # evidence / reference audit
```
`build_all.py` must end with `all checks passed`. If it fails, stop and report; do not
work around a validator.

## Website (`site/`)
Static site, deployed to GitHub Pages by `.github/workflows/pages.yml`. Data is fetched at
runtime with DuckDB-WASM over HTTP range requests from the deployed Parquet files.
`pct_change` can be extreme (troponin hemolysis reaches 14,100 %); charts must handle it
(symlog or clipped axis with explicit markers), and only rows with `plottable = true` are
drawn.
