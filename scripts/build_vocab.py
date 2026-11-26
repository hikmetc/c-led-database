import csv, glob, re, collections
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
import registry as R

DST   = ROOT
META = os.path.join(DST, "meta"); os.makedirs(META, exist_ok=True)


# ---- registry structure check: catch hand-editing mistakes with a clear message ----
def _check_registry():
    probs = []
    for a, d in R.ANALYTES.items():
        for k in ("prefix", "component", "system", "kind_of_property", "unit", "aps_percent"):
            if k not in d: probs.append(f"ANALYTES['{a}'] is missing '{k}'")
        if not isinstance(d.get("aps_percent"), (int, float)):
            probs.append(f"ANALYTES['{a}']['aps_percent'] must be a number")
    pref = [d["prefix"] for d in R.ANALYTES.values() if "prefix" in d]
    for p in set(pref):
        if pref.count(p) > 1: probs.append(f"prefix '{p}' is used by more than one analyte")
    for a in R.ANALYTES:
        if a not in R.CANON: probs.append(f"CANON has no entry for analyte '{a}'")
        if a not in R.TABLE_MAP: probs.append(f"TABLE_MAP has no entry for analyte '{a}'")
    for a, m in R.CANON.items():
        if a not in R.ANALYTES: probs.append(f"CANON['{a}'] has no matching analyte in ANALYTES")
        for k, v in m.items():
            if not (isinstance(v, tuple) and len(v) == 2):
                probs.append(f"CANON['{a}']['{k}'] must be a (name, concept) pair")
    for a, m in R.TABLE_MAP.items():
        if a not in R.ANALYTES: probs.append(f"TABLE_MAP['{a}'] has no matching analyte in ANALYTES")
        for t, i in m.items():
            if not isinstance(i, str):
                probs.append(f"TABLE_MAP['{a}']['{t}'] must be an interferent key (a string)")
            elif i not in R.CANON.get(a, {}):
                probs.append(f"TABLE_MAP['{a}']['{t}'] points to unknown interferent key '{i}'")
    for a, m in R.OVERRIDES.items():
        if a not in R.ANALYTES: probs.append(f"OVERRIDES['{a}'] has no matching analyte in ANALYTES")
        for t, rules in m.items():
            if t not in R.TABLE_MAP.get(a, {}):
                probs.append(f"OVERRIDES['{a}']['{t}'] names a table that is not in TABLE_MAP")
            if not isinstance(rules, list):
                probs.append(f"OVERRIDES['{a}']['{t}'] must be a list of (regex, interferent key) "
                             f"pairs, got {type(rules).__name__}")
                continue
            for r_ in rules:
                if not (isinstance(r_, tuple) and len(r_) == 2):
                    probs.append(f"OVERRIDES['{a}']['{t}'] contains {r_!r}, which is not a "
                                 f"(regex, interferent key) pair")
                elif r_[1] not in R.CANON.get(a, {}):
                    probs.append(f"OVERRIDES['{a}']['{t}'] points to unknown key '{r_[1]}'")
    if probs:
        raise SystemExit("\nBUILD STOPPED: scripts/registry.py is not consistent:\n"
                         + "".join(f"  - {p}\n" for p in probs))
_check_registry()

_known = set(R.ANALYTES)
_on_disk = sorted(d for d in os.listdir(DST)
                  if os.path.isdir(os.path.join(DST, d))
                  and glob.glob(os.path.join(DST, d, "database", "*.csv")))
_missing = [d for d in _on_disk if d not in _known]
if _missing:
    raise SystemExit(
        "\nBUILD STOPPED: these analyte folders hold evidence tables but are not registered:\n"
        + "".join(f"  - {d}\n" for d in _missing)
        + "Add each one to ANALYTES, CANON and TABLE_MAP in scripts/registry.py,\n"
          "then run scripts/build_all.py again. See 'Adding an analyte' in README.md.\n")
for _a in R.TABLE_MAP:
    _disk = {os.path.basename(p) for p in glob.glob(os.path.join(DST, _a, "database", "*.csv"))}
    _new = sorted(_disk - set(R.TABLE_MAP[_a]))
    if _new:
        raise SystemExit(
            f"\nBUILD STOPPED: {_a} has evidence tables that are not in TABLE_MAP:\n"
            + "".join(f"  - {t}\n" for t in _new)
            + "Map each table to a canonical interferent id in scripts/registry.py.\n")

def assign(analyte, table, verbatim):
    v = re.sub(r"\s+", " ", verbatim).strip().lower()
    for rx, iid in R.OVERRIDES.get(analyte, {}).get(table, []):
        if re.search(rx, v):
            return iid
    return R.TABLE_MAP[analyte][table]

syn_rows, used = [], collections.Counter()
row_counts = collections.Counter()
for analyte in sorted(R.TABLE_MAP):
    for table in sorted(R.TABLE_MAP[analyte]):
        p = os.path.join(DST, analyte, "database", table)
        seen = collections.Counter()
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if not any((x or "").strip() for x in r.values()): continue
                v = re.sub(r"\s+", " ", (r.get("Interferent") or "")).strip()
                iid = assign(analyte, table, v)
                used[(analyte, iid)] += 1
                row_counts[(analyte, iid)] += 1
                seen[v] += 1
        for v, n in seen.items():
            syn_rows.append([analyte, table, v, assign(analyte, table, v), n])

prefix = {a: d["prefix"] for a, d in R.ANALYTES.items()}
with open(os.path.join(META, "interferents.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["interferent_id", "analyte_folder", "interferent_key", "interferent_canonical",
                "concept", "evidence_rows", "wording_variants"])
    nvar = collections.Counter()
    for a, t, v, iid, n in syn_rows: nvar[(a, iid)] += 1
    for a in sorted(R.CANON):
        for key, (name, concept) in sorted(R.CANON[a].items()):
            w.writerow([f"{prefix[a]}.{key}", a, key, name, concept,
                        row_counts[(a, key)], nvar[(a, key)]])

with open(os.path.join(META, "interferent_synonyms.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["analyte_folder", "source_file", "interferent_verbatim", "interferent_id", "rows"])
    for a, t, v, iid, n in sorted(syn_rows):
        w.writerow([a, t, v, f"{prefix[a]}.{iid}", n])

with open(os.path.join(META, "table_index.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["analyte_folder", "source_file", "default_interferent_id", "has_wording_overrides"])
    for a in sorted(R.TABLE_MAP):
        for t, iid in sorted(R.TABLE_MAP[a].items()):
            w.writerow([a, t, f"{prefix[a]}.{iid}", "yes" if R.OVERRIDES.get(a, {}).get(t) else "no"])

print("interferent_synonyms rows (verbatim wordings):", len(syn_rows))
print("rows assigned:", sum(used.values()))
zero = [(a, k) for a in R.CANON for k in R.CANON[a] if row_counts[(a, k)] == 0]
print("canonical ids with no rows:", len(zero))
for z in zero: print("   ", z)
print()
print("coverage per analyte:")
for a in sorted(R.CANON):
    ids = [k for k in R.CANON[a] if row_counts[(a, k)] > 0]
    print(f"  {a:26s} ids-in-use={len(ids):3d}  rows={sum(row_counts[(a,k)] for k in ids):6d}")
