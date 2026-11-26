# -*- coding: utf-8 -*-
"""Write the web data layer as Parquet. This is the only layer the website reads.

    build/parquet/
    |-- manifest.json                 schema version, files, row counts, byte sizes, columns
    |-- slim_all.parquet              every row, slim columns, sorted by analyte_id, interferent_id
    |-- slim/<analyte_id>.parquet     slim columns, one file per analyte
    `-- detail/<analyte_id>.parquet   row_id + every source column (snake_case), one file per analyte

Why Parquet: the evidence text is highly repetitive, so a columnar, dictionary-encoded,
zstd-compressed file is 20-40x smaller than the same rows as JSON, and DuckDB-WASM can
read only the row groups and columns a query needs over HTTP range requests.

pyarrow is imported lazily, so `parquet_name()` works without it (build_meta.py uses it
to record the Parquet column name of every source column in the data dictionary).
"""
import json, os, re, shutil

SCHEMA_VERSION = "1.0"
ZSTD_LEVEL = 19                 # decompression speed does not depend on the level
ROW_GROUP_ANALYTE = 10_000      # rows per row group in per-analyte files
ROW_GROUP_ALL = 8_192           # rows per row group in slim_all (sorted, so filters prune)
ROW_GROUP_DETAIL = 2_000       # detail files are sorted by row_id, so a single-row lookup
                               # fetches one small row group instead of the whole file

# source column -> Parquet column. Everything is snake_case; three names are made explicit
# so they cannot be confused with the normalised field of the same meaning in the slim file.
_OVERRIDES = {
    "Analyte": "analyte_verbatim",
    "Interferent": "interferent_verbatim",
    "doi": "doi_as_printed",
}


def parquet_name(column):
    """Parquet column name for a source column of the evidence tables."""
    if column in _OVERRIDES:
        return _OVERRIDES[column]
    s = re.sub(r"[^0-9a-zA-Z]+", "_", column).strip("_").lower()
    return re.sub(r"_+", "_", s)


# slim: everything the table, the filters, the charts and the custom-APS logic need
SLIM_FIELDS = [
    ("row_id", "string"),
    ("analyte_id", "string"),
    ("interferent_id", "string"),
    ("interferent_canonical", "string"),
    ("concept", "string"),
    ("interferent_verbatim", "string"),
    ("platform", "string"),
    ("analyzer", "string"),
    ("sample_type", "string"),
    ("direction", "string"),
    ("direction_study", "string"),
    ("direction_aps", "string"),
    ("pct_change", "float64"),
    ("pct_change_source", "string"),
    ("plottable", "bool"),
    ("aps_percent", "float64"),
    ("aps_verdict", "string"),
    ("exceeds_aps", "bool"),
    ("realistic_concentration", "string"),
    ("design_appropriate", "string"),
    ("clinically_significant", "string"),
    ("real_world", "string"),
    ("doi", "string"),
    ("pmid", "string"),
    ("reference_status", "string"),
    ("reference_origin", "string"),
    ("has_effect_data", "bool"),
    ("source_file", "string"),
    ("source_row", "int32"),
]

# detail: derived reference fields that are not in the source columns, then every source column
DETAIL_DERIVED = [
    ("row_id", "string"),
    ("analyte_id", "string"),
    ("interferent_id", "string"),
    ("reference_full_resolved", "string"),
]


def _pa_type(pa, t):
    return {"string": pa.string(), "float64": pa.float64(), "bool": pa.bool_(),
            "int32": pa.int32()}[t]


def _table(pa, fields, rows):
    cols = {}
    for name, t in fields:
        cols[name] = pa.array([r.get(name) for r in rows], type=_pa_type(pa, t))
    return pa.table(cols)


def write(rows_out, analytes, build_dir, header):
    """rows_out: {analyte_folder: [record, ...]} as produced by build_dataset.py
    analytes: registry.ANALYTES; header: the 29 source column names in order.
    Returns the manifest dict, or None when pyarrow is not installed."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        stale = os.path.join(build_dir, "parquet")
        if os.path.isdir(stale):
            shutil.rmtree(stale)        # never leave Parquet that no longer matches the CSVs
        if os.environ.get("CLED_REQUIRE_PARQUET") == "1":
            raise SystemExit("\nBUILD STOPPED: CLED_REQUIRE_PARQUET=1 but pyarrow is not installed.\n"
                             "Run: pip install -r requirements.txt\n")
        print("NOTE: pyarrow is not installed, so the Parquet web layer was not built.\n"
              "      Install it with `pip install -r requirements.txt` to build it locally.\n"
              "      CI builds it on every push.")
        return None

    detail_cols = [(parquet_name(c), "string") for c in header]
    names = [n for n, _ in detail_cols]
    if len(set(names)) != len(names):
        raise SystemExit("BUILD STOPPED: two source columns map to the same Parquet column name")
    detail_fields = DETAIL_DERIVED + detail_cols
    clash = {n for n, _ in DETAIL_DERIVED} & set(names)
    if clash:
        raise SystemExit(f"BUILD STOPPED: Parquet column name clash in detail file: {sorted(clash)}")

    final = os.path.join(build_dir, "parquet")
    tmp = final + ".tmp"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(os.path.join(tmp, "slim"))
    os.makedirs(os.path.join(tmp, "detail"))

    def write_file(table, path, row_group):
        pq.write_table(table, path, compression="zstd", compression_level=ZSTD_LEVEL,
                       use_dictionary=True, write_statistics=True, row_group_size=row_group)
        return os.path.getsize(path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "compression": f"zstd-{ZSTD_LEVEL}",
        "row_count": 0,
        "slim_columns": [{"name": n, "type": t} for n, t in SLIM_FIELDS],
        "detail_columns": [{"name": n, "type": t} for n, t in detail_fields],
        "files": {"slim_all": None, "slim": {}, "detail": {}},
    }
    every = []
    for folder in sorted(rows_out):
        aid = analytes[folder]["prefix"]
        rows = sorted(rows_out[folder], key=lambda r: (r["interferent_id"], r["row_id"]))
        every.extend(rows)

        slim_path = os.path.join(tmp, "slim", f"{aid}.parquet")
        b = write_file(_table(pa, SLIM_FIELDS, rows), slim_path, ROW_GROUP_ANALYTE)
        manifest["files"]["slim"][aid] = {"path": f"parquet/slim/{aid}.parquet",
                                          "analyte_folder": folder, "rows": len(rows), "bytes": b,
                                          "sorted_by": ["interferent_id", "row_id"]}

        drows = []
        for r in sorted(rows, key=lambda r: r["row_id"]):
            d = {"row_id": r["row_id"], "analyte_id": r["analyte_id"],
                 "interferent_id": r["interferent_id"],
                 "reference_full_resolved": r.get("reference_full")}
            for c in header:
                d[parquet_name(c)] = r["verbatim"].get(c, "")
            drows.append(d)
        detail_path = os.path.join(tmp, "detail", f"{aid}.parquet")
        b = write_file(_table(pa, detail_fields, drows), detail_path, ROW_GROUP_DETAIL)
        manifest["files"]["detail"][aid] = {"path": f"parquet/detail/{aid}.parquet",
                                            "analyte_folder": folder, "rows": len(drows), "bytes": b,
                                            "sorted_by": ["row_id"]}

    every.sort(key=lambda r: (r["analyte_id"], r["interferent_id"], r["row_id"]))
    all_path = os.path.join(tmp, "slim_all.parquet")
    b = write_file(_table(pa, SLIM_FIELDS, every), all_path, ROW_GROUP_ALL)
    manifest["files"]["slim_all"] = {"path": "parquet/slim_all.parquet", "rows": len(every),
                                     "bytes": b, "sorted_by": ["analyte_id", "interferent_id", "row_id"]}
    manifest["row_count"] = len(every)

    with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    if os.path.isdir(final):
        shutil.rmtree(final)
    os.replace(tmp, final)          # swap in only a complete layer
    return manifest


def deploy_set(build_dir):
    """Paths, relative to build/, that the website is allowed to publish."""
    out = []
    for name in ("analytes.json", "interferents.json", "stats.json"):
        if os.path.exists(os.path.join(build_dir, name)):
            out.append(name)
    pq_dir = os.path.join(build_dir, "parquet")
    for dp, _, fn in os.walk(pq_dir):
        for f in fn:
            out.append(os.path.relpath(os.path.join(dp, f), build_dir))
    return sorted(out)
