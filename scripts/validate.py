#!/usr/bin/env python3
"""Integrity checks for the C-LED database. Exits non-zero on failure."""
import csv, glob, json, os, re, sqlite3, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
import registry as R

csv.field_size_limit(10 ** 7)
fail, warn = [], []
pdf_local = 0

# 0. analyte folders on disk that the registry does not know about
on_disk_analytes = sorted(
    d for d in os.listdir(ROOT)
    if os.path.isdir(os.path.join(ROOT, d))
    and glob.glob(os.path.join(ROOT, d, "database", "*.csv")))
for d in on_disk_analytes:
    if d not in R.ANALYTES:
        fail.append(
            f"analyte folder '{d}' holds evidence tables but is not registered. "
            f"Add it to ANALYTES, CANON and TABLE_MAP in scripts/registry.py "
            f"(see 'Adding an analyte' in README.md), then rebuild.")
for d in R.ANALYTES:
    if not os.path.isdir(os.path.join(ROOT, d)):
        fail.append(f"analyte '{d}' is registered but has no folder on disk")

# 1. every evidence table shares the same 29-column header
heads, tables = set(), sorted(glob.glob(os.path.join(ROOT, "*", "database", "*.csv")))
for f in tables:
    if open(f, "rb").read(3) == b"\xef\xbb\xbf":
        warn.append(f"UTF-8 BOM in {os.path.relpath(f, ROOT)} - strip it, it breaks the first column name for CSV readers")
    with open(f, newline="", encoding="utf-8-sig") as fh:
        heads.add(tuple(next(csv.reader(fh))))
if len(heads) != 1:
    fail.append(f"evidence tables use {len(heads)} different headers")
dict_cols = [r["column"] for r in csv.DictReader(
    open(os.path.join(ROOT, "meta", "data_dictionary.csv"), encoding="utf-8"))]
if heads and list(next(iter(heads))) != dict_cols:
    fail.append("data_dictionary.csv does not match the evidence table header")

# 2. every table is registered, every registered table exists
for a in R.TABLE_MAP:
    on_disk = {os.path.basename(p) for p in glob.glob(os.path.join(ROOT, a, "database", "*.csv"))}
    registered = set(R.TABLE_MAP[a])
    for t in on_disk - registered: fail.append(f"{a}: table not in registry: {t}")
    for t in registered - on_disk: fail.append(f"{a}: registered table missing on disk: {t}")

# 3. every canonical id referenced by the registry exists
for a, m in R.TABLE_MAP.items():
    for t, i in m.items():
        if i not in R.CANON[a]: fail.append(f"{a}/{t}: unknown interferent id {i}")
for a, m in R.OVERRIDES.items():
    for t, rules in m.items():
        for rx, i in rules:
            if i not in R.CANON[a]: fail.append(f"{a}/{t}: unknown override id {i}")

# 4. every row reaches a canonical interferent, and references are present
db = os.path.join(ROOT, "build", "cled.sqlite")
if os.path.exists(db):
    con = sqlite3.connect(db)
    n, = con.execute("SELECT count(*) FROM evidence").fetchone()
    orphan, = con.execute(
        "SELECT count(*) FROM evidence e LEFT JOIN interferent i"
        " USING(interferent_id) WHERE i.interferent_id IS NULL").fetchone()
    noref, = con.execute(
        "SELECT count(*) FROM evidence WHERE reference_status='unidentified'").fetchone()
    noid, = con.execute("SELECT count(*) FROM evidence WHERE row_id IS NULL OR row_id=''").fetchone()
    dupe, = con.execute("SELECT count(*) FROM (SELECT row_id FROM evidence"
                        " GROUP BY row_id HAVING count(*)>1)").fetchone()
    if orphan: fail.append(f"{orphan} evidence rows point to an unknown interferent_id")
    if noid:   fail.append(f"{noid} evidence rows have no row_id")
    if dupe:   fail.append(f"{dupe} row_id values are not unique")
    if noref:  warn.append(f"{noref} rows carry no DOI, PMID, full reference or author/year citation"
                           " (listed in meta/known_gaps.csv)")
    csv_rows = 0
    for f in tables:
        with open(f, newline="", encoding="utf-8-sig") as fh:
            csv_rows += sum(1 for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values()))
    if csv_rows != n: fail.append(f"build has {n} rows but the CSVs hold {csv_rows}")
    print(f"evidence rows: {n} (matches the CSVs)")
    con.close()
else:
    warn.append("build/cled.sqlite not found - run scripts/build_all.py first")

# 5. file-name portability and no stray PDFs in the repo
for dp, dn, fn in os.walk(ROOT):
    if ".git" in dp or os.sep + "build" in dp: continue
    for f in fn:
        rel = os.path.relpath(os.path.join(dp, f), ROOT)
        if " " in rel or any(ord(c) > 127 for c in rel) or re.search(r'[<>:"\\|?*]', rel):
            fail.append(f"non-portable path: {rel}")
        if len(rel) > 180: warn.append(f"path longer than 180 characters: {rel}")
        if f.lower().endswith(".pdf"):
            if any(os.sep + d + os.sep in os.sep + rel
                   for d in ("fulltext_pdfs", "analyte_level", "other_formats")):
                pdf_local += 1          # local full-text library: expected, and gitignored
            else:
                fail.append(f"PDF outside fulltext_pdfs (would be committed): {rel}")

# 6. growth guards: no single evidence table may approach GitHub's 100 MiB file limit
MiB = 1024 * 1024
for f in sorted(glob.glob(os.path.join(ROOT, "*", "database", "*.csv"))):
    size = os.path.getsize(f)
    rel = os.path.relpath(f, ROOT)
    if size > 90 * MiB:
        fail.append(f"{rel} is {size/MiB:.0f} MiB; GitHub rejects files over 100 MiB. "
                    "Split the table (for example by publication year or sub-group).")
    elif size > 50 * MiB:
        warn.append(f"{rel} is {size/MiB:.0f} MiB; split it before it reaches 90 MiB")

# 7. the Parquet web layer: present, complete, consistent with the evidence, and small
#    enough to publish (GitHub Pages sites may not exceed 1 GB)
import parquet_export as PX
build_dir = os.path.join(ROOT, "build")
pq_dir = os.path.join(build_dir, "parquet")
man_path = os.path.join(pq_dir, "manifest.json")
require_pq = os.environ.get("CLED_REQUIRE_PARQUET") == "1"
if os.path.exists(man_path):
    man = json.load(open(man_path, encoding="utf-8"))
    if os.path.exists(db):
        _c = sqlite3.connect(db)
        n_ev, = _c.execute("SELECT count(*) FROM evidence").fetchone()
        _c.close()
        if man.get("row_count") != n_ev:
            fail.append(f"Parquet layer holds {man.get('row_count')} rows but the evidence has {n_ev}; "
                        "it is stale - rebuild")
    files = man.get("files", {})
    s_rows = sum(v["rows"] for v in files.get("slim", {}).values())
    d_rows = sum(v["rows"] for v in files.get("detail", {}).values())
    if not (s_rows == d_rows == man.get("row_count") == (files.get("slim_all") or {}).get("rows")):
        fail.append(f"Parquet row counts disagree: slim {s_rows}, detail {d_rows}, "
                    f"slim_all {(files.get('slim_all') or {}).get('rows')}, manifest {man.get('row_count')}")
    for group in ("slim", "detail"):
        for aid, meta_ in files.get(group, {}).items():
            if not os.path.exists(os.path.join(build_dir, meta_["path"])):
                fail.append(f"Parquet file listed in the manifest is missing: {meta_['path']}")
    if set(files.get("slim", {})) != {d["prefix"] for d in R.ANALYTES.values()}:
        fail.append("Parquet layer does not hold exactly one slim file per registered analyte")
    try:
        import pyarrow.parquet as pq
        ids = pq.read_table(os.path.join(build_dir, "parquet", "slim_all.parquet"),
                            columns=["row_id"]).column("row_id").to_pylist()
        if len(ids) != len(set(ids)):
            fail.append("row_id is not unique in parquet/slim_all.parquet")
        for group in ("slim", "detail"):
            for aid, meta_ in files.get(group, {}).items():
                real = pq.read_metadata(os.path.join(build_dir, meta_["path"])).num_rows
                if real != meta_["rows"]:
                    fail.append(f"{meta_['path']} holds {real} rows, manifest says {meta_['rows']}")
    except ImportError:
        pass                                   # deep checks need pyarrow; CI always has it
    dep = PX.deploy_set(build_dir)
    dep_bytes = sum(os.path.getsize(os.path.join(build_dir, p)) for p in dep)
    if dep_bytes > 900e6:
        fail.append(f"web deploy set is {dep_bytes/1e6:.0f} MB; GitHub Pages sites may not exceed 1 GB")
    elif dep_bytes > 500e6:
        warn.append(f"web deploy set is {dep_bytes/1e6:.0f} MB; plan for object storage before 900 MB")
    print(f"parquet web layer: {man.get('row_count')} rows, deploy set {dep_bytes/1e6:.2f} MB "
          f"({len(dep)} files)")
elif require_pq:
    fail.append("CLED_REQUIRE_PARQUET=1 but build/parquet/manifest.json is missing")
else:
    print("note: Parquet web layer not present locally (needs pyarrow); CI builds it")

if pdf_local:
    print(f"note: {pdf_local} local-only PDFs present (fulltext_pdfs / analyte_level / other_formats); .gitignore keeps them out of git")
if os.environ.get("CLED_DISTRIBUTION") == "1" and pdf_local:
    fail.append("CLED_DISTRIBUTION=1 but local-only PDFs are present - the distributed repo must carry none")

for w in warn: print("WARN:", w)
for f_ in fail: print("FAIL:", f_)
print(("FAILED: %d problem(s)" % len(fail)) if fail else "all checks passed")
sys.exit(1 if fail else 0)
