# -*- coding: utf-8 -*-
import csv, glob, os, re, sqlite3, sys, collections
ROOT = sys.argv[1]
csv.field_size_limit(10 ** 7)
NOINFO = re.compile(r"masthead|front[- ]matter|classified advert|no text layer|no extractable text|"
                    r"ocr required|read in full and contains no|no article (body|text)", re.I)
DATA = ["Direction of effect", "Percentage change (calculated)", "Percentage change (as reported)",
        "Absolute change (as reported)", "Absolute change (calculated)",
        "Magnitude of change (verbatim from source)", "Baseline analyte concentration",
        "Final analyte concentration", "Interferent concentration (exact, with units)",
        "Platform/Brand/Method", "Analyzer/Instrument"]
def empty(v):
    v = (v or "").strip().lower()
    return (not v) or v.startswith("not reported") or v.startswith("not comput")

ENR = {}
_ep = os.path.join(ROOT, "meta", "references_enriched.csv")
if os.path.exists(_ep):
    for _r in csv.DictReader(open(_ep, encoding="utf-8")):
        ENR[re.sub(r"[^a-z0-9]", "", os.path.splitext(_r["source_pdf"])[0].lower())] = _r
def enriched(blob):
    for n in re.findall(r"([A-Za-z0-9][\w\.\-\+\(\)]*\.pdf)", blob):
        k = re.sub(r"[^a-z0-9]", "", os.path.splitext(n)[0].lower())
        if k in ENR: return True
        if len(k) > 15 and any(k2.endswith(k) or k.endswith(k2) or k2.startswith(k) or k.startswith(k2) for k2 in ENR): return True
    return False

tot = 0
no_cit = no_id = no_data = still_noinfo = both = 0
examples = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(ROOT, "*", "database", "*.csv"))):
    rel = os.path.relpath(f, ROOT)
    with open(f, newline="", encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh), 2):
            if not any((v or "").strip() for v in r.values()): continue
            tot += 1
            cit = (r.get("Citation") or "").strip()
            full = (r.get("Full reference (from PDF)") or "").strip()
            doi = (r.get("doi") or "").strip()
            blob = " ".join([cit, full, r.get("Notes") or ""])
            has_cit = bool(cit) and not cit.lower().startswith("not reported")
            has_id = bool(re.search(r"10\.\d{4,9}/", doi + " " + blob)) or \
                     bool(re.search(r"PMID[\s_:]*\d{6,8}", blob, re.I)) or \
                     (len(full) > 40 and bool(re.search(r"(18|19|20)\d{2}", full))) or enriched(blob)
            datafields = [c for c in DATA if not empty(r.get(c))]
            noinfo = bool(NOINFO.search(blob))
            if not has_cit: no_cit += 1; examples["no citation"].append((rel, i))
            if not has_id:  no_id += 1;  examples["no DOI / PMID / full reference"].append((rel, i, cit[:70]))
            if not datafields: no_data += 1; examples["no value in any data field"].append((rel, i, cit[:70]))
            if noinfo: still_noinfo += 1
            if noinfo and not datafields: both += 1; examples["source yielded nothing AND no data"].append((rel, i))

print(f"rows audited: {tot}")
print(f"  rows with no citation at all                    : {no_cit}")
print(f"  rows with no DOI, PMID or full reference        : {no_id}")
print(f"  rows with no value in any of the 11 data fields : {no_data}")
print(f"  rows whose source text mentions a retrieval problem (may still hold data): {still_noinfo}")
print(f"  rows that both lack data AND cite a document that supplied nothing       : {both}")
for k in ("no citation", "no DOI / PMID / full reference", "no value in any data field",
          "source yielded nothing AND no data"):
    if examples[k]:
        print(f"\n  >> {k} ({len(examples[k])}):")
        for e in examples[k][:8]: print("       ", e)
db = os.path.join(ROOT, "build", "cled.sqlite")
if os.path.exists(db):
    c = sqlite3.connect(db)
    print()
    for q, lab in [("doi is not null", "with DOI"), ("pmid is not null", "with PMID"),
                   ("doi is not null or pmid is not null", "with DOI or PMID"),
                   ("reference_status='reference_only'", "full reference only"),
                   ("has_effect_data=1", "carrying effect data"),
                   ("reference_origin='enriched'", "identifier recovered by enrichment")]:
        n = c.execute(f"select count(*) from evidence where {q}").fetchone()[0]
        print(f"  {lab:38s} {n:6d} / {tot}  ({n*100/tot:.1f}%)")
    e = c.execute("select count(*) from interferent where evidence_rows=0").fetchone()[0]
    print(f"\n  canonical interferents left with no rows: {e}")
