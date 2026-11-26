# -*- coding: utf-8 -*-
import csv, glob, json, os, sqlite3, sys, collections

def gen(root, distributed):
    META = os.path.join(root, "meta"); BUILD = os.path.join(root, "build")
    an = json.load(open(os.path.join(META, "analytes.json"), encoding="utf-8"))
    inter = list(csv.DictReader(open(os.path.join(META, "interferents.csv"), encoding="utf-8")))
    st = json.load(open(os.path.join(BUILD, "stats.json"), encoding="utf-8"))
    dd = list(csv.DictReader(open(os.path.join(META, "data_dictionary.csv"), encoding="utf-8")))
    con = sqlite3.connect(os.path.join(BUILD, "cled.sqlite"))
    rows = con.execute("SELECT count(*) FROM evidence").fetchone()[0]
    refs = con.execute("SELECT count(*) FROM reference_").fetchone()[0]
    tot_int = sum(a["interferent_count"] for a in an)
    tables = sum(a["evidence_tables"] for a in an)
    with_id = con.execute("SELECT count(*) FROM evidence WHERE doi IS NOT NULL OR pmid IS NOT NULL").fetchone()[0]
    plott = sum(st["plottable_by_analyte"].values())

    # ---------------- per-analyte markdown ----------------
    for a in an:
        k = a["analyte_folder"]
        ints = [i for i in inter if i["analyte_folder"] == k and int(i["evidence_rows"]) > 0]
        ints.sort(key=lambda i: -int(i["evidence_rows"]))
        q = con.execute("SELECT count(*), sum(plottable), sum(aps_verdict='exceeds'),"
                        " sum(aps_verdict='within'), sum(doi IS NOT NULL), sum(pmid IS NOT NULL)"
                        " FROM evidence WHERE analyte_folder=?", (k,)).fetchone()
        L = [f"# {a['component']} ({a['system']})", "",
             "## Analyte", "",
             f"- **Component:** {a['component']}",
             f"- **System (matrix):** {a['system']}",
             f"- **Kind of property:** {a['kind_of_property']}",
             f"- **Reporting unit:** {a['unit']}",
             f"- **Analyte id:** `{a['analyte_id']}`",
             f"- **Other spellings in the literature:** {a['synonyms']}", "",
             "## Analytical performance specification", "",
             f"- **Selected APS:** {a['aps_percent']}% ({a['aps_type']})"]
        if a["aps_note"]: L.append(f"- **Note:** {a['aps_note']}")
        L += ["",
             f"Every row was judged against this APS. The machine-readable record is "
             f"`{k}_analyte.csv`; the derived build also carries `pct_change` per row, so a site can "
             f"re-judge every row against a user-supplied APS instead of this one.", "",
             "## Contents", "",
             f"| | |", "|---|---|",
             f"| Interference causes | {len(ints)} |",
             f"| Evidence tables | {a['evidence_tables']} |",
             f"| Evidence rows | {q[0]:,} |",
             f"| Rows with a numeric percent change (plottable) | {q[1]:,} |",
             f"| Rows exceeding the {a['aps_percent']}% APS | {q[2]:,} |",
             f"| Rows within the {a['aps_percent']}% APS | {q[3]:,} |",
             f"| Rows with a DOI | {q[4]:,} |",
             f"| Rows with a PubMed ID | {q[5]:,} |", "",
             "## Interference causes", "",
             "| interferent_id | Interferent | Concept | Rows |", "|---|---|---|---|"]
        for i in ints:
            L.append(f"| `{i['interferent_id']}` | {i['interferent_canonical']} | "
                     f"`{i['concept']}` | {i['evidence_rows']} |")
        L += ["", "## Files", "",
              f"- `{k}_analyte.csv` - the analyte record: component, system, unit, selected APS.",
              f"- `{k}_interferent_list.csv` - the {len(ints)} interference causes, with ids and concepts.",
              "- `database/` - the source evidence tables, one CSV per interferent, "
              "all sharing the same 29 columns (see `meta/data_dictionary.csv`)."]
        if not distributed:
            pdfs = sorted(glob.glob(os.path.join(root, k, "fulltext_pdfs", "*")))
            npdf = len(glob.glob(os.path.join(root, k, "fulltext_pdfs", "*", "*.pdf")))
            L.append(f"- `fulltext_pdfs/` - {npdf} full-text PDFs in {len(pdfs)} interferent "
                     "subfolders. Local only: not distributed and excluded by `.gitignore`.")
            al = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, k, "analyte_level", "*")))
            of = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, k, "other_formats", "*")))
            if al: L.append("- `analyte_level/` - working interferent lists and APS documents (local only): "
                            + ", ".join(f"`{x}`" for x in al))
            if of: L.append("- `other_formats/` - non-CSV source files (local only): "
                            + ", ".join(f"`{x}`" for x in of))
        L.append("")
        open(os.path.join(root, k, f"{k}.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    # ---------------- README ----------------
    name = "c-led-database" if distributed else "c-led database (local working copy)"
    R = [f"# C-LED Database", "",
     "**C**linical **L**aboratory **E**rror **D**atabase - structured, source-cited evidence on how "
     "interferents bias clinical laboratory measurements, judged against an analytical performance "
     "specification (APS) for each analyte.", "",
     "| | |", "|---|---|",
     f"| Analytes | {len(an)} |",
     f"| Interference causes | {tot_int} |",
     f"| Evidence tables (CSV) | {tables} |",
     f"| Evidence rows | {rows:,} |",
     f"| Rows with a numeric effect size | {plott:,} |",
     f"| Distinct references | {refs:,} |",
     f"| Rows with a DOI or PubMed ID | {with_id:,} |",
     "", "## Analytes", "",
     "| Folder | Component | System | Unit | APS | Causes | Tables | Rows |", "|---|---|---|---|---|---|---|---|"]
    for a in an:
        R.append(f"| `{a['analyte_folder']}` | {a['component']} | {a['system']} | {a['unit']} | "
                 f"{a['aps_percent']}% | {a['interferent_count']} | {a['evidence_tables']} | {a['evidence_rows']:,} |")
    R += ["", "## Layout", "", "```", ("c-led-database/" if distributed else "c-led database/"),
     "|-- README.md",
     "|-- meta/                        registries and vocabulary (committed, small)",
     "|   |-- analytes.csv/.json       one record per analyte: component, system, unit, APS",
     "|   |-- interferents.csv         canonical interference causes with stable ids",
     "|   |-- interferent_synonyms.csv every verbatim wording -> canonical id  (the join key)",
     "|   |-- table_index.csv          evidence table -> default interferent id",
     "|   |-- data_dictionary.csv/.json definition of all 29 source columns",
     "|   |-- references.csv           distinct references with DOI / PubMed ID",
     "|   |-- references_enriched.csv  references recovered outside the source tables, with provenance",
     "|   |-- known_gaps.csv           rows whose source carries no usable identifier",
     "|   `-- file_index.csv           one row per evidence table",
     "|-- scripts/                     the build: registry.py + build_*.py + validate.py",
     "|-- <analyte>/",
     "|   |-- <analyte>_analyte.csv    the analyte record (incl. the selected APS)",
     "|   |-- <analyte>_interferent_list.csv  this analyte's causes, with ids",
     "|   |-- <analyte>.md             human-readable summary",
     "|   `-- database/*.csv           the evidence tables (29 columns, never modified by the build)"]
    if not distributed:
        R += ["|   |-- fulltext_pdfs/         local-only full-text PDFs, one folder per interferent",
              "|   |-- analyte_level/         local-only working files",
              "|   `-- other_formats/         local-only non-CSV sources"]
    R += ["`-- build/                       GENERATED, never committed (see .gitignore)",
     "    |-- parquet/                 THE WEB LAYER - the only data the website publishes",
     "    |   |-- manifest.json        schema version, files, row counts, byte sizes, columns",
     "    |   |-- slim_all.parquet     every row, slim columns, sorted by analyte and interferent",
     "    |   |-- slim/<analyte_id>.parquet    table, filter and chart columns, per analyte",
     "    |   `-- detail/<analyte_id>.parquet  every source column, sorted by row_id, per analyte",
     "    |-- analytes.json interferents.json stats.json   small registries, also published",
     "    |-- cled.sqlite              internal: feeds the docs and the checks, never published",
     "    `-- slim/, evidence/, evidence_slim.json   legacy JSON, never published",
     "```", "",
     "## Build", "", "```bash",
     "pip install -r requirements.txt     # pyarrow, for the Parquet web layer",
     "python3 scripts/build_all.py        # rebuilds meta/ and build/ from the CSVs",
     "python3 scripts/validate.py         # integrity checks only",
     "```", "",
     "Without pyarrow the build still runs and skips the Parquet layer with a notice. CI sets "
     "`CLED_REQUIRE_PARQUET=1`, which makes a missing or inconsistent Parquet layer a hard failure.", "",
     "The source CSVs are the single source of truth and the build never writes to them. "
     "`build/` is regenerated from scratch each time and is **not committed**: it is produced by "
     "CI (`.github/workflows/build.yml`) on every push, uploaded as a workflow artifact, and "
     "attached to published releases. Committing it would add a fresh multi-megabyte blob to git "
     "history on every rebuild and would eventually hit GitHub's 100 MB per-file limit.", "",
     "## Adding an analyte", "",
     "1. Create `<analyte>/database/` and drop in the evidence tables, using the same 29 columns.",
     "2. Add the analyte to `ANALYTES`, its causes to `CANON`, and its tables to `TABLE_MAP` in "
     "`scripts/registry.py`. Add wording rules to `OVERRIDES` only for a table that genuinely "
     "covers several distinct causes.",
     "3. Run `python3 scripts/build_all.py`. `validate.py` fails if a table is unregistered, a row "
     "cannot reach a canonical cause, or a row_id is not unique.", "",
     "## Using the data in a website", "",
     "The site publishes only the **web deploy set**: `build/parquet/` plus `analytes.json`, "
     "`interferents.json` and `stats.json`. `scripts/validate.py` fails the build if that set "
     "exceeds 900 MB (GitHub Pages sites may not exceed 1 GB) and warns from 500 MB.", "",
     "- **Engine.** Read the Parquet files in the browser with DuckDB-WASM loaded from a CDN. "
     "Parquet is columnar and zstd-compressed, so a query fetches only the columns and row groups "
     "it needs over HTTP range requests: a row count reads only the file footer, and opening one "
     "evidence row reads one row group of the detail file.",
     "- **Which file.** Overview and cross-analyte views: `slim_all.parquet`. An analyte page: "
     "`slim/<analyte_id>.parquet`. The row drawer or a row permalink: "
     "`detail/<analyte_id>.parquet` joined on `row_id`. `manifest.json` lists every file, so the "
     "site never hard-codes analyte ids.",
     "- **Facets.** Filter on `analyte_id`, `interferent_id`, `concept`, `direction`, "
     "`aps_verdict`, and the four appraisal fields. Never filter on the verbatim `Analyte` or "
     "`Interferent` text: the same cause is worded many different ways across papers, which is "
     "exactly what `interferent_synonyms.csv` resolves.",
     "- **Cross-analyte view.** `concept` is shared across analytes, so \"show every analyte "
     "affected by hemolysis\" is one query on `concept='hemolysis'`.",
     "- **Search.** Match the user's words against `interferent_canonical`, "
     "`interferent_verbatim`, `platform`, `analyzer` and `sample_type` in `slim_all.parquet`; "
     "search the long verbatim text in `detail/` only for the analyte in view.",
     "- **Custom APS.** Each row carries `pct_change` (percent, signed) and the analyte's "
     "`aps_percent`, plus `exceeds_aps` precomputed for the selected APS. To honour a user-supplied "
     "APS, recompute `abs(pct_change) > user_aps` client-side; fall back to the `aps_verdict` "
     "string when `pct_change` is null.",
     f"- **Charts.** Only {plott:,} of {rows:,} rows ({plott*100//rows}%) carry a numeric effect "
     "size, because many sources report an effect only in words or only in absolute units. Use the "
     "`plottable` flag to decide whether to draw: render a chart from the plottable subset and show "
     "the remainder as an evidence list. Never treat a missing value as zero.",
     "- **Column names.** Parquet uses snake_case; `meta/data_dictionary.csv` gives the "
     "`parquet_column` of every source column.", "",
     "## Reference coverage", ""]
    rs = dict(con.execute("SELECT reference_status, count(*) FROM evidence GROUP BY 1").fetchall())
    R += ["| reference_status | Rows | Meaning |", "|---|---|---|",
     f"| `doi` | {rs.get('doi',0):,} | DOI present |",
     f"| `pmid` | {rs.get('pmid',0):,} | no DOI, PubMed ID present |",
     f"| `reference_only` | {rs.get('reference_only',0):,} | no DOI or PubMed ID, full bibliographic reference present |",
     f"| `citation_only` | {rs.get('citation_only',0):,} | author and year only |",
     f"| `unidentified` | {rs.get('unidentified',0):,} | none of the above; listed in `meta/known_gaps.csv` |",
     "", "Full-text PDFs are **not** distributed: they are publisher copyright. Every row instead "
     "carries a DOI, a PubMed ID or a full reference so the source can be retrieved at its "
     "publisher.", "",
     "## Data dictionary", "",
     "| # | Column | Parquet column | Type | Values |", "|---|---|---|---|---|"]
    for d in dd:
        R.append(f"| {d['position']} | {d['column']} | `{d.get('parquet_column', '')}` | {d['type']} | {d['values']} |")
    R += ["", "Full definitions: `meta/data_dictionary.csv`.", "",
     "## Conventions", "",
     "- Analyte naming follows the IFCC/IUPAC System-Component convention "
     "(`meta/analytes.csv` carries component, system, kind of property and unit); the verbatim "
     "spelling used by each paper is kept in `analyte_verbatim`.",
     "- `row_id` is `<analyte_id>.<table stem>.<row number in that table>` and is stable as long as "
     "rows are appended rather than inserted.",
     "- `Significant-bias threshold` is the **source study's** own criterion. The database APS is "
     "separate and lives in `meta/analytes.csv`. Do not conflate them.",
     "- Direction is normalised to `up`, `down`, `none`, `not_reported`.",
     "- The database is English-only; source quotations are kept verbatim.", ""]
    open(os.path.join(root, "README.md"), "w", encoding="utf-8").write("\n".join(R) + "\n")
    con.close()
    return rows, tot_int

if __name__ == "__main__":
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
    # "distributed" = no local-only PDF library present in this checkout
    dist = not glob.glob(os.path.join(ROOT, "*", "fulltext_pdfs"))
    r, i = gen(ROOT, dist)
    print(f"docs written for {'distributed' if dist else 'local'} tree: {r} rows, {i} causes")
