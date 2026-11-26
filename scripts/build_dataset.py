# -*- coding: utf-8 -*-
"""Build the derived C-LED dataset from the source CSVs:
the Parquet web layer (build/parquet/), the internal SQLite + FTS database used by the
docs and checks, and legacy JSON shards. Source CSVs are never modified. Re-runnable."""
import csv, glob, json, re, sqlite3, collections
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
import registry as R
import parquet_export as PX

DST   = ROOT
META  = os.path.join(DST, "meta")
BUILD = os.path.join(DST, "build")
os.makedirs(BUILD, exist_ok=True)
os.makedirs(os.path.join(BUILD, "evidence"), exist_ok=True)

csv.field_size_limit(10 ** 7)
DOI_RE  = re.compile(r"10\.\d{4,9}/[^\s,;\"'\]\)]+")
PMID_RE = re.compile(r"PMID[\s_:]*(\d{6,8})", re.I)
PDF_RE  = re.compile(r"([A-Za-z0-9][\w\.\-\+\(\)]*\.pdf)")
ARROW   = {"↑": "up", "↓": "down", "↔": "none"}

def norm_pdf(s):
    return re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(s))[0].lower())

def direction(v):
    v = (v or "").strip()
    if v in ARROW: return ARROW[v]
    if v.lower().startswith("not reported"): return "not_reported"
    return "other" if v else "not_reported"

def appraisal(v):
    v = re.sub(r"\s+", " ", (v or "")).strip()
    if not v or v.lower().startswith("not reported"): return "not_reported"
    return v[0].upper() + v[1:].lower()

def number(v):
    v = (v or "").strip().replace("−", "-").replace(",", ".").rstrip("%").strip()
    if not v or re.match(r"(?i)not (reported|comput)", v): return None
    try:
        f = float(v)
    except ValueError:
        return None
    return f if -1e6 < f < 1e6 else None

def aps_verdict(t):
    t = t or ""
    if re.search(r"\bexceeds?\b", t, re.I): return "exceeds"
    if re.search(r"\bwithin\b", t, re.I): return "within"
    if re.search(r"not comput|cannot be calc|no quantitative|not calculable", t, re.I): return "not_computable"
    if t.strip().lower().startswith("not reported"): return "not_reported"
    return "other"

# ---- lookups -------------------------------------------------------------
inter_rows = list(csv.DictReader(open(os.path.join(META, "interferents.csv"), encoding="utf-8")))
INTER = {(r["analyte_folder"], r["interferent_key"]): r for r in inter_rows}
SYN = {}
for r in csv.DictReader(open(os.path.join(META, "interferent_synonyms.csv"), encoding="utf-8")):
    SYN[(r["analyte_folder"], r["source_file"], r["interferent_verbatim"])] = r["interferent_id"]

PDFPOOL = {}
for a in R.ANALYTES:
    PDFPOOL[a] = {norm_pdf(p): os.path.relpath(p, DST)
                  for p in glob.glob(os.path.join(DST, a, "fulltext_pdfs", "*", "*.pdf"))}
RENAME = {}
rm = os.path.join(META, "rename_map.csv")
if os.path.exists(rm):
    for r in csv.reader(open(rm, encoding="utf-8")):
        if len(r) == 2: RENAME[norm_pdf(r[0])] = r[1]

def find_pdf(a, name):
    n = norm_pdf(name)
    pool = PDFPOOL[a]
    if n in pool: return pool[n]
    for k, v in pool.items():
        if k.startswith(n) or n.startswith(k): return v
    if n in RENAME and os.path.exists(os.path.join(DST, RENAME[n])): return RENAME[n]
    return None


# ---- reference enrichment: identifiers recovered outside the source tables ----
ENRICH = {}
_ep = os.path.join(META, "references_enriched.csv")
if os.path.exists(_ep):
    for _r in csv.DictReader(open(_ep, encoding="utf-8")):
        ENRICH[norm_pdf(_r["source_pdf"])] = _r

HDR = None
rows_out = collections.defaultdict(list)
refs = {}
stats = collections.Counter()

for a in sorted(R.TABLE_MAP):
    d = R.ANALYTES[a]
    for table in sorted(R.TABLE_MAP[a]):
        path = os.path.join(DST, a, "database", table)
        stem = re.sub(r"\.csv$", "", table)
        with open(path, newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            if HDR is None: HDR = rd.fieldnames
            seq = 0
            for raw in rd:
                if not any((v or "").strip() for v in raw.values()): continue
                seq += 1
                verbatim = re.sub(r"\s+", " ", (raw.get("Interferent") or "")).strip()
                iid = SYN.get((a, table, verbatim)) or (d["prefix"] + "." + R.TABLE_MAP[a][table])
                key = iid.split(".", 1)[1]
                ic = INTER.get((a, key), {})

                cit  = (raw.get("Citation") or "").strip()
                full = (raw.get("Full reference (from PDF)") or "").strip()
                doif = (raw.get("doi") or "").strip()
                blob = " ".join([doif, cit, full])
                m = DOI_RE.search(doif) or DOI_RE.search(blob)
                doi = m.group(0).rstrip(".,;)") if m else None
                mp = PMID_RE.search(blob)
                pmid = mp.group(1) if mp else None
                pdfs = PDF_RE.findall(cit) + PDF_RE.findall(full)
                pdf_rel = find_pdf(a, pdfs[0]) if pdfs else None
                ref_full = full if full and not full.lower().startswith("not reported") else None
                cit_ident = bool(re.search(r"\b(18|19|20)\d{2}\b", cit)) and bool(
                    re.search(r"[A-Za-z]{4,}", re.sub(r"(?i)\b(file|pdf|project)\b", " ", cit)))
                origin = "source_table"
                if not doi and not pmid and pdfs:
                    _k = norm_pdf(pdfs[0])
                    _e = ENRICH.get(_k) or next(
                        (v for k2, v in ENRICH.items()
                         if len(_k) > 15 and (k2.endswith(_k) or _k.endswith(k2)
                                             or k2.startswith(_k) or _k.startswith(k2))), None)
                    if _e:
                        doi = _e["doi"] or None
                        pmid = _e["pmid"] or None
                        ref_full = ref_full or (_e["reference_full"] or None)
                        origin = "enriched"
                if doi:        rstat = "doi"
                elif pmid:     rstat = "pmid"
                elif ref_full: rstat = "reference_only"
                elif cit_ident: rstat = "citation_only"
                else:          rstat = "unidentified"

                pct = number(raw.get("Percentage change (calculated)"))
                pct_src = "calculated"
                if pct is None:
                    pct = number(raw.get("Percentage change (as reported)")); pct_src = "as_reported"
                if pct is None: pct_src = None
                verdict = aps_verdict(raw.get("Clinical significance vs user APS"))

                rec_dir = direction(raw.get("Direction of effect"))
                rid = f"{d['prefix']}.{stem}.{seq:04d}"
                rec = {
                 "row_id": rid,
                 "analyte_id": d["prefix"], "analyte_folder": a,
                 "analyte_component": d["component"], "analyte_system": d["system"],
                 "analyte_unit": d["unit"], "aps_percent": d["aps_percent"],
                 "interferent_id": iid,
                 "interferent_canonical": ic.get("interferent_canonical", ""),
                 "concept": ic.get("concept", ""),
                 "interferent_verbatim": verbatim,
                 "analyte_verbatim": re.sub(r"\s+", " ", (raw.get("Analyte") or "")).strip(),
                 "platform": (raw.get("Platform/Brand/Method") or "").strip(),
                 "analyzer": (raw.get("Analyzer/Instrument") or "").strip(),
                 "sample_type": (raw.get("Sample type") or "").strip(),
                 "direction": rec_dir,
                 "direction_study": direction(raw.get("Direction (study criterion)")),
                 "direction_aps": direction(raw.get("Direction (user APS)")),
                 "pct_change": pct, "pct_change_source": pct_src,
                 "plottable": pct is not None,
                 "aps_verdict": verdict,
                 "exceeds_aps": (abs(pct) > d["aps_percent"]) if pct is not None else None,
                 "realistic_concentration": appraisal(raw.get("Physiologically realistic concentration?")),
                 "design_appropriate": appraisal(raw.get("Study design appropriate?")),
                 "clinically_significant": appraisal(raw.get("Clinically significant effect?")),
                 "real_world": appraisal(raw.get("Real-world conditions reflected?")),
                 "doi": doi, "pmid": pmid, "reference_status": rstat,
                 "reference_origin": origin,
                 "has_effect_data": bool(
                     rec_dir != "not_reported" or pct is not None or (
                         (raw.get("Magnitude of change (verbatim from source)") or "")
                         .strip().lower().startswith("not reported") is False)),
                 "reference_full": ref_full, "citation": cit,
                 "source_pdf": pdfs[0] if pdfs else None, "pdf_path": pdf_rel,
                 "source_file": f"{a}/database/{table}", "source_row": seq + 1,
                 "verbatim": {k: (raw.get(k) or "") for k in HDR},
                }
                rows_out[a].append(rec)
                stats[("analyte", a)] += 1
                stats[("direction", rec["direction"])] += 1
                stats[("verdict", verdict)] += 1
                stats[("concept", rec["concept"])] += 1
                if pct is not None: stats[("plottable", a)] += 1
                rk = doi or (("pmid:" + pmid) if pmid else (ref_full or cit)[:200])
                if rk and rk not in refs:
                    refs[rk] = dict(reference_key=rk, doi=doi, pmid=pmid,
                                    reference_full=ref_full, citation_example=cit,
                                    pdf_path=pdf_rel, analytes=set())
                if rk: refs[rk]["analytes"].add(a)

for r in refs.values(): r["analytes"] = ";".join(sorted(r["analytes"]))

# ---- JSON ---------------------------------------------------------------
SLIM = ["row_id","analyte_id","interferent_id","concept","direction","pct_change","plottable",
        "aps_verdict","exceeds_aps","platform","analyzer","sample_type","doi","pmid",
        "reference_status","reference_origin","has_effect_data",
        "clinically_significant","design_appropriate",
        "realistic_concentration","real_world","interferent_verbatim"]
slim = []
manifest = {}
for a, rs in rows_out.items():
    os.makedirs(os.path.join(BUILD, "evidence", a), exist_ok=True)
    byint = collections.defaultdict(list)
    for r in rs:
        byint[r["interferent_id"].split(".", 1)[1]].append(r)
    for key, group in byint.items():
        fp = os.path.join(BUILD, "evidence", a, f"{key}.json")
        json.dump(group, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
        manifest[f"{R.ANALYTES[a]['prefix']}.{key}"] = dict(
            path=f"evidence/{a}/{key}.json", rows=len(group),
            bytes=os.path.getsize(fp))
    slim += [{k: r[k] for k in SLIM} for r in rs]
json.dump(manifest, open(os.path.join(BUILD, "manifest.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
# sharded slim index: one file per analyte, so a growing database never forces
# the browser to download one ever-larger file
os.makedirs(os.path.join(BUILD, "slim"), exist_ok=True)
shard_info = {}
byan = collections.defaultdict(list)
for r in slim: byan[r["analyte_id"]].append(r)
for aid, rs in byan.items():
    fp = os.path.join(BUILD, "slim", f"{aid}.json")
    json.dump(rs, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
    shard_info[aid] = dict(path=f"slim/{aid}.json", rows=len(rs), bytes=os.path.getsize(fp))
json.dump(shard_info, open(os.path.join(BUILD, "slim", "index.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
json.dump(slim, open(os.path.join(BUILD, "evidence_slim.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
json.dump(json.load(open(os.path.join(META, "analytes.json"), encoding="utf-8")),
          open(os.path.join(BUILD, "analytes.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
json.dump([{k: (int(v) if k in ("evidence_rows","wording_variants") else v)
            for k, v in r.items()} for r in inter_rows],
          open(os.path.join(BUILD, "interferents.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# stats for dashboards
pcts = collections.defaultdict(list)
for a, rs in rows_out.items():
    for r in rs:
        if r["pct_change"] is not None: pcts[a].append(r["pct_change"])
st = dict(
 generated_rows=len(slim),
 by_analyte={a: stats[("analyte", a)] for a in sorted(rows_out)},
 plottable_by_analyte={a: stats[("plottable", a)] for a in sorted(rows_out)},
 by_direction={k[1]: v for k, v in stats.items() if k[0] == "direction"},
 by_verdict={k[1]: v for k, v in stats.items() if k[0] == "verdict"},
 by_concept=dict(sorted(((k[1], v) for k, v in stats.items() if k[0] == "concept"),
                        key=lambda x: -x[1])),
 pct_change_summary={a: dict(n=len(v), min=min(v), max=max(v),
                             median=sorted(v)[len(v)//2]) for a, v in pcts.items() if v},
)
json.dump(st, open(os.path.join(BUILD, "stats.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)

with open(os.path.join(META, "references.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["reference_key","doi","pmid","reference_full",
                                       "citation_example","pdf_path","analytes"])
    w.writeheader()
    for r in sorted(refs.values(), key=lambda r: r["reference_key"]): w.writerow(r)

# ---- Parquet web layer ------------------------------------------------------
_manifest = PX.write(rows_out, R.ANALYTES, BUILD, HDR)
if _manifest:
    _pq = _manifest["files"]
    _tot = _pq["slim_all"]["bytes"] + sum(v["bytes"] for v in _pq["slim"].values()) \
           + sum(v["bytes"] for v in _pq["detail"].values())
    print(f"parquet: {_manifest['row_count']} rows | slim_all {_pq['slim_all']['bytes']/1e6:.2f} MB | "
          f"{len(_pq['slim'])} slim + {len(_pq['detail'])} detail files | total {_tot/1e6:.2f} MB")

# ---- SQLite -------------------------------------------------------------
dbp = os.path.join(BUILD, "cled.sqlite")
if os.path.exists(dbp): os.remove(dbp)
con = sqlite3.connect(dbp); cur = con.cursor()
cur.executescript("""
CREATE TABLE analyte(analyte_id TEXT PRIMARY KEY, analyte_folder TEXT, component TEXT, system TEXT,
  kind_of_property TEXT, unit TEXT, aps_percent REAL, aps_type TEXT, aps_note TEXT, synonyms TEXT,
  interferent_count INT, evidence_tables INT, evidence_rows INT);
CREATE TABLE interferent(interferent_id TEXT PRIMARY KEY, analyte_folder TEXT, interferent_key TEXT,
  interferent_canonical TEXT, concept TEXT, evidence_rows INT, wording_variants INT);
CREATE TABLE evidence(
  row_id TEXT PRIMARY KEY, analyte_id TEXT, analyte_folder TEXT, interferent_id TEXT, concept TEXT,
  interferent_verbatim TEXT, analyte_verbatim TEXT, platform TEXT, analyzer TEXT, sample_type TEXT,
  direction TEXT, direction_study TEXT, direction_aps TEXT,
  pct_change REAL, pct_change_source TEXT, plottable INT,
  aps_percent REAL, aps_verdict TEXT, exceeds_aps INT,
  realistic_concentration TEXT, design_appropriate TEXT, clinically_significant TEXT, real_world TEXT,
  doi TEXT, pmid TEXT, reference_status TEXT, reference_origin TEXT, has_effect_data INT,
  reference_full TEXT, citation TEXT,
  source_pdf TEXT, pdf_path TEXT, source_file TEXT, source_row INT);
CREATE INDEX ix_ev_analyte ON evidence(analyte_id);
CREATE INDEX ix_ev_inter ON evidence(interferent_id);
CREATE INDEX ix_ev_concept ON evidence(concept);
CREATE INDEX ix_ev_verdict ON evidence(aps_verdict);
CREATE INDEX ix_ev_pct ON evidence(pct_change);
CREATE INDEX ix_ev_ref ON evidence(reference_status);
CREATE TABLE reference_(reference_key TEXT PRIMARY KEY, doi TEXT, pmid TEXT, reference_full TEXT,
  citation_example TEXT, pdf_path TEXT, analytes TEXT);
CREATE VIRTUAL TABLE evidence_fts USING fts5(row_id UNINDEXED, text);
""")
an = json.load(open(os.path.join(META, "analytes.json"), encoding="utf-8"))
cur.executemany("INSERT INTO analyte VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
  [(r["analyte_id"],r["analyte_folder"],r["component"],r["system"],r["kind_of_property"],r["unit"],
    r["aps_percent"],r["aps_type"],r["aps_note"],r["synonyms"],r["interferent_count"],
    r["evidence_tables"],r["evidence_rows"]) for r in an])
cur.executemany("INSERT INTO interferent VALUES(?,?,?,?,?,?,?)",
  [(r["interferent_id"],r["analyte_folder"],r["interferent_key"],r["interferent_canonical"],
    r["concept"],int(r["evidence_rows"]),int(r["wording_variants"])) for r in inter_rows])
EV = ["row_id","analyte_id","analyte_folder","interferent_id","concept","interferent_verbatim",
 "analyte_verbatim","platform","analyzer","sample_type","direction","direction_study","direction_aps",
 "pct_change","pct_change_source","plottable","aps_percent","aps_verdict","exceeds_aps",
 "realistic_concentration","design_appropriate","clinically_significant","real_world",
 "doi","pmid","reference_status","reference_origin","has_effect_data",
 "reference_full","citation","source_pdf","pdf_path",
 "source_file","source_row"]
batch, fts = [], []
for a, rs in rows_out.items():
    for r in rs:
        batch.append(tuple(r[k] for k in EV))
        fts.append((r["row_id"], " ".join(filter(None, [
            r["analyte_verbatim"], r["interferent_verbatim"], r["interferent_canonical"],
            r["platform"], r["analyzer"], r["sample_type"],
            r["verbatim"].get("Magnitude of change (verbatim from source)", ""),
            r["verbatim"].get("Study method details", ""), r["verbatim"].get("Notes", ""),
            r["citation"], r["reference_full"] or ""]))))
cur.executemany(f"INSERT INTO evidence VALUES({','.join('?'*len(EV))})", batch)
cur.executemany("INSERT INTO evidence_fts VALUES(?,?)", fts)
cur.executemany("INSERT INTO reference_ VALUES(?,?,?,?,?,?,?)",
  [(r["reference_key"],r["doi"],r["pmid"],r["reference_full"],r["citation_example"],
    r["pdf_path"],r["analytes"]) for r in refs.values()])
con.commit()
cur.execute("VACUUM")
con.commit()

gaps = [r for a in rows_out for r in rows_out[a] if r["reference_status"] == "unidentified"]
with open(os.path.join(META, "known_gaps.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["row_id","source_file","source_row","issue","citation"])
    for r in gaps:
        w.writerow([r["row_id"], r["source_file"], r["source_row"],
                    "no DOI, no PMID, no full reference and no author/year citation in the source document", r["citation"]])

with open(os.path.join(BUILD, "schema.sql"), "w", encoding="utf-8") as fh:
    for (s,) in cur.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"):
        fh.write(s.strip() + ";\n")
print("rows:", len(batch))
print("references:", len(refs))
print("sqlite:", round(os.path.getsize(dbp)/1e6, 1), "MB")
print("evidence_slim.json:", round(os.path.getsize(os.path.join(BUILD,'evidence_slim.json'))/1e6, 1), "MB (combined)")
print("slim shards:", len(glob.glob(os.path.join(BUILD,'slim','*.json')))-1, "largest", round(max(os.path.getsize(p) for p in glob.glob(os.path.join(BUILD,'slim','*.json')))/1e6,1), "MB")
ejs = glob.glob(os.path.join(BUILD,'evidence','*','*.json'))
print("evidence json files:", len(ejs), "total", round(sum(os.path.getsize(p) for p in ejs)/1e6, 1), "MB, largest", round(max(os.path.getsize(p) for p in ejs)/1e6, 1), "MB")
print("plottable rows:", sum(1 for a in rows_out for r in rows_out[a] if r["plottable"]))
print("reference_status:", dict(collections.Counter(r["reference_status"] for a in rows_out for r in rows_out[a])))
con.close()
