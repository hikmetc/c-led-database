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
    21  animal_study          the specimen came from an animal, not from a human
    22  specimen_mismatch     the specimen is not the one the analyte is defined for (its
                              "system"): venous blood for an analyte defined in arterial blood,
                              plasma for an analyte defined in serum. Where the interferent itself
                              is about the specimen, the row is only pointed out, not rejected.

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
    "animal_study": dict(no=21, auto=True, title="Animal study: the specimen is not human"),
    "specimen_mismatch": dict(no=22, auto=True, title="The specimen is not the one the analyte is defined for"),
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


# --- criterion 21: animal studies -------------------------------------------------------------
# Only the specimen decides. An animal name alone proves nothing: reagents and interferents are
# often of animal origin (rabbit thromboplastin, bovine albumin, porcine heparin, ovine Fab,
# mouse monoclonal antibodies, HAMA), and such rows are about human samples.
_SPECIES = (r"rats?|mouse|mice|murine|rabbits?|dogs?|canine|beagles?|pigs?|piglets?|porcine|swine|minipigs?|sheep|ovine|lambs?|"
            r"goats?|caprine|bovine|cattle|cows?|calf|calves|horses?|equine|ponies|pony|cats?|feline|monkeys?|macaques?|baboons?|"
            r"guinea[- ]pigs?|hamsters?|ferrets?|rodents?|chickens?|alligators?")
_SPECIMEN = (r"(?:whole[- ])?blood|sera|serum|plasma|urine|erythrocytes?|red (?:blood )?cells?|h(?:a)?emolysates?|"
             r"(?:cavity |pleural |pericardial |body )?fluid|bile|specimens?|samples?")
_REAGENT = (r"gamma[- ]?globulin|globulin|albumin|thromboplastin|brain|lung|placenta|intestin\w*|mucosa|heparin|fab\b|antibod\w*|"
            r"immunoglobulin|igg\b|igm\b|anti[- ]\w+|thrombin|fibrinogen|collagen|tissue factor|factor [ivx]+|h(?:a)?emoglobin[- ]based|"
            r"polymeri[sz]ed|insulin|trypsin|pepsin|catalase|liver|kidney|pancrea\w*")
# "rat serum", "equine arterial blood", "heparinized rabbit carotid-artery blood": a species, then
# at most four words, then a specimen - unless one of those words names a reagent
ANIMAL_SPECIMEN = re.compile(rf"\b({_SPECIES})\b(?:[\s-]+(?!(?:{_REAGENT}))[\w.'-]+){{0,4}}?[\s-]+(?:{_SPECIMEN})\b", re.I)
# "plasma from 20 clinically normal dogs", "blood of six horses", "serum obtained from rabbits"
ANIMAL_DONOR = re.compile(rf"\b(?:{_SPECIMEN})\b[^.;()]{{0,60}}?\b(?:from|of|in|drawn from|obtained from|collected from)\b[^.;()]{{0,50}}?\b({_SPECIES})\b(?![\s-]+(?:{_REAGENT}))", re.I)
# strain or husbandry words that only describe animals
ANIMAL_STRAIN = re.compile(r"\b(wistar|sprague[- ]dawley|balb/?c|c57bl|swiss webster|new zealand white|client-owned|veterinary)\b", re.I)
ANIMAL_SUBJECTS = re.compile(rf"\b(?:animal (?:model|stud\w+|experiment\w*)|in (?:{_SPECIES})\b|administered to (?:the )?(?:{_SPECIES})\b|"
                             rf"(?:{_SPECIES}) (?:were|was) (?:given|dosed|injected|exposed|an(?:a)?esthetized|sacrificed|euthani[sz]ed))", re.I)
_REAGENT_AFTER = re.compile(rf"^[\s-]+(?:{_REAGENT})", re.I)


# "Whole blood (Dogs)", "Arterial blood, anesthetized dogs", "blood (transverse facial artery), healthy adult horses"
ANIMAL_AFTER = re.compile(rf"\b(?:{_SPECIMEN})\b[^.;]{{0,45}}?[(,]\s*(?:[\w-]+\s+){{0,3}}?({_SPECIES})\b", re.I)
# "In vivo (dog tongue probe)"
ANIMAL_INVIVO = re.compile(rf"\bin vivo\b[^.;]{{0,30}}?\b({_SPECIES})\b", re.I)
# a sample type that names humans is never rejected automatically: the animal word in it is
# then nearly always a reagent or an interferent ("human serum spiked with ... Fab (ovine)")
HUMAN_SPECIMEN = re.compile(r"\b(human|patients?|volunteers?|donors?|neonat\w*|infants?|children|adults? (?:men|women|volunteers?|patients?))\b", re.I)


def animal_specimen(sample_type):
    """The animal the specimen came from, or None. Deliberately strict: it answers yes only when
    the sample-type text itself says so, and never when that text also names humans."""
    t = sample_type or ""
    if HUMAN_SPECIMEN.search(t):
        return None
    for rx in (ANIMAL_SPECIMEN, ANIMAL_DONOR, ANIMAL_AFTER, ANIMAL_INVIVO):
        for m in rx.finditer(t):
            if _REAGENT_AFTER.match(t[m.end(1):]) or _REAGENT_AFTER.match(t[m.end():]):
                continue                                   # "bovine serum albumin", "rabbit brain thromboplastin"
            if re.search(r"\b(?:f(?:o)?etal|newborn)\s+$", t[:m.start(1)], re.I):
                continue                                   # "fetal bovine serum", "fetal calf serum": culture reagents
            return m.group(1).lower()
    m = ANIMAL_STRAIN.search(t)
    return m.group(1).lower() if m else None


# --- criterion 22: the specimen must be the one the analyte is defined for ---------------------
# The definition is data: the analyte's `system` in the registry ("Blood (arterial)", "Serum",
# "Serum or plasma", "Platelet-poor plasma (citrated)"). To accept another specimen for an
# analyte, change its system; nothing here names an analyte.
_VESSEL = {"arterial": r"arteri\w*|artery", "venous": r"venous|veins?|venipuncture",
           "capillary": r"capillar\w*|finger[- ]?(?:stick|prick)|heel[- ]?(?:stick|prick)"}
_MATRIX = {"serum": r"serum|sera", "plasma": r"plasma", "blood": r"whole[- ]blood|blood"}
# A row whose interference *is* the specimen (plasma measured instead of serum, venous instead of
# arterial blood, a body fluid in place of blood) is not rejected for its specimen: it is pointed
# out for a person to decide. Such causes carry one of these concepts in the registry, or say so
# in the interferent's own wording.
SPECIMEN_CONCEPTS = {"specimen_matrix", "sample_type"}
SPECIMEN_TOPIC = re.compile(r"venous|arterial|capillar|sample type|specimen type|sampling site|in place of|instead of|matrix", re.I)


def _tags(text, table):
    t = (text or "").lower()
    return {k for k, rx in table.items() if re.search(rf"\b(?:{rx})\b", t)}


def specimen_profile(text, definition=False):
    """(vessels, matrices) named in an analyte's system (definition=True) or in a sample type.

    A system is a definition: every matrix it names is accepted ("Plasma or blood" accepts both).
    A sample type is a description, and there the bare word "blood" next to serum or plasma
    usually tells where the serum came from ("Serum (blood drawn after 1 h)"), so it counts as a
    matrix of its own only when the text says "whole blood" or names neither serum nor plasma."""
    matrices = _tags(text, _MATRIX)
    if not definition and matrices & {"serum", "plasma"} and not re.search(r"\bwhole[- ]blood\b", (text or "").lower()):
        matrices.discard("blood")
    return _tags(text, _VESSEL), matrices


def accepted_specimens(system):
    """A sentence saying what a system accepts, for the manager's form."""
    vessels, matrices = specimen_profile(system, definition=True)
    names = {"serum": "serum", "plasma": "plasma", "blood": "whole blood"}
    if not matrices and not vessels:
        return "No specimen rule: this text names no matrix (serum, plasma, blood) and no vessel, so criterion 22 is not applied."
    parts = []
    if matrices:
        parts.append("accepts " + ", ".join(names[m] for m in ("serum", "plasma", "blood") if m in matrices)
                     + "; rejects " + (", ".join(names[m] for m in ("serum", "plasma", "blood") if m not in matrices) or "nothing"))
    if vessels:
        others = [v for v in ("arterial", "venous", "capillary") if v not in vessels]
        parts.append("only " + " or ".join(sorted(vessels)) + " blood" + (f"; rejects {' and '.join(others)}" if others else ""))
    else:
        parts.append("any vessel")
    return "Criterion 22 " + "; ".join(parts) + ". A sample type that does not say is never rejected."


def specimen_mismatch(system, sample_type):
    """('vessel' | 'matrix' | 'mixed' | None, explanation). A sample type that does not say
    which vessel or which matrix is never a mismatch: unknown is not wrong."""
    sys_v, sys_m = specimen_profile(system, definition=True)
    row_v, row_m = specimen_profile(sample_type)
    words = lambda s: " / ".join(sorted(s))
    if sys_v and row_v and not (row_v & sys_v):
        return "vessel", f"the analyte is defined in {words(sys_v)} blood (system \"{system}\"), the specimen is {words(row_v)}"
    if sys_m and row_m and not (row_m & sys_m):
        return "matrix", f"the analyte is defined in {words(sys_m)} (system \"{system}\"), the specimen is {words(row_m)}"
    if sys_v and row_v - sys_v:
        return "mixed", f"the analyte is defined in {words(sys_v)} blood, the specimen text names {words(row_v)}"
    return None, ""


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


def screen(rows, analyte, root, exclude_file=None, doi_status=None, concept=None):
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

        # 21: animal studies are excluded
        species = animal_specimen(r.get("Sample type"))
        if species:
            reject.append(entry("animal_study", f"The specimen is of animal origin (\"{species}\"): sample type \"{(r.get('Sample type') or '')[:140]}\"."))
        else:
            m2 = ANIMAL_SUBJECTS.search(" ".join((r.get(c) or "") for c in ("Sample type", "Study method details", "Analyte")))
            if m2:
                check.append(entry("animal_study", f"The row may describe an animal study (\"{m2.group(0)[:60]}\"); the sample type does not say so. "
                                                   "Reject it if the specimen was not human."))

        # 22: the specimen must be the one the analyte is defined for
        kind, why = specimen_mismatch(analyte.get("system"), r.get("Sample type"))
        if kind:
            st = (r.get("Sample type") or "")[:140]
            about_specimen = concept in SPECIMEN_CONCEPTS or bool(SPECIMEN_TOPIC.search(r.get("Interferent") or ""))
            if kind in ("vessel", "matrix") and not about_specimen:
                reject.append(entry("specimen_mismatch", f"{why[0].upper()}{why[1:]}: sample type \"{st}\"."))
            elif kind == "mixed":
                check.append(entry("specimen_mismatch", f"{why[0].upper()}{why[1:]}: sample type \"{st}\". Reject it if the result was not measured in the defined specimen."))
            else:
                check.append(entry("specimen_mismatch", f"{why[0].upper()}{why[1:]}, but the interferent (\"{(r.get('Interferent') or '')[:70]}\") is itself "
                                                        f"about the specimen, so the difference may be the point of the study: sample type \"{st}\"."))

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
