import csv, glob, json, re, collections
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
import registry as R
from parquet_export import parquet_name
DST   = ROOT
META = os.path.join(DST, "meta")

inter = list(csv.DictReader(open(os.path.join(META, "interferents.csv"), encoding="utf-8")))

# ---------- analyte registry ----------
ana_rows = []
for a in sorted(R.ANALYTES):
    d = R.ANALYTES[a]
    tables = sorted(R.TABLE_MAP[a])
    rows = 0
    for t in tables:
        with open(os.path.join(DST, a, "database", t), newline="", encoding="utf-8") as fh:
            rows += sum(1 for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values()))
    ints = [i for i in inter if i["analyte_folder"] == a and int(i["evidence_rows"]) > 0]
    rec = dict(
        analyte_id=d["prefix"], analyte_folder=a, component=d["component"], system=d["system"],
        kind_of_property=d["kind_of_property"], unit=d["unit"],
        aps_percent=d["aps_percent"],
        aps_type="allowable bias (relative), user-selected",
        aps_note=d["aps_note"], synonyms=d["synonyms"],
        interferent_count=len(ints), evidence_tables=len(tables), evidence_rows=rows)
    ana_rows.append(rec)
    # per-analyte analyte record
    with open(os.path.join(DST, a, f"{a}_analyte.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(list(rec.keys())); w.writerow([rec[k] for k in rec])

cols = list(ana_rows[0].keys())
with open(os.path.join(META, "analytes.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(cols)
    for r in ana_rows: w.writerow([r[c] for c in cols])
json.dump(ana_rows, open(os.path.join(META, "analytes.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)

# ---------- per-analyte interferent list, regenerated from the registry ----------
for a in sorted(R.ANALYTES):
    ints = [i for i in inter if i["analyte_folder"] == a and int(i["evidence_rows"]) > 0]
    ints.sort(key=lambda i: i["interferent_canonical"].lower())
    with open(os.path.join(DST, a, f"{a}_interferent_list.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["interferent_id", "interferent", "concept", "evidence_rows"])
        for i in ints:
            w.writerow([i["interferent_id"], i["interferent_canonical"], i["concept"], i["evidence_rows"]])

# ---------- data dictionary ----------
DICT = [
 ("Analyte", "string", "verbatim", "Analyte (measurand) exactly as named in the source publication. Spelling varies between papers; use analyte_id / component from analytes.csv for filtering."),
 ("Interferent", "string", "verbatim", "Interfering substance or condition exactly as named in the source publication. Use interferent_id (see interferent_synonyms.csv) for filtering."),
 ("Platform/Brand/Method", "string", "verbatim", "Measurement principle, assay brand or method as reported (e.g. CO-oximetry, FPIA, immunoturbidimetry)."),
 ("Analyzer/Instrument", "string", "verbatim", "Analyser or instrument on which the measurement was made."),
 ("Assay generation/version", "string", "verbatim", "Assay generation, kit version or lot where the source reports it."),
 ("Direction of effect", "enum", "up / down / no change / not reported", "Direction of the measurement error caused by the interferent, as reported: up = falsely increased, down = falsely decreased, no change = no detectable effect."),
 ("Direction (study criterion)", "enum", "up / down / no change / not reported", "Direction judged against the criterion used by the source study itself."),
 ("Direction (user APS)", "enum", "up / down / no change / not reported", "Direction judged against the analytical performance specification selected for this database (aps_percent)."),
 ("Interferent concentration (exact, with units)", "string", "verbatim, units embedded", "Concentration or dose of the interferent, with the units used by the source. Free text: not directly plottable."),
 ("Baseline analyte concentration", "string", "verbatim, units embedded", "Analyte concentration before or without the interferent, with source units. Free text."),
 ("Final analyte concentration", "string", "verbatim, units embedded", "Analyte concentration in the presence of the interferent, with source units. Free text."),
 ("Absolute change (as reported)", "string", "verbatim, units embedded", "Absolute change printed by the source, in the source's units."),
 ("Percentage change (as reported)", "string", "number or text", "Relative change printed by the source, in percent."),
 ("Absolute change (calculated)", "string", "number or text", "Absolute change derived from the baseline and final values in the source."),
 ("Percentage change (calculated)", "number", "percent", "Relative change in percent derived from the baseline and final values. This is the primary machine-readable effect size (pct_change in the derived build)."),
 ("Magnitude of change (verbatim from source)", "string", "verbatim", "The source's own wording for the size of the effect."),
 ("Significant-bias threshold", "string", "verbatim", "The threshold the SOURCE STUDY used to call a bias significant (often a statistical test, sometimes a percentage, often not reported). Not the database APS."),
 ("Clinical significance vs user APS", "string", "verbatim, contains the verdict", "Whether the observed effect exceeds the analytical performance specification selected for this database. The verdict is parsed into aps_verdict in the derived build."),
 ("Sample type", "string", "verbatim", "Specimen used (whole blood, serum, plasma, pooled plasma, postmortem blood, body cavity fluid and so on)."),
 ("Study method details", "string", "verbatim", "How the interference was produced and measured: spiking, in vivo exposure, patient samples, comparison arms."),
 ("Physiologically realistic concentration?", "enum", "Yes / Partial / Borderline / Unclear / not reported", "Appraisal: whether the interferent concentration tested can occur in patients."),
 ("Study design appropriate?", "enum", "Appropriate / Partially appropriate / Inappropriate / Unclear / not reported", "Appraisal of the study design for an interference claim."),
 ("Clinically significant effect?", "enum", "Yes / No / Partial / Unclear / not reported", "Appraisal of whether the effect matters clinically."),
 ("Real-world conditions reflected?", "enum", "Yes / No / Partial / Unclear / not reported", "Appraisal of how well the experiment reflects routine practice."),
 ("Additional sources of bias", "string", "verbatim", "Other biases the source reports or that are evident in it."),
 ("Notes", "string", "verbatim", "Free-text notes recorded during extraction."),
 ("Citation", "string", "verbatim", "Short citation plus the exact locator inside the source (page, table, figure). Often names the source PDF file."),
 ("Full reference (from PDF)", "string", "verbatim", "Full bibliographic reference as printed in the source document."),
 ("doi", "string", "DOI or 'not reported in the information source'", "Digital Object Identifier of the source publication."),
]
with open(os.path.join(META, "data_dictionary.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["position", "column", "parquet_column", "type", "values", "definition"])
    for i, (c, t, v, d) in enumerate(DICT, 1): w.writerow([i, c, parquet_name(c), t, v, d])
json.dump([dict(position=i, column=c, parquet_column=parquet_name(c), type=t, values=v, definition=d)
           for i, (c, t, v, d) in enumerate(DICT, 1)],
          open(os.path.join(META, "data_dictionary.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)

# verify the dictionary matches the real header
hdr = next(csv.reader(open(glob.glob(os.path.join(DST, "*", "database", "*.csv"))[0],
                           newline="", encoding="utf-8")))
assert [d[0] for d in DICT] == hdr, "dictionary does not match the CSV header"
print("data dictionary matches the 29-column header exactly")
print("analytes.csv / analytes.json written:", len(ana_rows), "analytes")
for r in ana_rows:
    print(f"  {r['analyte_folder']:26s} APS {r['aps_percent']:>5}%  interferents {r['interferent_count']:3d}  rows {r['evidence_rows']:5d}  unit {r['unit']}")

# ---------- table index + local full-text index ----------
syn = {}
for r in csv.DictReader(open(os.path.join(META, "interferent_synonyms.csv"), encoding="utf-8")):
    syn.setdefault((r["analyte_folder"], r["source_file"]), r["interferent_id"])
ICAN = {r["interferent_id"]: r["interferent_canonical"] for r in inter}
fi = []
for a in sorted(R.TABLE_MAP):
    for t in sorted(R.TABLE_MAP[a]):
        p = os.path.join(DST, a, "database", t)
        with open(p, newline="", encoding="utf-8-sig") as fh:
            n = sum(1 for x in csv.DictReader(fh) if any((v or "").strip() for v in x.values()))
        iid = f"{R.ANALYTES[a]['prefix']}.{R.TABLE_MAP[a][t]}"
        fi.append([a, R.ANALYTES[a]["component"], t, iid, ICAN.get(iid, ""), n])
with open(os.path.join(META, "file_index.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["analyte_folder", "analyte_component", "source_file",
                "default_interferent_id", "default_interferent", "data_rows"])
    w.writerows(fi)

pdf_idx = os.path.join(META, "fulltext_pdf_index.csv")
have_pdfs = glob.glob(os.path.join(DST, "*", "fulltext_pdfs", "*"))
if have_pdfs:
    with open(pdf_idx, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["analyte_folder", "fulltext_pdfs_subfolder", "pdf_count"])
        for d in sorted(have_pdfs):
            if os.path.isdir(d):
                w.writerow([os.path.relpath(d, DST).split(os.sep)[0], os.path.basename(d),
                            len(glob.glob(os.path.join(d, "*.pdf")))])
elif os.path.exists(pdf_idx):
    os.remove(pdf_idx)      # a distributed checkout carries no PDFs; a stale index would mislead

rm = os.path.join(META, "rename_map.csv")
if os.path.exists(rm) and not have_pdfs:
    rows = [r for r in csv.reader(open(rm, encoding="utf-8")) if not r[0].lower().endswith(".pdf")]
    with open(rm, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)

print("file_index.csv rows:", len(fi), "| full-text index:", "written" if have_pdfs else "not applicable")
