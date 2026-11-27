#!/usr/bin/env python3
"""A small literature archive for the manager tests, made from rows of the repository under test.
Usage: make_archive.py <repo> <archive dir>"""
import csv, glob, json, os, sys

repo, out = sys.argv[1], sys.argv[2]
csv.field_size_limit(10 ** 7)
src = sorted(glob.glob(os.path.join(repo, "potassium_serum", "database", "*.csv")))[0]
rows = list(csv.reader(open(src, encoding="utf-8-sig", newline="")))
hdr, data = rows[0], rows[1:]
col = hdr.index


def run(topic, stamp, run_id, analyte, interferent, aps, table_rows, version="", header=None):
    d = os.path.join(out, topic, stamp)
    os.makedirs(os.path.join(d, "04_extraction"), exist_ok=True)
    json.dump({"run_id": run_id, "analyte": analyte, "interferent": interferent, "aps": {"text": f"%{aps}", "percent": aps},
               "created": "2026-11-27T10:00:00+03:00", "scope": {"interferent_original": interferent.capitalize()},
               "folder": {"topic": topic}}, open(os.path.join(d, "00_parameters.json"), "w"))
    with open(os.path.join(d, "04_extraction", f"{run_id}_extraction_table{version}.csv"), "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([header or hdr] + table_rows)


def variant(r, tag):
    r = list(r)
    r[col("Notes")] = f"{r[col('Notes')]} [{tag}]"
    r[col("Baseline analyte concentration")] = f"{r[col('Baseline analyte concentration')]} [{tag}]"   # a different result, not a duplicate
    return r


# 1. a new analyte, with rows that the screening must reject:
#    a duplicate (8), a row without evidence (3), a row without a findable source (1),
#    a row whose verdict contradicts its number (17)
good = [variant(r, f"mg {i}") for i, r in enumerate(data[:8])]
for r in good:
    r[col("Analyte")] = "Magnesium (serum)"
    r[col("Percentage change (calculated)")] = "12.0"
    r[col("Clinical significance vs user APS")] = "Significant - exceeds user APS 4%"
dup = list(good[0])
empty = list(good[1])
for c in ("Direction of effect", "Percentage change (calculated)", "Percentage change (as reported)", "Absolute change (as reported)",
          "Absolute change (calculated)", "Magnitude of change (verbatim from source)", "Baseline analyte concentration",
          "Final analyte concentration", "Interferent concentration (exact, with units)", "Platform/Brand/Method", "Analyzer/Instrument"):
    empty[col(c)] = "not reported in the information source"
empty[col("Notes")] = "no evidence row"
nosrc = variant(good[2], "no source")
nosrc[col("Citation")] = "file_1234.pdf"
nosrc[col("Full reference (from PDF)")] = "not reported in the information source"
nosrc[col("doi")] = "not reported in the information source"
bad_verdict = variant(good[3], "verdict")
bad_verdict[col("Percentage change (calculated)")] = "1.0"
run("magnesium__hemolysis", "2026-11-27_1000__APS-4", "magnesium_hemolysis_20261127-1000_APS4", "Magnesium", "hemolysis", 4.0,
    good + [dup, empty, nosrc, bad_verdict])

# 2. a new cause for an existing analyte
run("potassium__testcause", "2026-11-27_1100__APS-0.4", "potassium_testcause_20261127-1100_APS0.4", "Potassium", "test cause", 0.4,
    [variant(r, f"tc {i}") for i, r in enumerate(data[:5])])

# 3. a table with the wrong columns: must be refused
run("potassium__badheader", "2026-11-27_1200__APS-0.4", "potassium_badheader_20261127-1200_APS0.4", "Potassium", "bad header", 0.4,
    [["a", "b"]], header=["x", "y"])

# 4. a run without an extraction table
os.makedirs(os.path.join(out, "potassium__empty", "2026-11-27_1300__APS-0.4", "04_extraction"), exist_ok=True)
print("test archive:", out)
