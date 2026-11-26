# -*- coding: utf-8 -*-
"""Rule: a row that carries no value in any of the 11 data fields is not evidence.
Such rows are removed from the evidence tables and archived in meta/removed_rows.csv."""
import csv, glob, os, sys
ROOT = sys.argv[1]
csv.field_size_limit(10 ** 7)
DATA = ["Direction of effect", "Percentage change (calculated)", "Percentage change (as reported)",
        "Absolute change (as reported)", "Absolute change (calculated)",
        "Magnitude of change (verbatim from source)", "Baseline analyte concentration",
        "Final analyte concentration", "Interferent concentration (exact, with units)",
        "Platform/Brand/Method", "Analyzer/Instrument"]
def empty(v):
    v = (v or "").strip().lower()
    return (not v) or v.startswith("not reported") or v.startswith("not comput")

removed, hdr, emptied = [], None, []
for f in sorted(glob.glob(os.path.join(ROOT, "*", "database", "*.csv"))):
    rel = os.path.relpath(f, ROOT)
    with open(f, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh); hdr = rd.fieldnames; rows = list(rd)
    keep, drop = [], []
    for i, r in enumerate(rows, 2):
        if not any((v or "").strip() for v in r.values()): continue
        (drop if all(empty(r.get(c)) for c in DATA) else keep).append((i, r))
    if not drop: continue
    for i, r in drop:
        removed.append(dict(source_file=rel, original_row=i,
                            reason="no value in any of the 11 data fields: the cited source "
                                   "supplied no interference evidence for this analyte", **r))
    if keep:
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=hdr); w.writeheader()
            w.writerows([r for _, r in keep])
        print(f"  {rel}: removed {len(drop)}, kept {len(keep)}")
    else:
        os.remove(f); emptied.append(rel)
        print(f"  {rel}: ALL {len(drop)} rows removed -> table deleted")

if removed:
    out = os.path.join(ROOT, "meta", "removed_rows.csv")
    prev = []
    if os.path.exists(out):
        prev = list(csv.DictReader(open(out, encoding="utf-8")))
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_file", "original_row", "reason"] + hdr)
        w.writeheader(); w.writerows(prev + removed)
print("removed:", len(removed), "| tables emptied:", emptied)
