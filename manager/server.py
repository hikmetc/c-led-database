#!/usr/bin/env python3
"""Local back end of the database manager (a desktop app for the maintainer).

It serves the interface in manager/ui/ on 127.0.0.1 and does the work the interface asks for:
showing what the database holds on this Mac, on GitHub and on the website, importing runs of
the literature archive, changing or deleting evidence, and publishing.

Rules it enforces
  - Nothing changes without a plan. Every change is first described (`/api/plan`); it is carried
    out only when the same plan is confirmed (`/api/apply` with the plan's token).
  - A change is a transaction: edit, rebuild, validate, audit, commit locally. If any step fails,
    every file is restored to the last commit.
  - A local commit is the local backup. GitHub and the website change only on "publish" (a push),
    which is a separate, confirmed step.
  - Only the Python standard library is used; the build itself needs pyarrow (the project venv).

Run:  .venv/bin/python manager/server.py            (prints the address to open)
"""
import argparse, collections, csv, datetime, difflib, glob, http.server, importlib.util, io, json, os, re, secrets, shutil
import subprocess, sys, threading, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(HERE, "ui")
SCRIPTS = os.path.join(ROOT, "scripts")
PY = sys.executable
CONFIG_DIR = os.environ.get("MANAGER_CONFIG_DIR") or os.path.expanduser("~/Library/Application Support/EFLM-LED-Manager")
CONFIG = os.path.join(CONFIG_DIR, "config.json")
BUILD_ENV = dict(os.environ, CLED_ROOT=ROOT, CLED_REQUIRE_PARQUET="1", CLED_DISTRIBUTION="1")
csv.field_size_limit(10 ** 7)

spec = importlib.util.spec_from_file_location("cled_import_archive", os.path.join(SCRIPTS, "import_archive.py"))
IA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(IA)
spec = importlib.util.spec_from_file_location("cled_screening", os.path.join(SCRIPTS, "screening.py"))
SC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SC)


class Problem(Exception):
    """Something the user has to know about; shown as it is."""


# ----------------------------------------------------------------------------- small helpers
def sh(cmd, check=True, env=None, timeout=None):
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=env, timeout=timeout)
    if check and r.returncode != 0:
        raise Problem(f"{' '.join(cmd[:3])} failed: {(r.stderr or r.stdout).strip()[-600:]}")
    return r


def git(*args, check=True):
    return sh(["git", *args], check=check).stdout


def load_config():
    cfg = {"archive": os.path.expanduser("~/Desktop/Literature_Archive")}
    try:
        cfg.update(json.load(open(CONFIG, encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), indent=2)


def remote():
    """(owner, repo) of origin on GitHub, or (None, None)."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/.\s]+)", git("remote", "get-url", "origin", check=False))
    return m.groups() if m else (None, None)


def header():
    return [r["column"] for r in csv.DictReader(open(os.path.join(ROOT, "meta", "data_dictionary.csv"), encoding="utf-8"))]


def read_csv_text(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def read_table_file(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8-sig")
    rows = read_csv_text(text)
    out = io.StringIO(newline="")
    csv.writer(out).writerows(rows)
    return rows, out.getvalue().encode("utf-8") == raw     # rows, "rewriting keeps every byte"


def write_table_file(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)


def table_path(analyte, file):
    R = IA.load_registry()
    if analyte not in R.ANALYTES or file not in R.TABLE_MAP.get(analyte, {}):
        raise Problem(f"unknown table: {analyte}/{file}")
    return os.path.join(ROOT, analyte, "database", file)


def index_rows(text):
    """meta/file_index.csv -> {(analyte_folder, file): rows}"""
    return {(r["analyte_folder"], r["source_file"]): int(r["data_rows"]) for r in csv.DictReader(io.StringIO(text))}


def clip(s, n=140):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


# ----------------------------------------------------------------------------- state
_fetch = {"at": 0.0, "ok": False}


def fetch_origin(force=False):
    if force or time.time() - _fetch["at"] > 45:
        try:
            _fetch["ok"] = sh(["git", "fetch", "-q", "origin"], check=False, timeout=25).returncode == 0
        except subprocess.TimeoutExpired:
            _fetch["ok"] = False
        _fetch["at"] = time.time()
    return _fetch["ok"]


def head_info(ref):
    out = git("log", "-1", "--format=%h%x1f%s%x1f%cI", ref, check=False).strip().split("\x1f")
    return {"sha": out[0], "subject": out[1], "date": out[2]} if len(out) == 3 else None


def summarize_index(idx):
    return {"rows": sum(idx.values()), "tables": len(idx), "analytes": len({a for a, _ in idx})}


def website_state(owner, repo):
    if not owner:
        return {"reachable": False}
    url = f"https://{owner}.github.io/{repo}/"
    out = {"url": url, "reachable": False}
    try:
        with urllib.request.urlopen(url + "data/parquet/manifest.json", timeout=6) as r:
            man = json.load(r)
        out.update(reachable=True, rows=man.get("row_count"), analytes=len(man.get("files", {}).get("slim", {})),
                   by_analyte={k: v.get("rows") for k, v in man.get("files", {}).get("slim", {}).items()})
    except Exception:
        pass
    if shutil.which("gh"):
        try:
            r = sh(["gh", "run", "list", "--workflow", "pages.yml", "--limit", "1", "--json", "status,conclusion,headSha,url,createdAt"], check=False, timeout=12)
            runs = json.loads(r.stdout or "[]")
            if runs:
                out["last_run"] = runs[0]
        except (ValueError, subprocess.TimeoutExpired, OSError):
            pass
    return out


_last_state = {}


def state(fresh=False):
    if JOB["status"] == "running" and _last_state:
        return dict(_last_state, busy=JOB["id"])
    if fresh:
        _fetch["at"] = 0                # an explicit refresh asks GitHub again
    s = _state()
    _last_state.clear()
    _last_state.update(s)
    return s


def _state():
    owner, repo = remote()
    online = fetch_origin()
    local_idx = index_rows(open(os.path.join(ROOT, "meta", "file_index.csv"), encoding="utf-8").read())
    gh_text = git("show", "origin/main:meta/file_index.csv", check=False)
    gh_idx = index_rows(gh_text) if gh_text else {}
    ahead = git("log", "--format=%h%x1f%s%x1f%cI", "origin/main..HEAD", check=False).strip()
    commits = [dict(zip(("sha", "subject", "date"), l.split("\x1f"))) for l in ahead.splitlines() if l]
    behind = int(git("rev-list", "--count", "HEAD..origin/main", check=False).strip() or 0)
    changed = []
    for line in git("diff", "--name-status", "origin/main", "HEAD", "--", "*/database/*.csv", check=False).splitlines():
        kind, path = line.split("\t", 1)[0], line.split("\t")[-1]
        a, f = path.split("/")[0], os.path.basename(path)
        changed.append({"analyte": a, "file": f, "kind": {"A": "new", "D": "deleted"}.get(kind[0], "changed"),
                        "local_rows": local_idx.get((a, f)), "github_rows": gh_idx.get((a, f))})
    cfg = load_config()
    return {
        "repo": ROOT, "archive": cfg["archive"], "archive_exists": os.path.isdir(cfg["archive"]),
        "repo_url": f"https://github.com/{owner}/{repo}" if owner else None,
        "online": online,
        "local": dict(summarize_index(local_idx), head=head_info("HEAD")),
        "github": dict(summarize_index(gh_idx), head=head_info("origin/main")),
        "website": website_state(owner, repo),
        "unpublished": {"commits": commits, "tables": changed},
        "behind": behind,
        "uncommitted": IA.changed_files(),
        "busy": JOB["id"] if JOB["status"] == "running" else None,
    }


def database():
    R = IA.load_registry()
    analytes = json.load(open(os.path.join(ROOT, "meta", "analytes.json"), encoding="utf-8"))
    local = list(csv.DictReader(open(os.path.join(ROOT, "meta", "file_index.csv"), encoding="utf-8")))
    gh_text = git("show", "origin/main:meta/file_index.csv", check=False)
    gh_idx = index_rows(gh_text) if gh_text else {}
    status = {}
    for line in git("diff", "--name-status", "origin/main", "HEAD", "--", "*/database/*.csv", check=False).splitlines():
        status[line.split("\t")[-1]] = {"A": "new", "D": "deleted"}.get(line[0], "changed")
    out = []
    for a in analytes:
        folder = a["analyte_folder"]
        tables = []
        for r in local:
            if r["analyte_folder"] != folder:
                continue
            f = r["source_file"]
            tables.append({"file": f, "interferent_id": r["default_interferent_id"], "interferent": r["default_interferent"],
                           "rows": int(r["data_rows"]), "github_rows": gh_idx.get((folder, f)),
                           "status": status.get(f"{folder}/database/{f}", "published"),
                           "multi": bool(R.OVERRIDES.get(folder, {}).get(f))})
        tables.sort(key=lambda t: t["interferent"].lower())
        used = collections.Counter(R.TABLE_MAP[folder].values())
        causes = [{"key": k, "name": v[0], "concept": v[1], "tables": used.get(k, 0)} for k, v in sorted(R.CANON[folder].items(), key=lambda x: x[1][0].lower())]
        reg = R.ANALYTES[folder]
        out.append({"folder": folder, "id": a["analyte_id"], "component": a["component"], "system": a["system"],
                    "unit": a["unit"], "aps": a["aps_percent"], "rows": a["evidence_rows"], "tables": tables, "causes": causes,
                    "kind_of_property": reg["kind_of_property"], "aps_note": reg.get("aps_note", ""), "synonyms": reg.get("synonyms", "")})
    return out


def table(analyte, file):
    path = table_path(analyte, file)
    rows, stable = read_table_file(path)
    prefix = IA.load_registry().ANALYTES[analyte]["prefix"]
    stem = os.path.splitext(file)[0]
    dictionary = json.load(open(os.path.join(ROOT, "meta", "data_dictionary.json"), encoding="utf-8"))
    return {"analyte": analyte, "file": file, "columns": rows[0], "rows": rows[1:],
            "row_ids": [f"{prefix}.{stem}.{i:04d}" for i in range(1, len(rows))],
            "definitions": {d["column"]: d["definition"] for d in dictionary}, "byte_stable": stable}


# ----------------------------------------------------------------------------- the archive
def left_out_rows(hdr):
    """Rows that were deliberately left out of a table: {table path: {row values}}.
    They come from the two archives the database keeps (rows without evidence, rejected rows)."""
    out = collections.defaultdict(collections.Counter)      # a multiset: a duplicate is left out once, its original stays
    for name in ("removed_rows.csv", "rejected_rows.csv"):
        p = os.path.join(ROOT, "meta", name)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8", newline="")):
                out[r.get("source_file", "")][tuple((r.get(c) or "") for c in hdr)] += 1
    return out


def archive_runs():
    cfg = load_config()
    base = cfg["archive"]
    if not os.path.isdir(base):
        return []
    hdr = header()
    R = IA.load_registry()
    left_out = left_out_rows(hdr)
    runs = []
    for run_dir in sorted(glob.glob(os.path.join(base, "*__*", "*"))):
        ext = os.path.join(run_dir, "04_extraction")
        if not os.path.isdir(ext):
            continue
        tables = sorted((f for f in glob.glob(os.path.join(ext, "*.csv")) if IA.version_of(os.path.basename(f))),
                        key=lambda f: IA.version_of(os.path.basename(f)))
        params = {}
        try:
            params = json.load(open(os.path.join(run_dir, "00_parameters.json"), encoding="utf-8"))
        except (OSError, ValueError):
            pass
        item = {"path": run_dir, "topic": os.path.basename(os.path.dirname(run_dir)), "run": os.path.basename(run_dir),
                "analyte": params.get("analyte"), "interferent": params.get("interferent"),
                "aps": params.get("aps", {}).get("percent"), "created": params.get("created"),
                "versions": len(tables)}
        if not tables:
            runs.append(dict(item, status="no_table", note="No extraction table in this run yet."))
            continue
        src = tables[-1]
        item["table"] = os.path.basename(src)
        try:
            text, n = IA.read_table(src, hdr)
        except IA.Stop as e:
            runs.append(dict(item, status="invalid", note=str(e).splitlines()[0]))
            continue
        item["rows"] = n
        dest_name = re.sub(r"_extraction_table_v\d+\.csv$", "_extraction_table.csv", os.path.basename(src))
        scope = params.get("scope", {})
        texts = [params.get("analyte"), item["topic"].split("__")[0], dest_name.split("_")[0], (scope.get("analyte_original") or "").split("(")[0]]
        hits = IA.find_analyte(R, texts)
        folder = hits[0] if len(hits) == 1 else None
        item["analyte_folder"] = folder
        dest = os.path.join(ROOT, folder, "database", dest_name) if folder else None
        # rows of this run that were left out on purpose (no evidence, or rejected by the screening)
        skipped = collections.Counter(left_out.get(f"{folder}/database/{dest_name}", {})) if folder else collections.Counter()
        src_rows = [tuple(r) for r in read_csv_text(text)[1:] if any((v or "").strip() for v in r)]
        wanted = []
        for r in reversed(src_rows):                 # of identical rows, the later ones are the ones left out
            if skipped[r] > 0:
                skipped[r] -= 1
            else:
                wanted.append(r)
        wanted.reverse()
        if len(wanted) != len(src_rows):
            item["left_out"] = len(src_rows) - len(wanted)
        if dest and os.path.exists(dest):
            have = [tuple(r) for r in read_csv_text(open(dest, encoding="utf-8-sig", newline="").read())[1:] if any((v or "").strip() for v in r)]
            item.update(status="imported" if have == wanted else "update", local_rows=len(have))
        elif src_rows and not wanted:
            item.update(status="rejected", note="Every row of this run was left out by the inclusion criteria.")
        else:
            item["status"] = "new"
        runs.append(item)
    order = {"new": 0, "update": 1, "invalid": 2, "no_table": 3, "rejected": 4, "imported": 5}
    runs.sort(key=lambda r: (order.get(r["status"], 9), r.get("created") or ""), reverse=False)
    return runs


def run_proposal(path):
    """What the importer would do with a run, and what it still needs to be told."""
    hdr = header()
    run_dir, src, params = IA.resolve_source(path)
    text, n = IA.read_table(src, hdr)
    R = IA.load_registry()
    dest_name = re.sub(r"_extraction_table_v\d+\.csv$", "_extraction_table.csv", os.path.basename(src))
    scope = params.get("scope", {})
    topic = params.get("folder", {}).get("topic", "").split("__")[0]
    hits = IA.find_analyte(R, [params.get("analyte"), topic, dest_name.split("_")[0], (scope.get("analyte_original") or "").split("(")[0]])
    folder = hits[0] if len(hits) == 1 else None
    label = params.get("interferent") or scope.get("interferent_original") or ""
    key = IA.slug(label)
    registered = bool(folder) and dest_name in R.TABLE_MAP[folder]
    causes = {f: [{"key": k, "name": v[0], "concept": v[1]} for k, v in sorted(c.items())] for f, c in R.CANON.items()}
    suggestion = None
    if folder:
        if registered:
            suggestion = R.TABLE_MAP[folder][dest_name]
        elif key in R.CANON[folder]:
            suggestion = key
    concepts = sorted({c for a in R.CANON.values() for _, c in a.values()})
    return {
        "path": path, "table": os.path.basename(src), "rows": n, "dest_name": dest_name,
        "analyte_label": params.get("analyte") or topic, "interferent_label": label,
        "aps": params.get("aps", {}).get("percent"),
        "analyte_folder": folder, "registered": registered,
        "analytes": [{"folder": f, "component": a["component"], "system": a["system"], "aps": a["aps_percent"]} for f, a in R.ANALYTES.items()],
        "causes": causes, "interferent_key": suggestion, "new_key": key,
        "new_name": scope.get("interferent_original") or label.capitalize(),
        "concepts": concepts, "concept_guess": (difflib.get_close_matches(key, concepts, n=1, cutoff=0.6) or [None])[0],
        "tables_by_cause": {f: {k: [t for t, kk in m.items() if kk == k and t != dest_name] for k in set(m.values())} for f, m in R.TABLE_MAP.items()},
    }


def importer_args(p):
    args = [p["path"]]
    for flag, k in (("--analyte-folder", "analyte_folder"), ("--interferent-key", "interferent_key"),
                    ("--interferent-name", "interferent_name"), ("--concept", "concept"), ("--prefix", "prefix"),
                    ("--component", "component"), ("--system", "system"), ("--kind-of-property", "kind_of_property"),
                    ("--unit", "unit"), ("--aps", "aps")):
        v = p.get(k)
        if v not in (None, ""):
            args += [flag, str(v)]
    if "prefix" in p:                                  # a new analyte: synonyms may be empty
        args += ["--synonyms", str(p.get("synonyms") or "").strip()]
    if p.get("allow_duplicate"):
        args.append("--allow-duplicate-cause")
    if p.get("rejects"):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        path = os.path.join(CONFIG_DIR, "rejects.json")
        json.dump(p["rejects"], open(path, "w", encoding="utf-8"))
        args += ["--reject-json", path]
    return args


# ----------------------------------------------------------------------------- screening
def screening(body):
    """Screen an archive run (before import) or a table of the database against the rejection criteria."""
    R = IA.load_registry()
    hdr = header()
    if body.get("kind") == "run":
        _, src, _ = IA.resolve_source(body["path"])
        text, _ = IA.read_table(src, hdr)
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
        folder = body.get("analyte_folder") or ""
        dest_name = re.sub(r"_extraction_table_v\d+\.csv$", "_extraction_table.csv", os.path.basename(src))
        if folder in R.ANALYTES:
            info = dict(R.ANALYTES[folder], folder=folder)
        else:
            info = {"folder": folder or "new_analyte", "component": body.get("component"), "prefix": body.get("prefix"),
                    "synonyms": body.get("synonyms"), "aps_percent": float(body["aps"]) if body.get("aps") not in (None, "") else None}
        exclude, label = dest_name, os.path.basename(src)
    else:
        folder, file = body["analyte"], body["file"]
        raw, _ = read_table_file(table_path(folder, file))
        rows = [dict(zip(raw[0], r)) for r in raw[1:]]
        info = dict(R.ANALYTES[folder], folder=folder)
        exclude, label = file, file
    doi_status = None
    if body.get("check_dois"):
        doi_status = SC.check_dois([d for d in (SC.row_doi(r) for r in rows) if d], os.path.join(CONFIG_DIR, "doi_cache.json"))
    result = SC.screen(rows, info, ROOT, exclude_file=exclude, doi_status=doi_status)
    for res, r in zip(result, rows):
        pct = SC.number(r.get("Percentage change (calculated)"))
        res["preview"] = {"interferent": clip(r.get("Interferent"), 70), "platform": clip(r.get("Platform/Brand/Method"), 60),
                          "change": pct if pct is not None else SC.number(r.get("Percentage change (as reported)")),
                          "citation": clip(r.get("Citation"), 90)}
    unchecked = sum(1 for v in (doi_status or {}).values() if v is None)
    return {"label": label, "aps": info.get("aps_percent"), "aps_note": info.get("aps_note", ""),
            "summary": SC.summary(result), "rows": [r for r in result if r["reject"] or r["check"]],
            "criteria": {k: {"no": v["no"], "title": v["title"], "auto": v["auto"]} for k, v in SC.CRITERIA.items()},
            "dois_checked": doi_status is not None, "dois_unreachable": unchecked}


def screening_all():
    """Screen every table of the database; one summary line per table that has something to show."""
    R = IA.load_registry()
    out = []
    for folder in R.ANALYTES:
        info = dict(R.ANALYTES[folder], folder=folder)
        for file in sorted(R.TABLE_MAP[folder]):
            raw, _ = read_table_file(os.path.join(ROOT, folder, "database", file))
            rows = [dict(zip(raw[0], r)) for r in raw[1:]]
            sm = SC.summary(SC.screen(rows, info, ROOT, exclude_file=file))
            if sm["rejected"] or sm["to_check"]:
                out.append(dict(sm, analyte=folder, component=info["component"], file=file))
    out.sort(key=lambda t: (-t["rejected"], -t["to_check"]))
    return {"tables": out, "criteria": {k: {"no": v["no"], "title": v["title"], "auto": v["auto"]} for k, v in SC.CRITERIA.items()}}


def analyte_block(folder, a):
    q = IA.pystr
    return (f' {q(folder)}: dict(\n    prefix={q(a["prefix"])}, component={q(a["component"])}, system={q(a["system"])},\n'
            f'    kind_of_property={q(a["kind_of_property"])}, unit={q(a["unit"])},\n'
            f'    aps_percent={float(a["aps_percent"])!r}, aps_note={q(a.get("aps_note", ""))},\n    synonyms={q(a.get("synonyms", ""))}),\n')


def _section(text, name):
    d = re.compile(rf"^{name}\s*=\s*\{{\s*$", re.M).search(text)
    end = re.compile(r"^\}\s*$", re.M).search(text, d.end())
    return d.end(), end.start()


def _cut(text, name, pattern, replacement=""):
    a, b = _section(text, name)
    m = re.compile(pattern, re.M | re.S).search(text, a, b)
    if not m:
        raise Problem(f"could not find the {name} entry in scripts/registry.py; edit it by hand")
    return text[:m.start()] + replacement + text[m.end():]


def registry_edit_analyte(folder, changes):
    R = IA.load_registry()
    new = dict(R.ANALYTES[folder])
    new.update(changes)
    text = open(IA.REGISTRY, encoding="utf-8").read()
    text = _cut(text, "ANALYTES", rf'^[ \t]*"{re.escape(folder)}":[ \t]*dict\(.*?\),[ \t]*\n', analyte_block(folder, new))
    expected = {f: dict(v) for f, v in R.ANALYTES.items()}
    expected[folder] = {k: new.get(k, "") for k in ("prefix", "component", "system", "kind_of_property", "unit", "aps_percent", "aps_note", "synonyms")}
    expected[folder]["aps_percent"] = float(expected[folder]["aps_percent"])
    return text, expected, R


def registry_without_analyte(folder):
    R = IA.load_registry()
    text = open(IA.REGISTRY, encoding="utf-8").read()
    f = re.escape(folder)
    text = _cut(text, "ANALYTES", rf'^[ \t]*"{f}":[ \t]*dict\(.*?\),[ \t]*\n')
    for name in ("CANON", "TABLE_MAP"):
        text = _cut(text, name, rf'^[ \t]*"{f}":[ \t]*\{{[ \t]*\n.*?^\s{{0,2}}\}},[ \t]*\n')
    if folder in R.OVERRIDES:
        a, b = _section(text, "OVERRIDES")
        m = re.compile(rf'^[ \t]*"{f}":[ \t]*\{{\}},[ \t]*\n', re.M).search(text, a, b)
        if m:
            text = text[:m.start()] + text[m.end():]
        else:
            text = _cut(text, "OVERRIDES", rf'^[ \t]*"{f}":[ \t]*\{{[ \t]*\n.*?^\s{{0,2}}\}},[ \t]*\n')
    return text, R


def registry_rename_cause(folder, key, name, concept):
    R = IA.load_registry()
    text = open(IA.REGISTRY, encoding="utf-8").read()
    a, b = _section(text, "CANON")
    h = re.compile(rf'^"{re.escape(folder)}":\s*\{{\s*$', re.M).search(text, a, b)
    e = re.compile(r"^\s{0,2}\},\s*$", re.M).search(text, h.end())
    m = re.compile(rf'^[ \t]*"{re.escape(key)}":[ \t]*\(.*\),[ \t]*\n', re.M).search(text, h.end(), e.start())
    if not m:
        raise Problem(f"could not find cause \"{key}\" in scripts/registry.py; edit it by hand")
    text = text[:m.start()] + f" {IA.pystr(key)}: ({IA.pystr(name)}, {IA.pystr(concept)}),\n" + text[m.end():]
    expected = {f: dict(v) for f, v in R.CANON.items()}
    expected[folder][key] = (name, concept)
    return text, expected, R


# ----------------------------------------------------------------------------- registry edits
def registry_without_table(analyte, file):
    """New text of registry.py with one table (and causes nothing uses any more) removed."""
    R = IA.load_registry()
    text = open(IA.REGISTRY, encoding="utf-8").read()
    key = R.TABLE_MAP[analyte][file]
    exp_map = {a: dict(m) for a, m in R.TABLE_MAP.items()}
    exp_over = {a: dict(m) for a, m in R.OVERRIDES.items()}
    exp_canon = {a: dict(m) for a, m in R.CANON.items()}
    del exp_map[analyte][file]
    had_override = file in exp_over.get(analyte, {})
    exp_over.get(analyte, {}).pop(file, None)
    used = set(exp_map[analyte].values()) | {k for rules in exp_over.get(analyte, {}).values() for _, k in rules}
    dropped = [k for k in ([key] + [k for _, k in R.OVERRIDES.get(analyte, {}).get(file, [])]) if k not in used and k in exp_canon[analyte]]
    dropped = list(dict.fromkeys(dropped))
    for k in dropped:
        del exp_canon[analyte][k]

    def section(name):
        d = re.compile(rf"^{name}\s*=\s*\{{\s*$", re.M).search(text)
        end = re.compile(r"^\}\s*$", re.M).search(text, d.end())
        return d.end(), end.start()

    def cut(pattern, name):
        nonlocal text
        a, b = section(name)
        m = re.compile(pattern, re.M | re.S).search(text, a, b)
        if not m:
            raise Problem(f"could not find the {name} entry to remove in scripts/registry.py; edit it by hand")
        text = text[:m.start()] + text[m.end():]

    cut(rf'^[ \t]*"{re.escape(file)}":[ \t]*"{re.escape(key)}",[ \t]*\n', "TABLE_MAP")
    if had_override:
        cut(rf'^[ \t]*"{re.escape(file)}":[ \t]*\[.*?\],[ \t]*\n', "OVERRIDES")
    for k in dropped:
        a, b = section("CANON")
        h = re.compile(rf'^"{re.escape(analyte)}":\s*\{{\s*$', re.M).search(text, a, b)
        e = re.compile(r"^\s{0,2}\},\s*$", re.M).search(text, h.end())
        m = re.compile(rf'^[ \t]*"{re.escape(k)}":[ \t]*\(.*\),[ \t]*\n', re.M).search(text, h.end(), e.start())
        if not m:
            raise Problem(f"could not find cause \"{k}\" in scripts/registry.py; edit it by hand")
        text = text[:m.start()] + text[m.end():]
    return text, {"TABLE_MAP": exp_map, "OVERRIDES": exp_over, "CANON": exp_canon}, dropped, R


# ----------------------------------------------------------------------------- plans
PLANS = {}


def new_plan(op, params, title, lines, warnings=(), where=()):
    token = secrets.token_urlsafe(16)
    PLANS.clear()                       # one pending plan at a time
    PLANS[token] = {"op": op, "params": params, "at": time.time()}
    return {"token": token, "title": title, "lines": list(lines), "warnings": list(warnings), "where": list(where)}


LOCAL_ONLY = ["This Mac: the change is made and saved as a local commit (your local backup).",
              "GitHub and the website: not touched until you choose Publish."]


def plan(body):
    op = body.get("op")
    if JOB["status"] == "running":
        raise Problem("Another operation is still running. Wait for it to finish.")
    if op != "publish" and IA.changed_files():
        raise Problem("The repository has uncommitted changes that this app did not make. Commit or discard them first (git status).")

    if op == "import":
        r = sh([PY, os.path.join(SCRIPTS, "import_archive.py"), *importer_args(body), "--dry-run"], check=False, env=BUILD_ENV)
        text = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            raise Problem(text.replace("STOPPED: ", "").strip() or "the importer could not plan this run")
        if "Nothing to do" in text:
            raise Problem(text)
        lines = [l.rstrip() for l in text.splitlines() if l.strip() and not set(l.strip()) <= {"="} and "dry-run" not in l and l.strip() != "Import plan"]
        warnings = [l.strip().replace("WARNING: ", "") for l in lines if "WARNING" in l]
        cont = [l.strip() for l in lines if l.startswith("           ")]
        if cont and warnings:
            warnings[-1] += " " + " ".join(cont)
        lines = [l.strip() for l in lines if "WARNING" not in l and not l.startswith("           ")]
        lines.append("Rows without any evidence (all 11 data fields empty) are removed before the import.")
        return new_plan(op, body, "Import a run of the archive", lines, warnings, LOCAL_ONLY)

    if op == "change_table":
        analyte, file = body["analyte"], body["file"]
        path = table_path(analyte, file)
        rows, stable = read_table_file(path)
        hdr, data = rows[0], rows[1:]
        prefix = IA.load_registry().ANALYTES[analyte]["prefix"]
        rid = lambda i: f"{prefix}.{os.path.splitext(file)[0]}.{i:04d}"
        edits, deletes, adds = body.get("edits") or [], sorted(set(body.get("deletes") or [])), body.get("adds") or []
        if not (edits or deletes or adds):
            raise Problem("There is nothing to change.")
        lines, warnings = [f"Table: {analyte}/database/{file} ({len(data)} rows)"], []
        for e in edits:
            i, col = int(e["row"]), e["column"]
            if not (1 <= i <= len(data)) or col not in hdr:
                raise Problem("an edit points to a row or column that does not exist; reload the table")
            if i in deletes:
                continue
            old = data[i - 1][hdr.index(col)]
            if old == e["value"]:
                continue
            lines.append(f"Change  {rid(i)}  ·  {col}:  \"{clip(old, 90)}\"  →  \"{clip(e['value'], 90)}\"")
        for i in deletes:
            if not (1 <= i <= len(data)):
                raise Problem("a row to delete does not exist; reload the table")
            lines.append(f"Delete  {rid(i)}  ·  {clip(data[i - 1][hdr.index('Interferent')], 60)}  ·  {clip(data[i - 1][hdr.index('Citation')], 60)}")
        for a in adds:
            if not any((a.get(c) or "").strip() for c in hdr):
                raise Problem("a new row is completely empty")
            lines.append(f"Add a row at the end  ·  {clip(a.get('Interferent'), 60)}  ·  {clip(a.get('Citation'), 60)}")
        if len(lines) == 1:
            raise Problem("There is nothing to change: every edited value equals the current value.")
        if len(deletes) >= len(data) and not adds:
            raise Problem("This would delete every row. Use \"Delete table\" instead.")
        if deletes:
            later = len(data) - deletes[0] - (len(deletes) - 1)
            if later > 0:
                warnings.append(f"Deleting rows renumbers the {later} rows after the first deleted one, so their row ids and "
                                "permalinks on the website change. Deleted rows cannot be restored from the app once published "
                                "(they remain in the git history).")
        if not stable:
            warnings.append("This file is stored with unusual quoting; saving rewrites it in the standard CSV form. No other value changes.")
        return new_plan(op, body, "Change evidence rows", lines, warnings, LOCAL_ONLY)

    if op == "delete_table":
        analyte, file = body["analyte"], body["file"]
        path = table_path(analyte, file)
        rows, _ = read_table_file(path)
        _, _, dropped, R = registry_without_table(analyte, file)
        if len(R.TABLE_MAP[analyte]) <= 1:
            raise Problem("This is the last table of the analyte. Removing a whole analyte is not supported by the app; it has to be done by hand (see STRUCTURE.md).")
        lines = [f"Delete the table {analyte}/database/{file} with all its {len(rows) - 1} evidence rows.",
                 "Remove the table from scripts/registry.py."]
        for k in dropped:
            lines.append(f"Remove the interference cause \"{R.CANON[analyte][k][0]}\" ({R.ANALYTES[analyte]['prefix']}.{k}): no other table uses it.")
        warnings = ["Every row id and permalink of this table stops working on the website after publishing.",
                    "The rows are not archived elsewhere by the app; they remain only in the git history."]
        return new_plan(op, body, "Delete an evidence table", lines, warnings, LOCAL_ONLY)

    if op == "reject_rows":
        analyte, file = body["analyte"], body["file"]
        rows, stable = read_table_file(table_path(analyte, file))
        rejects = body.get("rejects") or []
        if not rejects:
            raise Problem("No row is marked for rejection.")
        if len({int(r["row"]) for r in rejects}) >= len(rows) - 1:
            raise Problem("This would reject every row of the table. Use \"Delete table\" instead.")
        prefix = IA.load_registry().ANALYTES[analyte]["prefix"]
        by = collections.Counter(c for r in rejects for c in r["criteria"].split("; "))
        lines = [f"Table: {analyte}/database/{file} ({len(rows) - 1} rows)",
                 f"Reject {len(rejects)} row{'s' if len(rejects) != 1 else ''} and remove {'them' if len(rejects) != 1 else 'it'} from the table:"]
        lines += [f"   {n:4d}  criterion {c}" for c, n in by.most_common()]
        lines.append("")
        for r in sorted(rejects, key=lambda r: int(r["row"]))[:60]:
            i = int(r["row"])
            if not (1 <= i < len(rows)):
                raise Problem("a row to reject does not exist; screen the table again")
            lines.append(f"{prefix}.{os.path.splitext(file)[0]}.{i:04d}  [{r['criteria']}]  {clip(r['reason'], 170)}")
        if len(rejects) > 60:
            lines.append(f"... and {len(rejects) - 60} more")
        lines.append("")
        lines.append("Every rejected row is archived in full, with its reasons, in meta/rejected_rows.csv.")
        first = min(int(r["row"]) for r in rejects)
        warnings = [f"Removing rows renumbers the {len(rows) - 1 - first - (len(rejects) - 1)} rows after the first rejected one, so their row ids and permalinks change."]
        if not stable:
            warnings.append("This file is stored with unusual quoting; saving rewrites it in the standard CSV form. No other value changes.")
        return new_plan(op, body, "Reject rows that fail the inclusion criteria", lines, warnings, LOCAL_ONLY)

    if op == "edit_analyte":
        folder = body["analyte"]
        R = IA.load_registry()
        if folder not in R.ANALYTES:
            raise Problem(f"unknown analyte: {folder}")
        old = R.ANALYTES[folder]
        changes = {}
        for k in ("component", "system", "kind_of_property", "unit", "aps_note", "synonyms"):
            if k in body and str(body[k]).strip() != str(old.get(k, "")).strip():
                changes[k] = str(body[k]).strip()
        if "aps_percent" in body:
            try:
                aps = float(str(body["aps_percent"]).replace(",", "."))
            except ValueError:
                raise Problem("The APS must be a number, in percent.")
            if not (0 < aps <= 1000):
                raise Problem("The APS must be greater than 0 and at most 1000 percent.")
            if abs(aps - float(old["aps_percent"])) > 1e-12:
                changes["aps_percent"] = aps
        for k in ("component", "system", "kind_of_property", "unit"):
            if k in changes and not changes[k]:
                raise Problem(f"{k.replace('_', ' ')} cannot be empty.")
        if not changes:
            raise Problem("Nothing was changed.")
        registry_edit_analyte(folder, changes)          # fails early if the registry entry cannot be found
        body = dict(body, changes=changes)
        n = sum(1 for _ in glob.glob(os.path.join(ROOT, folder, "database", "*.csv")))
        lines = [f"Analyte: {old['component']} ({folder}, id prefix {old['prefix']})"]
        lines += [f"{k.replace('_', ' ')}:  \"{old.get(k, '')}\"  \u2192  \"{v}\"" for k, v in changes.items()]
        lines.append("The folder name and the id prefix stay the same, so no row id changes.")
        warnings = []
        if "aps_percent" in changes:
            warnings.append(f"The APS changes from {old['aps_percent']} % to {changes['aps_percent']} %. Every numeric verdict of this analyte "
                            f"(all {n} tables) is recomputed against the new APS, on this Mac now and on the website after publishing. "
                            "The verdict text inside the tables was written for the old APS and is not rewritten; the screening may flag "
                            "rows whose recorded verdict no longer matches (criterion 17).")
        if "component" in changes:
            warnings.append("The analyte's name changes everywhere it is shown: website pages, search, README.")
        return new_plan(op, body, "Change an analyte", lines, warnings, LOCAL_ONLY)

    if op == "delete_analyte":
        folder = body["analyte"]
        R = IA.load_registry()
        if folder not in R.ANALYTES:
            raise Problem(f"unknown analyte: {folder}")
        if len(R.ANALYTES) <= 1:
            raise Problem("This is the last analyte; the database cannot be emptied from the app.")
        registry_without_analyte(folder)
        idx = index_rows(open(os.path.join(ROOT, "meta", "file_index.csv"), encoding="utf-8").read())
        mine = {f: n for (a, f), n in idx.items() if a == folder}
        lines = [f"Delete the analyte {R.ANALYTES[folder]['component']} ({folder}) completely:",
                 f"   {len(mine)} evidence tables with {sum(mine.values())} rows",
                 f"   {len(R.CANON[folder])} interference causes",
                 f"   the folder {folder}/ and its entries in scripts/registry.py", "", "Tables:"]
        lines += [f"   {f}  ({n} rows)" for f, n in sorted(mine.items())]
        warnings = ["After publishing, the analyte's page, all its interferent pages and every row permalink disappear from the website.",
                    "The rows are not archived by the app; they remain only in the git history. This is the largest deletion the app can make."]
        return new_plan(op, body, "Delete an analyte", lines, warnings, LOCAL_ONLY)

    if op == "rename_cause":
        folder, key = body["analyte"], body["key"]
        R = IA.load_registry()
        if key not in R.CANON.get(folder, {}):
            raise Problem(f"unknown interference cause: {folder}/{key}")
        old_name, old_concept = R.CANON[folder][key]
        name = str(body.get("name", "")).strip()
        concept = IA.slug(str(body.get("concept", old_concept)))
        if not name or not concept:
            raise Problem("A cause needs a name and a concept.")
        if (name, concept) == (old_name, old_concept):
            raise Problem("Nothing was changed.")
        registry_rename_cause(folder, key, name, concept)
        lines = [f"Interference cause {R.ANALYTES[folder]['prefix']}.{key} of {R.ANALYTES[folder]['component']}"]
        if name != old_name:
            lines.append(f"name:  \"{old_name}\"  \u2192  \"{name}\"")
        if concept != old_concept:
            lines.append(f"concept:  \"{old_concept}\"  \u2192  \"{concept}\"")
        lines.append("The cause's id stays the same, so no row id and no address changes. The verbatim wording in the rows is not touched.")
        warnings = []
        if concept != old_concept:
            known = {c for a in R.CANON.values() for _, c in a.values()}
            warnings.append(f"The cause moves to the concept \"{concept}\" in the website's matrix and concept pages"
                            + ("." if concept in known else ", which is a new concept (it gets its own row in the matrix)."))
        return new_plan(op, body, "Rename an interference cause", lines, warnings, LOCAL_ONLY)

    if op == "publish":
        if IA.changed_files():
            raise Problem("There are uncommitted changes that this app did not make. Commit or discard them first.")
        fetch_origin(force=True)
        commits = git("log", "--format=%h  %s", "origin/main..HEAD").strip().splitlines()
        if not commits:
            raise Problem("Everything on this Mac is already on GitHub.")
        if int(git("rev-list", "--count", "HEAD..origin/main").strip() or 0):
            raise Problem("GitHub has changes that are not on this Mac. Use \"Update this Mac\" first.")
        owner, repo = remote()
        stat = git("diff", "--stat", "origin/main", "HEAD", "--", "*/database/*.csv").strip().splitlines()
        lines = [f"Send {len(commits)} local change{'s' if len(commits) != 1 else ''} to GitHub:"] + ["   " + c for c in commits]
        if stat:
            lines += ["Evidence tables affected:"] + ["   " + s.strip() for s in stat[:-1]][:20]
        where = [f"GitHub (github.com/{owner}/{repo}): updated at once. The repository is public.",
                 "Website: GitHub rebuilds the data and the site and runs the tests; the change is visible a few minutes later.",
                 "This cannot be undone from the app. A published change stays in the public history."]
        return new_plan(op, body, "Publish to GitHub and the website", lines, [], where)

    if op == "discard":
        commits = git("log", "--format=%h  %s", "origin/main..HEAD").strip().splitlines()
        if not commits:
            raise Problem("There is nothing unpublished to discard.")
        lines = [f"Throw away {len(commits)} unpublished local change{'s' if len(commits) != 1 else ''}:"] + ["   " + c for c in commits]
        return new_plan(op, body, "Discard unpublished changes", lines,
                        ["This cannot be undone. The local database goes back to exactly what is on GitHub."],
                        ["This Mac: the listed changes are removed.", "GitHub and the website: not touched."])

    if op == "pull":
        fetch_origin(force=True)
        n = int(git("rev-list", "--count", "HEAD..origin/main").strip() or 0)
        if not n:
            raise Problem("This Mac already has everything that is on GitHub.")
        if git("log", "--format=%h", "origin/main..HEAD").strip():
            raise Problem("This Mac has unpublished changes and GitHub has other changes. This needs to be merged by hand (git).")
        lines = [f"Bring {n} change{'s' if n != 1 else ''} from GitHub to this Mac:"] + ["   " + c for c in git("log", "--format=%h  %s", "HEAD..origin/main").strip().splitlines()]
        return new_plan(op, body, "Update this Mac from GitHub", lines, [], ["This Mac: updated and rebuilt.", "GitHub and the website: not touched."])

    raise Problem(f"unknown operation: {op}")


# ----------------------------------------------------------------------------- applying
JOB = {"id": None, "status": "idle", "log": [], "result": None, "title": ""}
LOCK = threading.Lock()


def log(msg=""):
    for line in str(msg).splitlines() or [""]:
        JOB["log"].append(line)


def rollback():
    log("Restoring every file to the last commit ...")
    git("checkout", "--", ".")
    for line in git("status", "--porcelain").splitlines():
        if line.startswith("??"):
            p = os.path.join(ROOT, line[3:].strip().strip('"'))
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    sh([PY, os.path.join(SCRIPTS, "build_all.py")], check=False, env=BUILD_ENV)
    log("Restored. Nothing was changed.")


def build_and_check():
    log("Rebuilding the data layer and validating it (about half a minute) ...")
    if os.environ.get("MANAGER_TEST_FAIL_BUILD") == "1":          # used only by manager/tests
        raise Problem("The build did not pass:\n(test) forced failure")
    r = sh([PY, os.path.join(SCRIPTS, "build_all.py")], check=False, env=BUILD_ENV)
    if r.returncode != 0 or "all checks passed" not in r.stdout:
        raise Problem("The build did not pass:\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-20:]))
    for line in r.stdout.splitlines():
        if line.startswith(("WARN", "parquet web layer", "evidence rows")):
            log("  " + line)
    r = sh([PY, os.path.join(SCRIPTS, "audit_evidence.py"), ROOT], check=False)
    if r.returncode != 0:
        raise Problem("The evidence audit failed:\n" + (r.stdout + r.stderr)[-1500:])
    log("  all checks passed")


def commit(message):
    git("add", "-A")
    bad = [f for f in git("diff", "--cached", "--name-only").splitlines()
           if re.search(r"\.(pdf|xlsx|numbers|sqlite|parquet)$", f, re.I) or f.startswith("build/")]
    if bad:
        git("reset", "-q")
        raise Problem(f"files that must never be committed were staged: {bad}")
    if not git("diff", "--cached", "--name-only").strip():
        raise Problem("the operation changed nothing")
    git("commit", "-q", "-m", message)
    log("Saved on this Mac as a local commit: " + git("log", "-1", "--format=%h %s").strip())


def transaction(mutate, message):
    try:
        mutate()
        build_and_check()
        commit(message)
    except Exception:
        rollback()
        raise


def apply_change_table(p):
    analyte, file = p["analyte"], p["file"]
    path = table_path(analyte, file)
    rows, _ = read_table_file(path)
    hdr, data = rows[0], [list(r) for r in rows[1:]]
    edits, deletes, adds = p.get("edits") or [], set(p.get("deletes") or []), p.get("adds") or []
    for e in edits:
        i = int(e["row"])
        if i in deletes:
            continue
        data[i - 1][hdr.index(e["column"])] = e["value"]
    kept = [r for i, r in enumerate(data, 1) if i not in deletes]
    kept += [[(a.get(c) or "") for c in hdr] for a in adds]

    def mutate():
        write_table_file(path, [hdr] + kept)
        if read_table_file(path)[0] != [hdr] + kept:      # what is on disk must be exactly the plan
            raise Problem("the rewritten table does not match the plan; nothing was saved")

    n_e = len({(int(e["row"]), e["column"]) for e in edits if int(e["row"]) not in deletes})
    parts = [f"{n_e} value{'s' if n_e != 1 else ''} changed" if n_e else "", f"{len(deletes)} row{'s' if len(deletes) != 1 else ''} deleted" if deletes else "",
             f"{len(adds)} row{'s' if len(adds) != 1 else ''} added" if adds else ""]
    transaction(mutate, f"Edit evidence: {analyte} / {file}\n\n" + ", ".join(x for x in parts if x) + " (through the manager app)")


def apply_delete_table(p):
    analyte, file = p["analyte"], p["file"]
    path = table_path(analyte, file)
    n = len(read_table_file(path)[0]) - 1
    new_text, expected, _, _ = registry_without_table(analyte, file)

    def mutate():
        open(IA.REGISTRY, "w", encoding="utf-8").write(new_text)
        N = IA.load_registry()
        if N.TABLE_MAP != expected["TABLE_MAP"] or N.OVERRIDES != expected["OVERRIDES"] or N.CANON != expected["CANON"]:
            raise Problem("the edit of scripts/registry.py did not produce the expected registry")
        os.remove(path)

    transaction(mutate, f"Delete evidence table: {analyte} / {file} ({n} rows)\n\n(through the manager app)")


def apply_reject_rows(p):
    analyte, file = p["analyte"], p["file"]
    path = table_path(analyte, file)
    rows, _ = read_table_file(path)
    hdr = rows[0]
    drop = {int(r["row"]) for r in p["rejects"]}
    today = datetime.date.today().isoformat()
    entries = [{"source_file": f"{analyte}/database/{file}", "original_row": int(r["row"]), "criteria": r["criteria"],
                "reason": r["reason"], "decided": r.get("decided", "manual"), "date": today,
                "values": dict(zip(hdr, rows[int(r["row"])]))} for r in p["rejects"]]
    kept = [hdr] + [r for i, r in enumerate(rows[1:], 1) if i not in drop]

    def mutate():
        write_table_file(path, kept)
        if read_table_file(path)[0] != kept:
            raise Problem("the rewritten table does not match the plan; nothing was saved")
        SC.archive_rejected(ROOT, hdr, entries)

    by = collections.Counter(c for r in p["rejects"] for c in r["criteria"].split("; "))
    transaction(mutate, f"Reject {len(drop)} rows by the inclusion criteria: {analyte} / {file}\n\n"
                + "\n".join(f"{n} x criterion {c}" for c, n in by.most_common()) + "\n\nArchived in meta/rejected_rows.csv (through the manager app)")


def apply_edit_analyte(p):
    folder = p["analyte"]
    text, expected, R = registry_edit_analyte(folder, p["changes"])

    def mutate():
        open(IA.REGISTRY, "w", encoding="utf-8").write(text)
        N = IA.load_registry()
        if N.ANALYTES != expected or N.CANON != R.CANON or N.TABLE_MAP != R.TABLE_MAP or N.OVERRIDES != R.OVERRIDES:
            raise Problem("the edit of scripts/registry.py did not produce the expected registry")

    transaction(mutate, f"Change analyte {folder}: " + ", ".join(f"{k} -> {v}" for k, v in p["changes"].items()) + "\n\n(through the manager app)")


def apply_delete_analyte(p):
    folder = p["analyte"]
    text, R = registry_without_analyte(folder)

    def mutate():
        open(IA.REGISTRY, "w", encoding="utf-8").write(text)
        N = IA.load_registry()
        drop = lambda d: {k: v for k, v in d.items() if k != folder}
        if N.ANALYTES != drop(R.ANALYTES) or N.CANON != drop(R.CANON) or N.TABLE_MAP != drop(R.TABLE_MAP) or N.OVERRIDES != drop(R.OVERRIDES):
            raise Problem("the edit of scripts/registry.py did not produce the expected registry")
        shutil.rmtree(os.path.join(ROOT, folder))

    transaction(mutate, f"Delete analyte: {folder}\n\n(through the manager app)")


def apply_rename_cause(p):
    folder, key = p["analyte"], p["key"]
    R0 = IA.load_registry()
    name = str(p.get("name", "")).strip()
    concept = IA.slug(str(p.get("concept", R0.CANON[folder][key][1])))
    text, expected, R = registry_rename_cause(folder, key, name, concept)

    def mutate():
        open(IA.REGISTRY, "w", encoding="utf-8").write(text)
        N = IA.load_registry()
        if N.CANON != expected or N.ANALYTES != R.ANALYTES or N.TABLE_MAP != R.TABLE_MAP or N.OVERRIDES != R.OVERRIDES:
            raise Problem("the edit of scripts/registry.py did not produce the expected registry")

    transaction(mutate, f"Rename interference cause {folder}/{key}: {name} [{concept}]\n\n(through the manager app)")


def apply_publish(_):
    log("Sending to GitHub ...")
    r = sh(["git", "push"], check=False, timeout=180)
    if r.returncode != 0:
        raise Problem("The push failed; your changes are still saved on this Mac.\n" + r.stderr.strip()[-600:])
    fetch_origin(force=True)
    owner, repo = remote()
    log(f"GitHub is updated: https://github.com/{owner}/{repo}")
    if not shutil.which("gh"):
        log("The website updates in a few minutes (the gh command is not installed, so progress cannot be shown here).")
        return
    log("GitHub is rebuilding the data and the website; this takes a few minutes ...")
    sha = git("rev-parse", "HEAD").strip()
    deadline = time.time() + 900
    seen = False
    while time.time() < deadline:
        time.sleep(10)
        r = sh(["gh", "run", "list", "--workflow", "pages.yml", "--limit", "5", "--json", "status,conclusion,headSha,url"], check=False, timeout=30)
        try:
            run = next((x for x in json.loads(r.stdout or "[]") if x["headSha"] == sha), None)
        except ValueError:
            run = None
        if not run:
            if not seen and time.time() > deadline - 840:
                log("No website build was started for this change (it touched nothing the website shows).")
                return
            continue
        if not seen:
            log("  website build: " + run["url"])
            seen = True
        if run["status"] == "completed":
            if run["conclusion"] == "success":
                log(f"The website is updated: https://{owner}.github.io/{repo}/")
            else:
                raise Problem("GitHub could not rebuild the website (" + str(run["conclusion"]) + "). The website still shows the previous version. Details: " + run["url"])
            return
    log("Still building after 15 minutes; check the Actions page on GitHub.")


def apply_discard(_):
    git("reset", "--hard", "origin/main")
    log("Local changes discarded. Rebuilding ...")
    sh([PY, os.path.join(SCRIPTS, "build_all.py")], check=False, env=BUILD_ENV)
    log("This Mac now matches GitHub.")


def apply_pull(_):
    r = sh(["git", "pull", "--ff-only", "-q"], check=False, timeout=180)
    if r.returncode != 0:
        raise Problem("Could not update from GitHub:\n" + r.stderr.strip()[-600:])
    log("Updated. Rebuilding ...")
    sh([PY, os.path.join(SCRIPTS, "build_all.py")], check=False, env=BUILD_ENV)
    log("This Mac now has everything that is on GitHub.")


def apply_import(p):
    r = subprocess.Popen([PY, "-u", os.path.join(SCRIPTS, "import_archive.py"), *importer_args(p), "--commit-only"],
                         cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=BUILD_ENV)
    for line in r.stdout:
        if not line.startswith("warning:"):
            log(line.rstrip())
    if r.wait() != 0:
        raise Problem("The import did not complete. Nothing was changed.")


APPLY = {"import": apply_import, "change_table": apply_change_table, "delete_table": apply_delete_table,
         "reject_rows": apply_reject_rows, "edit_analyte": apply_edit_analyte, "delete_analyte": apply_delete_analyte,
         "rename_cause": apply_rename_cause,
         "publish": apply_publish, "discard": apply_discard, "pull": apply_pull}


def start(token):
    p = PLANS.pop(token, None)
    if not p:
        raise Problem("This plan is no longer valid (the data changed or another plan was made). Review the operation again.")
    if not LOCK.acquire(blocking=False):
        raise Problem("Another operation is still running.")
    JOB.update(id=secrets.token_hex(6), status="running", log=[], result=None, title=p["op"])

    def work():
        try:
            APPLY[p["op"]](p["params"])
            JOB["status"] = "done"
        except Problem as e:
            log("")
            log(str(e))
            JOB["status"] = "failed"
        except Exception as e:                       # never leave the interface waiting
            log("")
            log(f"Unexpected error: {e!r}")
            JOB["status"] = "failed"
        finally:
            _fetch["at"] = 0
            LOCK.release()

    threading.Thread(target=work, daemon=True).start()
    return {"job": JOB["id"]}


# ----------------------------------------------------------------------------- http
TOKEN = secrets.token_urlsafe(18)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorised(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost") and secrets.compare_digest(self.headers.get("X-Token") or "", TOKEN)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if not url.path.startswith("/api/"):
            name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            path = os.path.normpath(os.path.join(UI, name))
            if not path.startswith(UI) or not os.path.isfile(path):
                return self.send(404, b"not found", "text/plain")
            return self.send(200, open(path, "rb").read(), TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))
        if not self.authorised():
            return self.send(403, {"error": "not authorised"})
        try:
            if url.path == "/api/state":
                return self.send(200, state(fresh=q.get("fresh") == "1"))
            if url.path == "/api/database":
                return self.send(200, database())
            if url.path == "/api/table":
                return self.send(200, table(q["analyte"], q["file"]))
            if url.path == "/api/archive":
                return self.send(200, archive_runs())
            if url.path == "/api/run":
                return self.send(200, run_proposal(q["path"]))
            if url.path == "/api/screen_all":
                return self.send(200, screening_all())
            if url.path == "/api/job":
                return self.send(200, {k: JOB[k] for k in ("id", "status", "log", "title")})
            return self.send(404, {"error": "unknown address"})
        except (Problem, IA.Stop) as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:
            return self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self.authorised():
            return self.send(403, {"error": "not authorised"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/plan":
                return self.send(200, plan(body))
            if self.path == "/api/screen":
                return self.send(200, screening(body))
            if self.path == "/api/apply":
                return self.send(200, start(body.get("token", "")))
            if self.path == "/api/config":
                cfg = load_config()
                path = os.path.expanduser(str(body.get("archive", "")).strip())
                if not os.path.isdir(path):
                    raise Problem(f"folder not found: {path}")
                cfg["archive"] = path
                save_config(cfg)
                return self.send(200, cfg)
            return self.send(404, {"error": "unknown address"})
        except (Problem, IA.Stop) as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:
            return self.send(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        sys.exit("pyarrow is not installed for this Python. Start the manager with the project's environment: .venv/bin/python manager/server.py")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"URL http://127.0.0.1:{server.server_address[1]}/#t={TOKEN}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
