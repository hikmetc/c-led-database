# C-LED Database

**C**linical **L**aboratory **E**rror **D**atabase - structured, source-cited evidence on how interferents bias clinical laboratory measurements, judged against an analytical performance specification (APS) for each analyte.

**Website: <https://hikmetc.github.io/c-led-database/>** - browse, filter, chart and download the evidence.

**Archive: <https://doi.org/10.5281/zenodo.24561393>** - every released version on Zenodo; this DOI always resolves to the latest one.

| | |
|---|---|
| Analytes | 8 |
| Interference causes | 136 |
| Evidence tables (CSV) | 117 |
| Evidence rows | 11,949 |
| Rows with a numeric effect size | 6,607 |
| Distinct references | 783 |
| Rows with a DOI or PubMed ID | 7,400 |

## Analytes

| Folder | Component | System | Unit | APS | Causes | Tables | Rows |
|---|---|---|---|---|---|---|---|
| `carboxyhemoglobin_blood` | Carboxyhemoglobin | Blood | % of total haemoglobin | 1.0% | 27 | 20 | 2,095 |
| `digoxin_serum` | Digoxin | Serum | ng/mL (nmol/L) | 3.0% | 29 | 25 | 4,308 |
| `inr_plasma` | International Normalized Ratio (prothrombin time) | Platelet-poor plasma (citrated) | ratio (INR) | 2.0% | 24 | 19 | 3,687 |
| `pco2_blood` | Carbon dioxide partial pressure | Blood | mmHg (kPa) | 2.7% | 9 | 8 | 146 |
| `ph_blood` | pH | Blood | pH unit | 1.5% | 11 | 10 | 182 |
| `po2_blood` | Oxygen partial pressure | Blood (arterial) | mmHg (kPa) | 3.0% | 13 | 13 | 548 |
| `potassium_serum` | Potassium | Serum | mmol/L | 0.4% | 12 | 12 | 304 |
| `troponin_serum` | Cardiac troponin I and T | Serum or plasma | ng/L (pg/mL) | 13.6% | 11 | 10 | 679 |

## Layout

```
c-led-database/
|-- README.md
|-- meta/                        registries and vocabulary (committed, small)
|   |-- analytes.csv/.json       one record per analyte: component, system, unit, APS
|   |-- interferents.csv         canonical interference causes with stable ids
|   |-- interferent_synonyms.csv every verbatim wording -> canonical id  (the join key)
|   |-- table_index.csv          evidence table -> default interferent id
|   |-- data_dictionary.csv/.json definition of all 29 source columns
|   |-- references.csv           distinct references with DOI / PubMed ID
|   |-- references_enriched.csv  references recovered outside the source tables, with provenance
|   |-- known_gaps.csv           rows whose source carries no usable identifier
|   `-- file_index.csv           one row per evidence table
|-- scripts/                     the build: registry.py + build_*.py + validate.py
|-- <analyte>/
|   |-- <analyte>_analyte.csv    the analyte record (incl. the selected APS)
|   |-- <analyte>_interferent_list.csv  this analyte's causes, with ids
|   |-- <analyte>.md             human-readable summary
|   `-- database/*.csv           the evidence tables (29 columns, never modified by the build)
`-- build/                       GENERATED, never committed (see .gitignore)
    |-- parquet/                 THE WEB LAYER - the only data the website publishes
    |   |-- manifest.json        schema version, files, row counts, byte sizes, columns
    |   |-- slim_all.parquet     every row, slim columns, sorted by analyte and interferent
    |   |-- slim/<analyte_id>.parquet    table, filter and chart columns, per analyte
    |   `-- detail/<analyte_id>.parquet  every source column, sorted by row_id, per analyte
    |-- analytes.json interferents.json stats.json   small registries, also published
    |-- cled.sqlite              internal: feeds the docs and the checks, never published
    `-- slim/, evidence/, evidence_slim.json   legacy JSON, never published
```

## Build

```bash
pip install -r requirements.txt     # pyarrow, for the Parquet web layer
python3 scripts/build_all.py        # rebuilds meta/ and build/ from the CSVs
python3 scripts/validate.py         # integrity checks only
```

Without pyarrow the build still runs and skips the Parquet layer with a notice. CI sets `CLED_REQUIRE_PARQUET=1`, which makes a missing or inconsistent Parquet layer a hard failure.

The source CSVs are the single source of truth and the build never writes to them. `build/` is regenerated from scratch each time and is **not committed**: it is produced by CI (`.github/workflows/build.yml`) on every push, uploaded as a workflow artifact, and attached to published releases. Committing it would add a fresh multi-megabyte blob to git history on every rebuild and would eventually hit GitHub's 100 MB per-file limit.

## Adding an analyte

1. Create `<analyte>/database/` and drop in the evidence tables, using the same 29 columns.
2. Add the analyte to `ANALYTES`, its causes to `CANON`, and its tables to `TABLE_MAP` in `scripts/registry.py`. Add wording rules to `OVERRIDES` only for a table that genuinely covers several distinct causes.
3. Run `python3 scripts/build_all.py`. `validate.py` fails if a table is unregistered, a row cannot reach a canonical cause, or a row_id is not unique.

## Importing a run of the literature archive

`scripts/import_archive.py` does the three steps above for one extraction run of the literature archive, then publishes it:

```bash
.venv/bin/python scripts/import_archive.py <run folder | topic folder | extraction table>
```

It picks the latest version of the run's extraction table, checks its 29 columns, works out the analyte and the interferent (asking for anything it cannot work out: it never invents a name, a concept or an APS), copies the table into `<analyte>/database/`, registers it in `scripts/registry.py`, removes rows without evidence, rebuilds and validates. If anything fails, every change is undone. It then shows a summary and asks before it commits and pushes. Only the CSV is copied; PDFs and other archive files stay where they are. `--dry-run` shows the plan without changing anything; `--no-push` stops before the commit.

## The website

<https://hikmetc.github.io/c-led-database/> is a static site in `site/` (SvelteKit), deployed to GitHub Pages by `.github/workflows/pages.yml` on every push that changes the data, the scripts or the site. The workflow rebuilds the data layer from the CSVs, builds the site from it, runs the unit and end-to-end tests, and deploys. Nothing generated is committed.

How it works: the pages are prerendered and readable without JavaScript. The browser reads the Parquet files directly with a small JavaScript Parquet reader (hyparquet) and does all filtering, counting and charting in memory, so a chart needs only the analyte's own file (20-90 kB) and no database engine has to be downloaded first. Files above 4 MB are read over HTTP range requests instead of whole. The site makes no third-party request and uses no analytics or cookies. Everything is driven by `parquet/manifest.json`: a new analyte appears on the site with no code change.

Local development (build the data layer first, see above):

```bash
cd site && npm ci && npm run dev    # http://localhost:5173
npm run test                       # unit tests
npm run build && npm run build:growth && npx playwright test   # end-to-end tests
```

## Using the data in a website

The site publishes only the **web deploy set**: `build/parquet/` plus `analytes.json`, `interferents.json` and `stats.json`. `scripts/validate.py` fails the build if that set exceeds 900 MB (GitHub Pages sites may not exceed 1 GB) and warns from 500 MB.

- **Engine.** Any Parquet reader works. This site uses hyparquet, a small JavaScript reader, because DuckDB-WASM is a download of about 8 MB before the first query; DuckDB-WASM remains a good choice for ad-hoc SQL over the same files. Parquet is columnar and zstd-compressed, so a query fetches only the columns and row groups it needs over HTTP range requests: a row count reads only the file footer, and opening one evidence row reads one row group of the detail file.
- **Which file.** Overview and cross-analyte views: `slim_all.parquet`. An analyte page: `slim/<analyte_id>.parquet`. The row drawer or a row permalink: `detail/<analyte_id>.parquet` joined on `row_id`. `manifest.json` lists every file, so the site never hard-codes analyte ids.
- **Facets.** Filter on `analyte_id`, `interferent_id`, `concept`, `direction`, `aps_verdict`, and the four appraisal fields. Never filter on the verbatim `Analyte` or `Interferent` text: the same cause is worded many different ways across papers, which is exactly what `interferent_synonyms.csv` resolves.
- **Cross-analyte view.** `concept` is shared across analytes, so "show every analyte affected by hemolysis" is one query on `concept='hemolysis'`.
- **Search.** Match the user's words against `interferent_canonical`, `interferent_verbatim`, `platform`, `analyzer` and `sample_type` in `slim_all.parquet`; search the long verbatim text in `detail/` only for the analyte in view.
- **Custom APS.** Each row carries `pct_change` (percent, signed) and the analyte's `aps_percent`, plus `exceeds_aps` precomputed for the selected APS. To honour a user-supplied APS, recompute `abs(pct_change) > user_aps` client-side; fall back to the `aps_verdict` string when `pct_change` is null.
- **Charts.** Only 6,607 of 11,949 rows (55%) carry a numeric effect size, because many sources report an effect only in words or only in absolute units. Use the `plottable` flag to decide whether to draw: render a chart from the plottable subset and show the remainder as an evidence list. Never treat a missing value as zero.
- **Column names.** Parquet uses snake_case; `meta/data_dictionary.csv` gives the `parquet_column` of every source column.

## Reference coverage

| reference_status | Rows | Meaning |
|---|---|---|
| `doi` | 6,177 | DOI present |
| `pmid` | 1,223 | no DOI, PubMed ID present |
| `reference_only` | 4,549 | no DOI or PubMed ID, full bibliographic reference present |
| `citation_only` | 0 | author and year only |
| `unidentified` | 0 | none of the above; listed in `meta/known_gaps.csv` |

Full-text PDFs are **not** distributed: they are publisher copyright. Every row instead carries a DOI, a PubMed ID or a full reference so the source can be retrieved at its publisher.

## Data dictionary

| # | Column | Parquet column | Type | Values |
|---|---|---|---|---|
| 1 | Analyte | `analyte_verbatim` | string | verbatim |
| 2 | Interferent | `interferent_verbatim` | string | verbatim |
| 3 | Platform/Brand/Method | `platform_brand_method` | string | verbatim |
| 4 | Analyzer/Instrument | `analyzer_instrument` | string | verbatim |
| 5 | Assay generation/version | `assay_generation_version` | string | verbatim |
| 6 | Direction of effect | `direction_of_effect` | enum | up / down / no change / not reported |
| 7 | Direction (study criterion) | `direction_study_criterion` | enum | up / down / no change / not reported |
| 8 | Direction (user APS) | `direction_user_aps` | enum | up / down / no change / not reported |
| 9 | Interferent concentration (exact, with units) | `interferent_concentration_exact_with_units` | string | verbatim, units embedded |
| 10 | Baseline analyte concentration | `baseline_analyte_concentration` | string | verbatim, units embedded |
| 11 | Final analyte concentration | `final_analyte_concentration` | string | verbatim, units embedded |
| 12 | Absolute change (as reported) | `absolute_change_as_reported` | string | verbatim, units embedded |
| 13 | Percentage change (as reported) | `percentage_change_as_reported` | string | number or text |
| 14 | Absolute change (calculated) | `absolute_change_calculated` | string | number or text |
| 15 | Percentage change (calculated) | `percentage_change_calculated` | number | percent |
| 16 | Magnitude of change (verbatim from source) | `magnitude_of_change_verbatim_from_source` | string | verbatim |
| 17 | Significant-bias threshold | `significant_bias_threshold` | string | verbatim |
| 18 | Clinical significance vs user APS | `clinical_significance_vs_user_aps` | string | verbatim, contains the verdict |
| 19 | Sample type | `sample_type` | string | verbatim |
| 20 | Study method details | `study_method_details` | string | verbatim |
| 21 | Physiologically realistic concentration? | `physiologically_realistic_concentration` | enum | Yes / Partial / Borderline / Unclear / not reported |
| 22 | Study design appropriate? | `study_design_appropriate` | enum | Appropriate / Partially appropriate / Inappropriate / Unclear / not reported |
| 23 | Clinically significant effect? | `clinically_significant_effect` | enum | Yes / No / Partial / Unclear / not reported |
| 24 | Real-world conditions reflected? | `real_world_conditions_reflected` | enum | Yes / No / Partial / Unclear / not reported |
| 25 | Additional sources of bias | `additional_sources_of_bias` | string | verbatim |
| 26 | Notes | `notes` | string | verbatim |
| 27 | Citation | `citation` | string | verbatim |
| 28 | Full reference (from PDF) | `full_reference_from_pdf` | string | verbatim |
| 29 | doi | `doi_as_printed` | string | DOI or 'not reported in the information source' |

Full definitions: `meta/data_dictionary.csv`.

## Conventions

- Analyte naming follows the IFCC/IUPAC System-Component convention (`meta/analytes.csv` carries component, system, kind of property and unit); the verbatim spelling used by each paper is kept in `analyte_verbatim`.
- `row_id` is `<analyte_id>.<table stem>.<row number in that table>` and is stable as long as rows are appended rather than inserted.
- `Significant-bias threshold` is the **source study's** own criterion. The database APS is separate and lives in `meta/analytes.csv`. Do not conflate them.
- Direction is normalised to `up`, `down`, `none`, `not_reported`.
- The database is English-only; source quotations are kept verbatim.

