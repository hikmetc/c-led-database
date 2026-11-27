# Changelog

## 0.4.2 - 2026-11-26

### Added
- `manager/` - a macOS desktop app for maintaining the database. It shows the database on this
  Mac, on GitHub and on the website, lists archive runs that are not imported yet, and imports,
  changes, deletes and publishes. Every change is described and confirmed first and is undone if
  the build, the validation or the audit fails. Built with `manager/build_app.sh`.
- `scripts/import_archive.py --commit-only` (commit locally, do not push), and a warning when a
  newer version of a table has fewer rows than the one it replaces.
- **Inclusion screening** (`scripts/screening.py`): rejection criteria applied row by row, with a
  concrete reason for every rejection. Automatic: no findable source (1), no citation (2), no
  evidence (3), duplicate row (8), malformed or unknown DOI (9), recorded verdict contradicting
  the numeric change (17). Decided by hand: wrong analyte (4), wrong document (5), out of scope
  (10). The importer applies it with `--screen`; the manager screens every import, any table and
  the whole database. Rejections need confirmation and are archived in `meta/rejected_rows.csv`.
- Manager: edit an analyte (name, system, unit, kind of property, APS, synonyms), delete an
  analyte, rename an interference cause or move it to another concept.

### Changed
- The database is now named **EFLM Laboratory Error Database** and is marked as a **Beta version** on the
  website, in the README and in STRUCTURE.md. It was called C-LED (Clinical Laboratory Error
  Database) before. The repository name, the file names and the identifiers are unchanged.

### Fixed
- The APS type was described as "allowable total error (relative)". It is an **allowable bias
  (relative)**: corrected in `meta/analytes.*`, every analyte record and page, STRUCTURE.md and
  the website (analyte pages, Methods, About). No APS value and no verdict changed.

## 0.4.1 - 2026-11-26

Archival release. No change to the data, the build or the website since 0.4.0.

### Changed
- The repository is linked to Zenodo, which archives each published release from this one on.
  0.4.0 was published before the link existed and is therefore not archived there.
- `meta/zenodo.json` records the DOIs Zenodo issued (all versions: 10.5281/zenodo.24561393;
  0.4.1: 10.5281/zenodo.24561394). The README and the website's How to cite page show them.

## 0.4.0 - 2026-11-26

The database gets a website, and a one-command import from the literature archive.

### Added
- **Website** at <https://hikmetc.github.io/c-led-database/>, a static site under `site/`
  (SvelteKit, Svelte 5, TypeScript) that reads only the web deploy set, directly in the
  browser, with a small JavaScript Parquet reader (hyparquet).
  - Pages: overview with a concept x analyte matrix, analyte, interferent, concept, search,
    row permalink (also shown as a drawer), about, methods, data dictionary, how to cite,
    changelog, downloads.
  - Custom APS per analyte, kept in the URL; rows without a numeric change are never
    recomputed and never shown as zero.
  - Effect charts on a symmetric log scale, with a clipped linear alternative that marks and
    counts the values beyond the axis instead of dropping them.
  - Driven by `parquet/manifest.json`: a new analyte appears with no code change, which a
    growth test verifies against a fake analyte that exists only in that test build.
  - No analytics, no cookies and no third-party requests.
  - Fast first chart: a page needs only its own Parquet file (20-90 kB), preloaded with the
    HTML. An earlier build queried the files with DuckDB-WASM, whose 8 MB download delayed the
    first chart by a minute or more on a slow connection; it was replaced. Files above 4 MB are
    read over HTTP range requests, with a whole-file fallback.
- `.github/workflows/pages.yml` - rebuilds the data, builds and tests the site (unit tests,
  end-to-end tests with accessibility checks) and deploys it to GitHub Pages on every push.
- `scripts/import_archive.py` - imports one extraction run of the literature archive: checks
  the table, registers it, prunes, rebuilds, validates, undoes everything on failure, and asks
  before it commits and pushes.
- `build/stats.json` - new `references` and `by_reference_status`, so the website can show
  reference coverage without querying the Parquet files.

### Changed
- README and STRUCTURE.md describe the website, its data contract and the importer. The
  earlier advice to query with DuckDB-WASM from a CDN is replaced by what the site does.

### Open
- About, Methods and How to cite carry clearly marked TODOs where the repository holds no
  information: authors, affiliations, funding, intended use, literature search and selection
  methods, the rationale of each APS, and a formal citation.

## 0.3.0 - 2026-11-26

A Parquet web layer, built to stay small and fast as the database grows at least fifty-fold.

### Added
- `build/parquet/` - the only data the website reads, built by `scripts/parquet_export.py`:
  - `slim_all.parquet` - every row, the columns a table, facets, charts and the custom-APS logic
    need, typed (`pct_change` is a real number, `plottable` and `exceeds_aps` are booleans),
    sorted by analyte and interferent so filters skip whole row groups.
  - `slim/<analyte_id>.parquet` - the same columns for one analyte.
  - `detail/<analyte_id>.parquet` - `row_id` plus every source column, sorted by `row_id` in
    2,000-row groups, so opening one evidence row reads one row group rather than the file.
  - `manifest.json` - schema version, every file, row counts, byte sizes and column types, so a
    site never hard-codes analytes.
- The web deploy set (2.61 MB today) replaces a 160 MB JSON-and-SQLite build as the
  published data. Measured on this data, Parquet is about 40 times smaller than the same rows as
  JSON; a fifty-fold growth projects to well under 100 MB against GitHub Pages' 1 GB limit.
- `meta/data_dictionary.*` - new `parquet_column`: the snake_case Parquet name of every source
  column. `Analyte`, `Interferent` and `doi` map to `analyte_verbatim`, `interferent_verbatim`
  and `doi_as_printed`, so they cannot be confused with normalised slim fields.
- `requirements.txt` - pyarrow, the only dependency of the build.

### Validation
- An evidence CSV over 90 MiB now fails the build (GitHub rejects files over 100 MiB); over
  50 MiB it warns.
- The Parquet layer is checked against the evidence: equal row counts across slim, detail,
  `slim_all` and the manifest, one slim file per analyte, unique `row_id`, every listed file
  present. A stale layer fails the build.
- The web deploy set fails the build above 900 MB and warns above 500 MB.
- `CLED_REQUIRE_PARQUET=1` (set in CI) makes a missing Parquet layer a hard failure. Without
  pyarrow a local build skips the layer with a notice and removes any stale copy.

### Changed
- CI installs `requirements.txt`, requires the Parquet layer, runs the evidence audit, uploads
  only the web deploy set as an artifact, and attaches `cled-parquet.zip` to releases instead
  of the SQLite file (which would outgrow the 2 GiB release-asset limit).
- README and STRUCTURE.md document the Parquet layer, the deploy set, which file each view
  reads, and the new invariants. The SQLite database and the JSON shards are now internal or
  legacy and are never published.

## 0.2.0 - 2026-11-25

Evidence-integrity pass: every row must be backed by a cited source that actually
supplied data.

### Removed - 33 rows that carried no evidence
Rule applied: **a row with no value in any of the 11 data fields is not evidence.**
The 11 fields are direction of effect, the four change fields, magnitude, baseline and
final concentration, interferent concentration, platform/method and analyzer.
All removed rows are archived with their full 29 columns in `meta/removed_rows.csv`.

Why each group was removed:
- 6 rows citing scanned PDFs with no text layer, from which nothing could be read.
- 6 rows citing a journal masthead or editorial-board front-matter page instead of the article.
- 5 rows citing Clin Lab articles whose PDF carried no article text.
- 1 row citing a Blood classified-advertisement page instead of the 2006 ASH abstract.
- 1 row citing a publisher permissions sheet instead of the Morgan article.
- 1 row citing an FDA bioequivalence guidance that contains no digoxin or uzara data.
- 5 rows where the cited source reports salicylate interference for **chloride** (or for the
  carbonate electrode), not for pH.
- 2 rows where the cited source did not measure the analyte at all (L-lactate instead of pH;
  no COHb content in the Hb Bassett paper).
- 1 row where the source lists leucocyte larceny under pO2 only, with the pCO2 cell left blank.
- 2 further coverage rows with no extracted values.

### Consequences
- Evidence rows: 11,982 -> 11,949. Rows carrying a numeric effect size are unchanged at 6,607,
  so no quantitative evidence was lost.
- Two evidence tables became empty and were deleted, together with their canonical interferents:
  - `ph_blood` **salicylate** - every row described chloride, not pH interference.
  - `carboxyhemoglobin_blood` **hemoglobin Bassett** - the cited paper contains no COHb content.
  - Evidence tables: 119 -> 117. Interference causes: 138 -> 136.
  - Their full-text PDFs are kept in the local working copy in case usable evidence is found later.

### Added
- `meta/removed_rows.csv` - every removed row in full, with the reason.
- `meta/pdf_issues.csv` - PDFs that hold the wrong document or are duplicates.
- `meta/references_enriched.csv` grew to 13 entries: identifiers recovered from the PDF title
  page, from PubMed, or from publisher article identifiers encoded in file names, each with
  its resolution method and what it was verified against.
- `scripts/audit_evidence.py` - re-runnable audit: citation present, identifier present,
  data present, and no row left citing a document that supplied nothing.
- `scripts/prune_unevidenced_rows.py` - the rule above, re-runnable on new analytes.

### Reference coverage after the pass
- 0 rows without a citation.
- 0 rows without a DOI, a PubMed ID or a full reference, except 5 rows whose sources are a
  conference poster, a journal letter not indexed in PubMed, and a book chapter; all three
  carry complete author, title and venue details.
- 0 rows that both lack data and cite a document that supplied nothing.

## 0.1.0 - 2026-11-25

First structured release of the C-LED database: 8 analytes, 138 interference causes,
119 evidence tables, 11,982 evidence rows, 814 distinct references.

### Data
- All 119 evidence tables verified to share one identical 29-column header; all valid UTF-8;
  no duplicate rows.
- `potassium_order_of_draw_extraction.csv` converted from the original Apple Numbers file
  (10 rows, same 29 columns, same 0.4% APS). The `.numbers` original is kept locally.
- UTF-8 BOM stripped from 5 tables (`digoxin_DLIS`, `digoxin_glycoside`, `digoxin_haemolysis`,
  `digoxin_spironolactone`, `inr_anticoagulant_contamination`); a BOM breaks the first column
  name for CSV readers. No content changed.
- The undocumented `XX ` prefix removed from three `ph_blood` table names.
- File and folder names normalised for portability: spaces to underscores, non-ASCII hyphens to
  ASCII, over-long paths shortened. Every rename is recorded in `meta/rename_map.csv`.

### Added - controlled vocabulary and join keys
- `meta/interferents.csv`: 138 canonical interference causes with stable ids
  (`<analyte_id>.<key>`) and a cross-analyte `concept`.
- `meta/interferent_synonyms.csv`: all 1,147 verbatim interferent wordings mapped to a canonical
  id. This is the join key that makes facet filtering possible; the same cause is worded many
  different ways across papers.
- `meta/table_index.csv`: evidence table to default interferent id, flagging the tables that
  carry wording-level overrides because they genuinely cover several distinct causes.
- `meta/analytes.csv` / `.json` and `<analyte>/<analyte>_analyte.csv`: component, system,
  kind of property, unit and the selected APS, as data rather than prose.
- `meta/data_dictionary.csv` / `.json`: definitions of all 29 source columns, verified against
  the real header by `scripts/validate.py`.
- `meta/references.csv`: 814 distinct references with DOI and PubMed ID.
- `meta/references_enriched.csv`: 2 references recovered via PubMed for rows whose source PDF had
  no text layer, recorded separately with provenance rather than written into the source tables.
- `meta/known_gaps.csv`: the 7 rows whose source document carries no usable identifier.

### Added - derived build (generated, not committed)
- `build/cled.sqlite`: `analyte`, `interferent`, `evidence`, `reference_` and an FTS5 full-text
  index, with a stable `row_id` per row.
- Normalised fields for filtering and charting: `direction`, `pct_change` (signed percent),
  `plottable`, `aps_percent`, `aps_verdict`, `exceeds_aps`, `doi`, `pmid`, `reference_status`,
  and the four appraisal fields with consistent casing.
- `build/slim/<analyte_id>.json` and `build/evidence/<analyte>/<interferent>.json`, sharded so
  neither the repository nor a single HTTP response grows without bound as analytes are added.
- `build/stats.json` for dashboards; `build/manifest.json` and `build/slim/index.json` as shard
  manifests; `build/schema.sql`.

### Added - repository plumbing
- `scripts/build_all.py` rebuilds everything from the CSVs and never writes to them;
  `scripts/validate.py` fails on an unregistered table, an orphan interferent id, a duplicate
  `row_id`, a row-count mismatch, a non-portable path or a committed PDF.
- `.github/workflows/build.yml` builds and validates on every push, uploads the dataset as an
  artifact, and attaches `cled.sqlite` plus a JSON bundle to published releases.
- `.gitignore` keeps `build/` and all local-only material out of git.

### Not distributed
- Full-text PDFs (1,632 files, 1.3 GB) are publisher copyright and stay in the local working
  copy only. Every row carries a DOI, a PubMed ID or a full reference instead.
- `analyte_level/` and `other_formats/` working files stay local; their machine-readable
  equivalents are `meta/` and `<analyte>/<analyte>_analyte.csv`.

### Known limitations
- `pct_change` is present for 6,607 of 11,982 rows (55%). Many sources report an effect only in
  words or only in absolute units. Use the `plottable` flag; never read a missing value as zero.
- `Significant-bias threshold` is the source study's own criterion and is "not reported" in
  7,213 rows. It is not the database APS.
- `row_id` is stable while rows are appended to a table, not if rows are inserted in the middle.
