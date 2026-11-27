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
| New from archive | Every run of the literature archive with its status: not in the database, newer than the database, in the database, cannot be imported. Import or update a run |
| Database | Browse analytes, tables and rows. Change values, delete rows, add a row, delete a table |
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

## Limits

- Removing a whole analyte, changing an analyte's APS, unit or name, and renaming an interference
  cause are not done by the app. They are edits of `scripts/registry.py` (see STRUCTURE.md).
- A published change cannot be withdrawn from the app. It stays in the public git history.
- The app works on the repository folder it was built for. The archive is only read.
  Full-text PDFs are never copied.

## Build and run

```bash
manager/build_app.sh            # builds ~/Applications/EFLM Database Manager.app
```

Needs the Xcode command line tools (`swiftc`) and the project's Python environment (`.venv` with
`pip install -r requirements.txt`). Run the script again if the repository folder is moved.
`"…/EFLM Database Manager.app/Contents/MacOS/Manager" --selftest` checks that the window can load.

Without building the app, the same interface runs in a browser:

```bash
.venv/bin/python manager/server.py     # prints the address to open
```

## Parts

- `server.py` - the local back end: Python standard library only, bound to 127.0.0.1, every
  request needs the session token. It plans, applies and publishes changes.
- `ui/` - the interface: plain HTML, CSS and JavaScript, no dependencies, no network.
- `macos/Main.swift` - a native window (WKWebView) that starts the back end and stops it on quit.
