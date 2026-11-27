# Database manager

A small desktop app for the maintainer. It shows what the database holds in its three places and
lets you change it, always after a review:

- **This Mac** - the repository folder (the working copy; every change is a local commit).
- **GitHub** - `origin/main`.
- **Website** - what the deployed site currently shows.

## What it does

| Section | What you can do |
|---|---|
| Overview | Row, analyte and table counts in the three places, whether they agree, the state of the last website build |
| Research | Start a literature search and extraction for an analyte, an interferent and an APS, follow it, stop it, continue an unfinished run |
| New from archive | Every run of the literature archive with its status: not in the database, newer than the database, in the database, cannot be imported. Import or update a run |
| Database | Browse analytes, tables and rows. Change values, delete rows, add a row, delete a table. Edit an analyte (name, system, unit, kind of property, APS, synonyms), delete an analyte, rename an interference cause or move it to another concept |
| Screening | Check the whole database, one table, or a run before import against the rejection criteria; see why each row fails; reject after confirmation |
| Unpublished changes | What is saved on this Mac but not on GitHub. Publish, or discard |
| Settings | The archive folder |

## How a change happens

1. You ask for a change. Nothing is touched yet.
2. The app shows a **plan**: exactly what will change, the warnings (for example row ids that
   shift when rows are deleted), and where it takes effect. You confirm or cancel.
3. On confirmation the change is made as a transaction: edit, rebuild, validate, audit, then a
   **local commit** (the local backup). If any step fails, every file is restored.
4. GitHub and the website change only when you choose **Publish**, which is planned and confirmed
   the same way. Publishing pushes to GitHub; GitHub then rebuilds the data and the website and
   runs the tests, and the app waits and reports the result.

Importing uses `scripts/import_archive.py`, so the same rules apply as on the command line.

## Research

The research itself is not done by the manager. It is done by Claude Code with the maintainer's
own pipeline skill (`laboratory-interference-pipeline`): PubMed and Crossref search and screening,
full-text download through Firefox with the Full-Text Fetcher extension, PDF-to-Markdown
conversion, extraction of the 29-column table, and the report, all written into the literature
archive. The manager starts that session unattended, shows what it is doing, and can stop it.

What it needs, and checks before it starts:

- Claude Code, as shipped with the Claude desktop app, signed in to your account;
- the `pubmed-search` and `crossref-search` servers defined for the Claude desktop app;
- the archive tool in the archive folder (`_system/tools/literature_archive.py`);
- Firefox open, signed in with institutional access, with the extension watching the queue
  (you do this yourself; the manager only reports whether Firefox has answered recently);
- the PDF to Markdown converter (optional: without it the PDFs are read directly).

What the unattended session is allowed to do: read and write files, use the two search servers,
and run a short list of shell commands (`python3`, `sleep`, `ls`, `cat`, `head`, `tail`, `grep`,
`wc`, `find`, `mkdir`, `cp`, `date`, `echo`, `pdftotext`, `pdftoppm`, `pdfinfo`). It has no other
web access and cannot use git. It runs in the archive folder and never touches the database:
a finished run appears under "New from archive" and goes through screening and import there.

The model is chosen in the form. The list is not fixed: it is read from the installed Claude
Code program, which names every model it knows, so it follows the Claude desktop app's updates.
"Check which models work" asks each model for a one-word answer through your account and marks
the ones that do not answer; those cannot be chosen.

The session uses your Claude account and its usage. It keeps running if you close the manager,
and is shown again when you come back. Its log is kept under
`~/Library/Application Support/EFLM-LED-Manager/research/`.

## Inclusion screening

Before a run is imported, and on demand for any table, every row is checked against the
rejection criteria of `scripts/screening.py`:

| # | Criterion | Decided |
|---|---|---|
| 1 | Not enough information to find the source: no DOI, no PubMed ID, no full reference, and a citation without an author and a year | automatically |
| 2 | No citation | automatically |
| 3 | No value in any of the 11 data fields | automatically |
| 4 | The source did not measure this analyte | by hand |
| 5 | The cited file is not the article | by hand |
| 6 | The table does not have the 29 columns | at import (whole table) |
| 7 | A row reaches no canonical interference cause | by the build |
| 8 | Duplicate of another row: same source, platform, analyzer, concentrations and values | automatically |
| 9 | The DOI is malformed, or doi.org does not know it (optional online check) | automatically |
| 10 | Out of scope: not analytical interference or pre-analytical error | by hand |
| 17 | The recorded APS verdict contradicts the numeric change (a change exactly equal to the APS is not a contradiction) | automatically |

The screening sheet lists every rejected row with the criterion and the concrete reason (for
example which row it duplicates, or the two numbers that disagree). You can untick a row to keep
it, and for the criteria that only a person can judge the app lists the rows worth looking at
and you choose the reason. Nothing is rejected until you confirm the plan. Rows that pass go
into the database folder; every rejected row is written in full, with its criteria, reason, date
and whether it was decided automatically or by hand, to `meta/rejected_rows.csv`.

Criterion 17 needs judgement for an analyte whose APS is read as an absolute difference in some
sources (the screening shows the analyte's APS note in that case).

## Limits

- An analyte's folder name and id prefix, and a cause's key, cannot be changed: every row id and
  every website address depends on them.
- A published change cannot be withdrawn from the app. It stays in the public git history.
- The app works on the repository folder it was built for. The archive is only read.
  Full-text PDFs are never copied.

## Build and run

```bash
manager/build_app.sh            # builds ~/Applications/EFLM Database Manager.app
```

Needs the Xcode command line tools (`swiftc`) and the project's Python environment (`.venv` with
`pip install -r requirements.txt`). Run the script again if the repository folder is moved.
If the back end stops while the app is open, the app starts it again and reloads by itself.

## Tests

```bash
manager/tests/run.sh                                   # every operation, in a throwaway clone
"$HOME/Applications/EFLM Database Manager.app/Contents/MacOS/Manager" --selftest          # the built app
"$HOME/Applications/EFLM Database Manager.app/Contents/MacOS/Manager" --selftest-restart  # recovery
```

`run.sh` clones the repository with its own origin, archive and settings, drives the interface
through every operation (edit, delete, add, screen, reject, import of a new cause and of a new
analyte, analyte and cause changes, table and analyte deletion, publish, update, discard) and
checks the repository after each step; a second pass forces the build to fail and checks that
everything is undone. `--selftest` opens every section of the built app in its real window and
changes nothing; `--selftest-restart` also stops the back end on purpose and expects the app to
recover. Set `PW_CHANNEL=chrome` to use an installed Chrome.

Without building the app, the same interface runs in a browser:

```bash
.venv/bin/python manager/server.py     # prints the address to open
```

## Parts

- `server.py` - the local back end: Python standard library only, bound to 127.0.0.1, every
  request needs the session token. It plans, applies and publishes changes.
- `ui/` - the interface: plain HTML, CSS and JavaScript, no dependencies, no network.
- `macos/Main.swift` - a native window (WKWebView) that starts the back end and stops it on quit.
