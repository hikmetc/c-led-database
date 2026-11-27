# -*- coding: utf-8 -*-
"""Inclusion screening: decide, row by row, whether a row of an evidence table may enter the
database, and say why not.

Rejection criteria (the numbers are the ones used in the documentation)

  automatic - decided from the row itself
     1  no_source             not enough information to find the source: no DOI, no PubMed ID,
                              no full reference, and a citation without an author and a year
     2  no_citation           the Citation column is empty
     3  no_evidence           no value in any of the 11 data fields
     8  duplicate             the same result is already present (same source, platform,
                              analyzer, concentrations and values)
     9  bad_identifier        the DOI is malformed, or doi.org does not know it
    17  verdict_inconsistent  the recorded APS verdict contradicts the numeric change

  manual - only a person can decide; the screening suggests rows to look at
     4  wrong_analyte         the source did not measure this analyte
     5  wrong_document        the cited file is not the article
    10  out_of_scope          not analytical interference or pre-analytical error

  table level (enforced elsewhere, listed for completeness)
     6  the table does not have the 29 columns of the database   (importer, validate.py)
     7  a row reaches no canonical interference cause            (build)

Nothing here changes a file. `screen()` returns a verdict per row; the importer and the manager
app apply it after the user has confirmed, and archive every rejected row with its reasons in
meta/rejected_rows.csv.
"""
import csv, json, os, re, urllib.error, urllib.parse, urllib.request

csv.field_size_limit(10 ** 7)

CRITERIA = {
    "no_source": dict(no=1, auto=True, title="Not enough information to find the source"),
    "no_citation": dict(no=2, auto=True, title="No citation"),
    "no_evidence": dict(no=3, auto=True, title="No evidence in any of the 11 data fields"),
    "wrong_analyte": dict(no=4, auto=False, title="The source did not measure this analyte"),
    "wrong_document": dict(no=5, auto=False, title="The cited file is not the article"),
    "duplicate": dict(no=8, auto=True, title="Duplicate of another row"),
    "bad_identifier": dict(no=9, auto=True, title="DOI malformed or unknown to doi.org"),
    "out_of_scope": dict(no=10, auto=False, title="Out of scope (not analytical interference or pre-analytical error)"),
    "verdict_inconsistent": dict(no=17, auto=True, title="Recorded APS verdict contradicts the numeric change"),
}
MANUAL = [k for k, v in CRITERIA.items() if not v["auto"]]

DATA_FIELDS = ["Direction of effect", "Percentage change (calculated)", "Percentage change (as reported)",
               "Absolute change (as reported)", "Absolute change (calculated)",
               "Magnitude of change (verbatim from source)", "Baseline analyte concentration",
               "Final analyte concentration", "Interferent concentration (exact, with units)",
               "Platform/Brand/Method", "Analyzer/Instrument"]
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;\"'\]\)]+")
PMID_RE = re.compile(r"PMID[\s_:]*(\d{6,8})", re.I)
PDF_RE = re.compile(r"([A-Za-z0-9][\w\.\-\+\(\)]*\.pdf)")
DOC_PROBLEM = re.compile(r"masthead|editorial[- ]board|classified[- ]advert|permissions? (sheet|page|form)|front[- ]matter|"
                         r"not the (cited |target )?article|wrong (document|pdf|file|paper)|no text layer|"
                         r"could not be (read|extracted|opened)|unreadable", re.I)


def _empty(v):
    v = (v or "").strip().lower()
    return (not v) or v.startswith("not reported") or v.startswith("not comput")


def number(v):
    """The build's rule for a numeric percent change (scripts/build_dataset.py)."""
    v = (v or "").strip().replace("−", "-").replace(",", ".").rstrip("%").strip()
    if not v or re.match(r"(?i)not (reported|comput)", v):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return f if -1e6 < f < 1e6 else None


def verdict(t):
    t = t or ""
    if re.search(r"\bexceeds?\b", t, re.I):
        return "exceeds"
    if re.search(r"\bwithin\b", t, re.I):
        return "within"
    return None


def norm_pdf(s):
    return re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(s))[0].lower())


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def duplicate_key(row):
    """Two rows are the same result when the first 16 columns, the sample type and the citation agree."""
    cols = list(row)[:16]
    return tuple((row.get(c) or "").strip() for c in cols) + ((row.get("Sample type") or "").strip(),
                                                                 re.sub(r"\s+", " ", row.get("Citation") or "").strip())


def existing_keys(root, analyte_folder, exclude_file=None):
    """Duplicate keys of every row already in the analyte's tables -> where it is."""
    out = {}
    base = os.path.join(root, analyte_folder, "database")
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if not name.endswith(".csv") or name == exclude_file:
            continue
        with open(os.path.join(base, name), encoding="utf-8-sig", newline="") as fh:
            for i, r in enumerate(csv.DictReader(fh), 1):
                out.setdefault(duplicate_key(r), f"{name}, row {i}")
    return out


def _enriched(root):
    out = {}
    p = os.path.join(root, "meta", "references_enriched.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            out[norm_pdf(r["source_pdf"])] = r
    return out


def check_dois(dois, cache_path=None, timeout=8):
    """Ask doi.org whether each DOI exists. Returns {doi: True | False | None (could not be checked)}.
    Only the DOI itself is sent. Results are cached."""
    cache = {}
    if cache_path and os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
        except ValueError:
            cache = {}
    out = {}
    for doi in sorted(set(dois)):
        if doi in cache:
            out[doi] = cache[doi]
            continue
        try:
            with urllib.request.urlopen("https://doi.org/api/handles/" + urllib.parse.quote(doi, safe="/"), timeout=timeout) as r:
                out[doi] = json.load(r).get("responseCode") == 1
        except urllib.error.HTTPError as e:
            out[doi] = False if e.code == 404 else None
        except Exception:
            out[doi] = None
        if out[doi] is not None:
            cache[doi] = out[doi]
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(cache, open(cache_path, "w", encoding="utf-8"))
    return out


def row_doi(row):
    blob = " ".join([(row.get("doi") or ""), (row.get("Citation") or ""), (row.get("Full reference (from PDF)") or "")])
    m = DOI_RE.search(row.get("doi") or "") or DOI_RE.search(blob)
    return m.group(0).rstrip(".,;)") if m else None


def screen(rows, analyte, root, exclude_file=None, doi_status=None):
    """rows: list of dicts keyed by the 29 column names.
    analyte: dict with folder, component, prefix, synonyms, aps_percent (aps_note optional).
    Returns one dict per row: {"row": n (1-based), "reject": [...], "check": [...]}, where each
    entry is {"code", "no", "title", "detail"}. `reject` are automatic rejections; `check` are
    suggestions for the manual criteria."""
    enriched = _enriched(root)
    seen_elsewhere = existing_keys(root, analyte["folder"], exclude_file)
    names = {_norm(x) for x in [analyte.get("component"), analyte.get("prefix"), analyte["folder"].split("_")[0]]
             + (analyte.get("synonyms") or "").split(";") if _norm(x)}
    aps = analyte.get("aps_percent")
    seen_here = {}
    out = []

    def entry(code, detail):
        c = CRITERIA[code]
        return {"code": code, "no": c["no"], "title": c["title"], "detail": detail}

    for i, r in enumerate(rows, 1):
        reject, check = [], []
        cit = (r.get("Citation") or "").strip()
        full = (r.get("Full reference (from PDF)") or "").strip()
        doif = (r.get("doi") or "").strip()
        blob = " ".join([doif, cit, full])
        doi = row_doi(r)
        pmid = (PMID_RE.search(blob) or [None, None])[1] if PMID_RE.search(blob) else None
        ref_full = full if full and not full.lower().startswith("not reported") else None
        has_citation = bool(cit) and not cit.lower().startswith("not reported")
        cit_ident = bool(re.search(r"\b(18|19|20)\d{2}\b", cit)) and bool(
            re.search(r"[A-Za-z]{4,}", re.sub(r"(?i)\b(file|pdf|project)\b", " ", cit)))
        pdfs = PDF_RE.findall(cit) + PDF_RE.findall(full)
        if not doi and not pmid and pdfs:
            k = norm_pdf(pdfs[0])
            e = enriched.get(k) or next((v for k2, v in enriched.items() if len(k) > 15 and (k2.endswith(k) or k.endswith(k2) or k2.startswith(k) or k.startswith(k2))), None)
            if e:
                doi, pmid, ref_full = e["doi"] or None, e["pmid"] or None, ref_full or (e["reference_full"] or None)

        # 2 and 1: the source
        if not has_citation:
            reject.append(entry("no_citation", "The Citation column is empty or says 'not reported'."))
        if not doi and not pmid and not ref_full and not cit_ident:
            reject.append(entry("no_source", "No DOI, no PubMed ID and no full reference; the citation "
                                + (f"\"{cit[:90]}\" names no author and year." if has_citation else "is missing.")))

        # 3: evidence
        if all(_empty(r.get(c)) for c in DATA_FIELDS):
            reject.append(entry("no_evidence", "Direction, the four change columns, magnitude, baseline, final and interferent "
                                               "concentration, platform and analyzer are all empty or 'not reported'."))

        # 8: duplicates, inside the table and against the analyte's other tables
        key = duplicate_key(r)
        if key in seen_here:
            reject.append(entry("duplicate", f"Identical to row {seen_here[key]} of this table (same source, platform, analyzer, concentrations and values)."))
        elif key in seen_elsewhere:
            reject.append(entry("duplicate", f"Identical to a row already in the database: {seen_elsewhere[key]}."))
        else:
            seen_here[key] = i

        # 9: the identifier
        if doif and not doif.lower().startswith("not reported") and not DOI_RE.search(doif):
            reject.append(entry("bad_identifier", f"The doi column holds \"{doif[:80]}\", which is not a DOI."))
        elif doi and doi_status is not None and doi_status.get(doi) is False:
            reject.append(entry("bad_identifier", f"doi.org does not know the DOI {doi}."))

        # 17: recorded verdict against the number
        pct = number(r.get("Percentage change (calculated)"))
        if pct is None:
            pct = number(r.get("Percentage change (as reported)"))
        v = verdict(r.get("Clinical significance vs user APS"))
        if pct is not None and v and aps is not None and abs(abs(pct) - aps) > 1e-9 and (abs(pct) > aps) != (v == "exceeds"):
            reject.append(entry("verdict_inconsistent",
                                f"The row says \"{v} APS\" but the change is {pct:g} % against an APS of {aps:g} %, which is "
                                f"{'beyond' if abs(pct) > aps else 'inside'} it. Recorded text: \"{(r.get('Clinical significance vs user APS') or '')[:140]}\""))

        # suggestions for the manual criteria
        an = _norm(r.get("Analyte"))
        if an and not any(n in an or (len(an) >= 3 and an in n) for n in names):
            check.append(entry("wrong_analyte", f"The analyte is written \"{(r.get('Analyte') or '')[:80]}\", which matches none of the names of {analyte.get('component') or analyte['folder']}."))
        notes = " ".join((r.get(c) or "") for c in ("Notes", "Study method details", "Magnitude of change (verbatim from source)", "Citation", "Additional sources of bias"))
        m = DOC_PROBLEM.search(notes)
        if m:
            check.append(entry("wrong_document", f"The row's text mentions a problem with the source file (\"{m.group(0)}\")."))
        out.append({"row": i, "reject": reject, "check": check})
    return out


def summary(result):
    """{code: count} over automatic rejections, plus totals."""
    counts = {}
    for r in result:
        for e in r["reject"]:
            counts[e["code"]] = counts.get(e["code"], 0) + 1
    return {"rows": len(result), "rejected": sum(1 for r in result if r["reject"]),
            "to_check": sum(1 for r in result if r["check"] and not r["reject"]), "by_criterion": counts}


REJECTED_FIELDS = ["source_file", "original_row", "criteria", "reason", "decided", "date"]


def archive_rejected(root, header, entries):
    """Append rejected rows, in full, to meta/rejected_rows.csv.
    entries: [{"source_file", "original_row", "criteria", "reason", "decided", "date", "values": {col: value}}]"""
    if not entries:
        return
    path = os.path.join(root, "meta", "rejected_rows.csv")
    old = []
    if os.path.exists(path):
        old = list(csv.DictReader(open(path, encoding="utf-8", newline="")))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REJECTED_FIELDS + list(header), extrasaction="ignore")
        w.writeheader()
        w.writerows(old)
        for e in entries:
            w.writerow({**{k: e.get(k, "") for k in REJECTED_FIELDS}, **e["values"]})
