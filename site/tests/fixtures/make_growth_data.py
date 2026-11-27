#!/usr/bin/env python3
"""Growth fixture: a copy of the web deploy set with one fake analyte added.

Usage: make_growth_data.py <build dir> <output data dir>

Nothing in site/ is changed for this analyte. The site build that reads the output must show
it in the navigation, the home cards and the matrix, and give it a working page.
Uses pyarrow, which the data build already requires.
"""
import json, os, shutil, sys
import pyarrow as pa
import pyarrow.parquet as pq

src, dest = sys.argv[1], sys.argv[2]
AID, FOLDER, TEMPLATE = "zz", "zzfixture_serum", None
N_ROWS = 40

shutil.rmtree(dest, ignore_errors=True)
os.makedirs(os.path.join(dest, "parquet", "slim"))
os.makedirs(os.path.join(dest, "parquet", "detail"))
man = json.load(open(os.path.join(src, "parquet", "manifest.json"), encoding="utf-8"))
for group in ("slim", "detail"):
    for f in man["files"][group].values():
        shutil.copy(os.path.join(src, f["path"]), os.path.join(dest, f["path"]))
TEMPLATE = sorted(man["files"]["slim"])[0]

def write(table, rel, row_group):
    path = os.path.join(dest, rel)
    pq.write_table(table, path, compression="zstd", row_group_size=row_group)
    return os.path.getsize(path)

# fake rows: one existing concept shared with real analytes, one concept of its own
slim_t = pq.read_table(os.path.join(src, man["files"]["slim"][TEMPLATE]["path"]))
detail_t = pq.read_table(os.path.join(src, man["files"]["detail"][TEMPLATE]["path"]))
slim_rows = slim_t.slice(0, N_ROWS).to_pylist()
detail_by_id = {r["row_id"]: r for r in detail_t.to_pylist()}
causes = [("hemolysis", "Fixture hemolysis", "hemolysis"), ("fixture_cause", "Fixture-only cause", "fixture_concept")]
new_slim, new_detail = [], []
for i, r in enumerate(slim_rows):
    key, name, concept = causes[i % 2]
    d = dict(detail_by_id[r["row_id"]])
    rid = f"{AID}.fixture_table.{i + 1:04d}"
    pct = None if i % 5 == 4 else float((i - 10) * 3)       # some rows carry no numeric value
    r.update(row_id=rid, analyte_id=AID, interferent_id=f"{AID}.{key}", interferent_canonical=name,
             concept=concept, pct_change=pct, plottable=pct is not None, aps_percent=10.0,
             exceeds_aps=None if pct is None else abs(pct) > 10.0,
             pct_change_source=None if pct is None else "calculated",
             source_file=f"{FOLDER}/database/fixture_table.csv", source_row=i + 1)
    d.update(row_id=rid, analyte_id=AID, interferent_id=f"{AID}.{key}")
    new_slim.append(r); new_detail.append(d)
new_slim.sort(key=lambda r: (r["interferent_id"], r["row_id"]))
slim_new_t = pa.Table.from_pylist(new_slim, schema=slim_t.schema)
detail_new_t = pa.Table.from_pylist(new_detail, schema=detail_t.schema)

b = write(slim_new_t, f"parquet/slim/{AID}.parquet", 10000)
man["files"]["slim"][AID] = dict(path=f"parquet/slim/{AID}.parquet", analyte_folder=FOLDER, rows=N_ROWS, bytes=b, sorted_by=["interferent_id", "row_id"])
b = write(detail_new_t, f"parquet/detail/{AID}.parquet", 2000)
man["files"]["detail"][AID] = dict(path=f"parquet/detail/{AID}.parquet", analyte_folder=FOLDER, rows=N_ROWS, bytes=b, sorted_by=["row_id"])
all_t = pa.concat_tables([pq.read_table(os.path.join(src, man["files"]["slim_all"]["path"])), slim_new_t])
all_t = all_t.sort_by([("analyte_id", "ascending"), ("interferent_id", "ascending"), ("row_id", "ascending")])
man["files"]["slim_all"]["bytes"] = write(all_t, man["files"]["slim_all"]["path"], 8192)
man["files"]["slim_all"]["rows"] = all_t.num_rows
man["row_count"] = all_t.num_rows
json.dump(man, open(os.path.join(dest, "parquet", "manifest.json"), "w", encoding="utf-8"), indent=2)

analytes = json.load(open(os.path.join(src, "analytes.json"), encoding="utf-8"))
analytes.append(dict(analyte_id=AID, analyte_folder=FOLDER, component="Zzfixturate", system="Serum",
                     kind_of_property="Substance concentration", unit="mmol/L", aps_percent=10.0,
                     aps_type="allowable bias (relative), user-selected", aps_note="", synonyms="fixture analyte",
                     interferent_count=2, evidence_tables=1, evidence_rows=N_ROWS))
json.dump(analytes, open(os.path.join(dest, "analytes.json"), "w", encoding="utf-8"), indent=2)

interferents = json.load(open(os.path.join(src, "interferents.json"), encoding="utf-8"))
for key, name, concept in causes:
    n = sum(1 for r in new_slim if r["interferent_id"] == f"{AID}.{key}")
    interferents.append(dict(interferent_id=f"{AID}.{key}", analyte_folder=FOLDER, interferent_key=key,
                             interferent_canonical=name, concept=concept, evidence_rows=n, wording_variants=1))
json.dump(interferents, open(os.path.join(dest, "interferents.json"), "w", encoding="utf-8"), indent=2)

stats = json.load(open(os.path.join(src, "stats.json"), encoding="utf-8"))
stats["generated_rows"] += N_ROWS
stats["by_analyte"][FOLDER] = N_ROWS
stats["plottable_by_analyte"][FOLDER] = sum(1 for r in new_slim if r["plottable"])
json.dump(stats, open(os.path.join(dest, "stats.json"), "w", encoding="utf-8"), indent=2)
print(f"growth fixture: analyte '{AID}' with {N_ROWS} rows -> {dest} ({all_t.num_rows} rows in total)")
