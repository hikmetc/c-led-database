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
import signal, subprocess, sys, threading, time, urllib.parse, urllib.request

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
                "versions": len(tables), "run_id": params.get("run_id"),
                "stages": {k: (v.get("status") if isinstance(v, dict) else None) for k, v in (params.get("stages") or {}).items()}}
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


# ----------------------------------------------------------------------------- research (literature pipeline)
# The research itself is done by Claude Code with the user's own pipeline skill: literature
# search, full-text download through Firefox, extraction into the archive. The manager only
# starts that session unattended, shows its progress, and can stop it. It never touches the
# database: a finished run appears under "New from archive" and is imported from there.
RESEARCH_DIR = os.path.join(CONFIG_DIR, "research")
RESEARCH_STATE = os.path.join(RESEARCH_DIR, "current.json")
SKILL = "anthropic-skills:laboratory-interference-pipeline"
# what the unattended session may use: files, the two search servers, and a short list of
# shell commands the skills need. No web access, no git, no deleting.
RESEARCH_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Skill", "Agent", "Task", "TodoWrite",
                  "mcp__pubmed-search__pubmed_search", "mcp__pubmed-search__pubmed_get_article",
                  "mcp__crossref-search__crossref_search", "mcp__crossref-search__crossref_get_work"] + [
                  f"Bash({c}:*)" for c in ("python3", "sleep", "ls", "cat", "head", "tail", "grep", "wc", "find", "mkdir",
                                           "cp", "date", "echo", "pdftotext", "pdftoppm", "pdfinfo")]


def claude_binary():
    """Claude Code that ships with the Claude desktop app (the newest version), or `claude` on PATH."""
    override = os.environ.get("MANAGER_CLAUDE")
    if override:
        return override if os.path.exists(override) else None
    found = glob.glob(os.path.expanduser("~/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"))
    def ver(p):
        return tuple(int(x) for x in re.findall(r"\d+", p.split("/claude-code/")[1].split("/")[0]))
    found.sort(key=ver)
    return found[-1] if found else None


def search_servers():
    """The PubMed and Crossref servers as they are defined for the Claude desktop app."""
    path = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    if os.environ.get("MANAGER_CLAUDE"):
        return {"pubmed-search": {}, "crossref-search": {}}          # tests use a stand-in for Claude
    try:
        servers = json.load(open(path, encoding="utf-8")).get("mcpServers", {})
    except (OSError, ValueError):
        servers = {}
    return {k: servers[k] for k in ("pubmed-search", "crossref-search") if k in servers}


MODELS_CACHE = os.path.join(CONFIG_DIR, "models.json")
MODEL_ID = re.compile(rb"claude-(?:fable|mythos|opus|sonnet|haiku)-\d+(?:-\d{1,2})?(?:-\d{8})?(?![\w-])")
FAMILIES = ["fable", "mythos", "opus", "sonnet", "haiku"]
MODEL_CHECK = {"running": False, "done": 0, "total": 0}


def _model_sort(mid):
    m = re.fullmatch(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-(\d{8}))?", mid)
    fam, major, minor, date = m.group(1), int(m.group(2)), int(m.group(3) or 0), m.group(4) or ""
    return (-major, -minor, FAMILIES.index(fam), date)


def _model_label(mid):
    m = re.fullmatch(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-(\d{8}))?", mid)
    fam, major, minor, date = m.group(1), m.group(2), m.group(3), m.group(4)
    label = f"{fam.capitalize()} {major}" + (f".{minor}" if minor else "")
    if date:
        label += f" (snapshot {date[:4]}-{date[4:6]}-{date[6:]})"
    return label


def known_models():
    """Every model the installed Claude Code names, newest first, with what is known about
    whether it works for this account. The list is read from the Claude Code program itself, so
    it follows the Claude desktop app's updates. Nothing here is a fixed list."""
    claude = claude_binary()
    try:
        cache = json.load(open(MODELS_CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if os.environ.get("MANAGER_CLAUDE"):                       # tests: a stand-in, with a short list
        ids = ["claude-test-9-1", "claude-test-9", "claude-bad-1"]
        cache = cache if cache.get("source") == "test" else {"source": "test", "ids": ids, "checked": {}}
    elif claude and cache.get("source") != claude:
        found = set()
        with open(claude, "rb") as fh:                         # the program lists the ids it knows
            tail = b""
            while True:
                chunk = fh.read(8 << 20)
                if not chunk:
                    break
                found.update(m.decode() for m in MODEL_ID.findall(tail + chunk))
                tail = chunk[-64:]
        ids = sorted(found, key=_model_sort)
        cache = {"source": claude, "ids": ids, "checked": cache.get("checked", {}) if cache.get("ids") == ids else {}}
        os.makedirs(CONFIG_DIR, exist_ok=True)
        json.dump(cache, open(MODELS_CACHE, "w", encoding="utf-8"))
    ids = cache.get("ids", [])
    checked = cache.get("checked", {})
    families = [f for f in FAMILIES if any(i.startswith(f"claude-{f}-") for i in ids)]
    version = ""
    if claude and "/claude-code/" in claude:
        version = claude.split("/claude-code/")[1].split("/")[0]
    return {
        "aliases": [{"id": f, "label": f"{f.capitalize()}, latest version", **checked.get(f, {})} for f in families],
        "models": [{"id": i, "label": _model_label(i) if re.match(r"claude-(fable|mythos|opus|sonnet|haiku)-", i) else i, **checked.get(i, {})} for i in ids],
        "claude_version": version, "checked_at": cache.get("checked_at"),
        "checking": dict(MODEL_CHECK),
    }


def check_models():
    """Ask each model for a one-word answer, to learn which ones this account can use."""
    if MODEL_CHECK["running"]:
        return
    info = known_models()
    todo = [m["id"] for m in info["aliases"] + info["models"]]
    claude = claude_binary()
    MODEL_CHECK.update(running=True, done=0, total=len(todo))
    results = {}
    lock = threading.Lock()

    def probe(mid):
        ok, why = False, ""
        try:
            r = subprocess.run([claude, "-p", "Reply with the single word OK", "--model", mid], cwd=CONFIG_DIR,
                               capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
            out = (r.stdout + r.stderr).strip()
            ok = r.returncode == 0 and "error" not in out.lower()[:200]
            if not ok:
                why = clip(re.sub(r"\s+", " ", out), 160)
        except subprocess.TimeoutExpired:
            why = "no answer within two minutes"
        except OSError as e:
            why = str(e)
        with lock:
            results[mid] = {"ok": ok, **({"why": why} if why else {})}
            MODEL_CHECK["done"] += 1

    def work():
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            pending = list(todo)
            threads = []
            while pending or threads:
                threads = [t for t in threads if t.is_alive()]
                while pending and len(threads) < 4:
                    t = threading.Thread(target=probe, args=(pending.pop(0),), daemon=True)
                    t.start()
                    threads.append(t)
                time.sleep(0.3)
            try:
                cache = json.load(open(MODELS_CACHE, encoding="utf-8"))
            except (OSError, ValueError):
                cache = {"source": "test" if os.environ.get("MANAGER_CLAUDE") else claude, "ids": [m["id"] for m in info["models"]]}
            cache["checked"] = results
            cache["checked_at"] = datetime.datetime.now().astimezone().isoformat(timespec="minutes")
            json.dump(cache, open(MODELS_CACHE, "w", encoding="utf-8"))
        finally:
            MODEL_CHECK["running"] = False

    threading.Thread(target=work, daemon=True).start()


def research_ready():
    cfg = load_config()
    ar = cfg["archive"]
    tool = os.path.join(ar, "_system", "tools", "literature_archive.py")
    ext = {}
    try:
        ext = json.load(open(os.path.join(ar, "_system", "extension_status.json"), encoding="utf-8"))
    except (OSError, ValueError):
        pass
    minutes = None
    try:
        last = datetime.datetime.fromisoformat(ext["last_poll"])
        minutes = round((datetime.datetime.now(last.tzinfo) - last).total_seconds() / 60, 1)
    except (KeyError, ValueError, TypeError):
        pass
    servers = search_servers()
    claude = claude_binary()
    return {"claude": claude, "pubmed": "pubmed-search" in servers, "crossref": "crossref-search" in servers,
            "archive_tool": os.path.exists(tool), "firefox_minutes_ago": minutes,
            "firefox_polling": minutes is not None and minutes <= 3,
            "converter_ready": bool(ext.get("converter", {}).get("ready")),
            "ok": bool(claude) and len(servers) == 2 and os.path.exists(tool)}


def research_prompt(p, archive):
    tool = os.path.join(archive, "_system", "tools", "literature_archive.py")
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    note = f"""
Environment note from the program that started this session (the EFLM Database Manager): you are
running unattended, directly on the user's Mac in Claude Code, not in a cloud container.
- The literature archive is {archive} and it is your working directory. It is already connected:
  skip Phase 0 step 1.
- Where the skill says device_bash, use the Bash tool. Run the archive tool as one plain command,
  without shell variables:  python3 "{tool}" --archive "{archive}" <command> ...
- Where the skill says to create a file under /mnt/user-data/outputs and commit it with
  device_commit_files, write it directly to the path that next-name returns inside the run folder.
  Where it says device_stage_files, read the files where they are.
- Only these shell commands are available: python3, sleep, ls, cat, head, tail, grep, wc, find,
  mkdir, cp, date, echo, pdftotext, pdftoppm, pdfinfo. There is no web access other than the
  PubMed and Crossref tools.
- Nobody is watching. Ask no questions. If something required is missing or a step cannot be
  done, write what happened into the run's 05_report summary, say it in your final message, and
  stop. Wait for downloads with sleep-based polling as the skill describes; do not use send_later.
- The current time is {now}.
- Pass the analyte and the interferent to init-run exactly as given below (they are the English
  names the user chose for the folder)."""
    if p.get("continue_run"):
        return f"/{SKILL}\ndevam et {p['continue_run']}\n{note}"
    scope = "".join(f"\n{k}: {p[k]}" for k in ("sample_type", "date_range", "platforms") if p.get(k))
    return (f"/{SKILL}\nuse this skill and prepare table for :\nanalyte: {p['analyte']}\ninterferent: {p['interferent']}\n"
            f"analytical performance specification: {p['aps']}{scope}\n{note}")


def research_state():
    try:
        st = json.load(open(RESEARCH_STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    alive = False
    if st.get("pid"):
        try:
            os.kill(st["pid"], 0)
            alive = True
        except OSError:
            alive = False
    st["running"] = alive and not st.get("stopped")
    return st


def research_view():
    """What the Research section shows: readiness, the current or last session, its progress."""
    out = {"ready": research_ready(), "session": None}
    st = research_state()
    if not st:
        return out
    lines, result = [], None
    try:
        for raw in open(st["log"], encoding="utf-8", errors="replace"):
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except ValueError:
                if not raw.startswith("[mcp-sdk]"):
                    lines.append(raw[:300])
                continue
            if ev.get("type") == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        lines.append(block["text"].strip())
                    elif block.get("type") == "tool_use":
                        inp = block.get("input", {})
                        detail = inp.get("command") or inp.get("query") or inp.get("file_path") or inp.get("skill") or inp.get("description") or ""
                        lines.append(f"\u2192 {block.get('name', 'tool')}: {clip(str(detail).replace(chr(10), ' '), 160)}")
            elif ev.get("type") == "result":
                result = {"ok": not ev.get("is_error"), "text": ev.get("result", ""), "turns": ev.get("num_turns"),
                          "cost_usd": ev.get("total_cost_usd"), "minutes": round((ev.get("duration_ms") or 0) / 60000, 1)}
    except OSError:
        pass
    # the run folder this session created, and what the archive tool says about it
    run = None
    cfg = load_config()
    started = st.get("started", "")
    newest = None
    for f in glob.glob(os.path.join(cfg["archive"], "*__*", "*", "00_parameters.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if st["params"].get("continue_run"):
            if d.get("run_id") == st["params"]["continue_run"]:
                newest = (d.get("created", ""), f, d)
        elif d.get("created", "") >= started[:16] and (newest is None or d.get("created", "") > newest[0]):
            newest = (d.get("created", ""), f, d)
    if newest:
        d = newest[2]
        stages = d.get("stages", {})
        run = {"run_id": d.get("run_id"), "folder": os.path.relpath(os.path.dirname(newest[1]), cfg["archive"]),
               "stages": {k: (v.get("status") if isinstance(v, dict) else None) for k, v in stages.items()},
               "shortlist": stages.get("screening", {}).get("shortlist"), "rows": stages.get("extraction", {}).get("rows")}
        tool = os.path.join(cfg["archive"], "_system", "tools", "literature_archive.py")
        try:
            r = subprocess.run([sys.executable, tool, "--archive", cfg["archive"], "status", "--run-dir", run["folder"]],
                               capture_output=True, text=True, timeout=20)
            info = json.loads(r.stdout)
            dl = info.get("download") or {}
            run.update(status=info.get("status"), downloaded=dl.get("downloaded"), total=dl.get("total"),
                       md_running=info.get("md_running"))
        except Exception:
            pass
    state = "running" if st["running"] else ("stopped" if st.get("stopped") else ("done" if result and result["ok"] else "failed" if result else "ended"))
    out["session"] = {"id": st["id"], "params": st["params"], "model": st.get("model") or "default", "started": started,
                      "state": state, "lines": lines[-400:], "result": result, "run": run}
    return out


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
    if op not in ("publish", "research", "research_stop") and IA.changed_files():
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

    if op == "research":
        ready = research_ready()
        st = research_state()
        if st and st["running"]:
            raise Problem("A research session is already running. Wait for it to finish or stop it first.")
        if not ready["claude"]:
            raise Problem("Claude Code was not found. It comes with the Claude desktop app; open that app once and try again.")
        if not (ready["pubmed"] and ready["crossref"]):
            raise Problem("The PubMed and Crossref search servers are not set up for the Claude desktop app (claude_desktop_config.json), so the literature cannot be searched.")
        if not ready["archive_tool"]:
            raise Problem("The archive tool (_system/tools/literature_archive.py) was not found in the archive folder. Check the folder in Settings.")
        model = str(body.get("model") or "").strip()
        if model and not re.fullmatch(r"[A-Za-z0-9._\-]+", model):
            raise Problem("The model name may only hold letters, digits, dots and hyphens.")
        if model:
            known = known_models()
            entry = next((m for m in known["aliases"] + known["models"] if m["id"] == model), None)
            if entry and entry.get("ok") is False:
                raise Problem(f"The model {model} did not answer for your account when it was checked"
                              + (f": {entry['why']}" if entry.get("why") else ".") + " Choose another model.")
        if body.get("continue_run"):
            lines = [f"Continue the archive run {body['continue_run']} with the pipeline skill, from its first unfinished phase."]
        else:
            for k in ("analyte", "interferent", "aps"):
                if not str(body.get(k) or "").strip():
                    raise Problem(f"Please give the {k if k != 'aps' else 'analytical performance specification'}.")
            lines = [f"Analyte: {body['analyte']}", f"Interferent: {body['interferent']}", f"Analytical performance specification: {body['aps']}"]
            lines += [f"{k.replace('_', ' ').capitalize()}: {body[k]}" for k in ("sample_type", "date_range", "platforms") if body.get(k)]
        lines += [f"Model: {model or 'the default of your Claude Code settings'}", "",
                  "Claude Code runs your pipeline skill unattended: it searches PubMed and Crossref, screens the records,",
                  "queues the full texts for Firefox (Full-Text Fetcher), waits for the download and the PDF-to-Markdown",
                  "conversion, checks each PDF is the right article, extracts the 29-column table and writes the report.",
                  "This can take from half an hour to several hours. You can close the manager; the session goes on."]
        warnings = ["This uses your own Claude account and counts against its usage, like a session you start by hand."]
        if not ready["firefox_polling"]:
            warnings.append("Firefox is not answering right now. Open Firefox and sign in with your university access before the download "
                            "phase starts; without it the full texts cannot be fetched and the run stops at the download.")
        if not ready["converter_ready"]:
            warnings.append("The PDF to Markdown converter is not ready; the extraction would read the PDFs directly.")
        warnings.append("The session works on its own with a fixed set of permissions: it may read and write files, use the PubMed and "
                        "Crossref tools, and run a short list of shell commands (python3, sleep, ls, cat, pdftotext and similar). "
                        "It has no other web access, cannot delete files with shell commands and cannot use git.")
        where = ["The literature archive: a new run folder is written (never an existing file).",
                 "This Mac's database, GitHub and the website: not touched. A finished run appears under \"New from archive\"."]
        return new_plan(op, body, "Start a literature search and extraction" if not body.get("continue_run") else "Continue a run", lines, warnings, where)

    if op == "research_stop":
        st = research_state()
        if not st or not st["running"]:
            raise Problem("No research session is running.")
        return new_plan(op, body, "Stop the running research session",
                        ["The Claude Code session is stopped now.", "Files it has already written stay in the archive; the run can be continued later."],
                        [], ["The literature archive: nothing is deleted.", "Downloads already queued for Firefox go on."])

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


def apply_research(p):
    cfg = load_config()
    archive = cfg["archive"]
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    sid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    mcp = os.path.join(RESEARCH_DIR, "mcp.json")
    json.dump({"mcpServers": search_servers()}, open(mcp, "w", encoding="utf-8"))
    log_path = os.path.join(RESEARCH_DIR, f"{sid}.jsonl")
    model = str(p.get("model") or "").strip()
    cmd = [claude_binary(), "-p", research_prompt(p, archive), "--output-format", "stream-json", "--verbose",
           "--mcp-config", mcp, "--add-dir", archive, "--allowed-tools", *RESEARCH_TOOLS]
    if model:
        cmd += ["--model", model]
    env = dict(os.environ)
    env["PATH"] = ":".join(["/opt/homebrew/bin", "/usr/local/bin", os.path.dirname(sys.executable), env.get("PATH", "")])
    proc = subprocess.Popen(cmd, cwd=archive, stdin=subprocess.DEVNULL, stdout=open(log_path, "w", encoding="utf-8"),
                            stderr=subprocess.STDOUT, env=env, start_new_session=True)     # outlives the manager
    json.dump({"id": sid, "pid": proc.pid, "params": {k: v for k, v in p.items() if k not in ("op",)}, "model": model,
               "started": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "log": log_path},
              open(RESEARCH_STATE, "w", encoding="utf-8"))
    log("The research session has started. Its progress is shown in the Research section.")
    log("You can close the manager; the session goes on and is shown again when you come back.")


def apply_research_stop(_):
    st = research_state()
    if st and st["running"]:
        try:
            os.killpg(st["pid"], signal.SIGTERM)
        except OSError:
            pass
        st["stopped"] = True
        json.dump({k: v for k, v in st.items() if k != "running"}, open(RESEARCH_STATE, "w", encoding="utf-8"))
    log("The session was stopped. What it wrote so far is in the archive.")


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
         "rename_cause": apply_rename_cause, "research": apply_research, "research_stop": apply_research_stop,
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
            if url.path == "/api/research":
                return self.send(200, research_view())
            if url.path == "/api/models":
                return self.send(200, known_models())
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
            if self.path == "/api/models/check":
                if not claude_binary():
                    raise Problem("Claude Code was not found.")
                check_models()
                return self.send(200, known_models())
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
