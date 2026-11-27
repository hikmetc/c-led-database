#!/usr/bin/env python3
"""Import one extraction run of the literature archive into the C-LED database.

    python3 scripts/import_archive.py <path> [options]

<path> is one of
  - a run folder of the archive    .../carboxyhemoglobin__methylene-blue/2026-11-05_1058__APS-1
  - a topic folder                 .../carboxyhemoglobin__methylene-blue      (its latest run is used)
  - an extraction table            .../04_extraction/<run id>_extraction_table_v2.csv

What it does, in order
  1. picks the extraction table (the highest _vN version unless a file is named) and checks it
     against the 29-column header of the database
  2. works out the analyte and the interferent; anything it cannot work out it asks for
     (or takes from the options below) - it never invents a name, a concept or an APS
  3. copies the table to <analyte>/database/ and registers it in scripts/registry.py
  4. removes rows that carry no evidence (scripts/prune_unevidenced_rows.py), rebuilds everything
     (scripts/build_all.py) and runs the audit; if anything fails, every change is undone
  5. shows a summary and asks before it commits and pushes; the push makes GitHub rebuild the
     data and the website, so the new evidence appears there a few minutes later

Only the extraction CSV is copied. PDFs, Markdown conversions, Excel files and screening tables
stay in the archive. The archive itself is only read, never changed.

Options
  --table FILE            use this extraction table instead of the latest version in the run
  --analyte-folder NAME   import into this analyte folder (e.g. potassium_serum)
  --interferent-key KEY   canonical interferent key (e.g. methylene_blue)
  --interferent-name TXT  canonical interferent name, for a new interferent
  --concept NAME          cross-analyte concept, for a new interferent (e.g. hemolysis)
  for a new analyte: --prefix --component --system --kind-of-property --unit --synonyms [--aps]
  --dry-run               show what would happen; change nothing
  --yes                   do not ask before committing and pushing
  --no-push               import and rebuild locally; do not commit or push
  --commit-only           import, rebuild and commit locally; do not push
  --allow-duplicate-cause do not stop when the interferent already has another table
  --screen                apply the automatic rejection criteria (scripts/screening.py): rows that
                          fail are left out and archived, with the reason, in meta/rejected_rows.csv
  --reject-json FILE      leave out exactly the rows listed in FILE (written by the manager app)
"""
import argparse, csv, datetime, difflib, glob, importlib.util, io, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
REGISTRY = os.path.join(HERE, "registry.py")
csv.field_size_limit(10 ** 7)


class Stop(Exception):
    """A problem the user has to resolve. Nothing has been changed when it is raised early."""


def say(msg=""):
    print(msg, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, **kw)


def git(*args):
    r = run(["git", *args], capture_output=True)
    if r.returncode != 0:
        raise Stop(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def changed_files():
    """Files that really differ from the last commit. Line-ending-only differences of
    generated files (the build writes CRLF, git stores LF) do not count."""
    # `git diff` compares normalised content, so it does not list line-ending-only differences,
    # and unlike `git add` it leaves the index alone
    names = git("diff", "--name-only", "HEAD").splitlines()
    names += git("ls-files", "--others", "--exclude-standard").splitlines()
    return [n for n in names if n.strip()]


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def slug(s):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (s or "").lower())).strip("_")


def pystr(s):
    return json.dumps(s, ensure_ascii=False)


def load_registry(path=REGISTRY):
    spec = importlib.util.spec_from_file_location("cled_registry_tmp", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ask(prompt, default=None, interactive=True):
    if not interactive:
        raise Stop(f"needs an answer but is not running in a terminal: {prompt}")
    suffix = f" [{default}]" if default not in (None, "") else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


# ----------------------------------------------------------------------------- the source run
def version_of(name):
    m = re.search(r"_extraction_table(?:_v(\d+))?\.csv$", name)
    return None if not m else int(m.group(1) or 1)


def resolve_source(path, table=None):
    """Return (run folder or None, extraction table path, parameters dict)."""
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        raise Stop(f"path not found: {path}")
    run_dir = None
    if os.path.isfile(path):
        table = table or path
        parent = os.path.dirname(path)
        run_dir = os.path.dirname(parent) if os.path.basename(parent) == "04_extraction" else None
    elif os.path.isdir(os.path.join(path, "04_extraction")):
        run_dir = path
    else:
        runs = sorted(d for d in glob.glob(os.path.join(path, "*")) if os.path.isdir(os.path.join(d, "04_extraction")))
        if not runs:
            raise Stop(f"{path} is neither a run folder (with 04_extraction/) nor a topic folder holding one")
        run_dir = runs[-1]
        if len(runs) > 1:
            say(f"note: {len(runs)} runs in this topic; using the latest, {os.path.basename(run_dir)}")
    if table is None:
        tables = [f for f in glob.glob(os.path.join(run_dir, "04_extraction", "*.csv")) if version_of(os.path.basename(f))]
        if not tables:
            raise Stop(f"no *_extraction_table*.csv in {os.path.join(run_dir, '04_extraction')}")
        tables.sort(key=lambda f: version_of(os.path.basename(f)))
        table = tables[-1]
        if len(tables) > 1:
            say(f"note: {len(tables)} versions of the extraction table; using the latest, {os.path.basename(table)}")
    table = os.path.abspath(os.path.expanduser(table))
    if not os.path.isfile(table):
        raise Stop(f"extraction table not found: {table}")
    params = {}
    if run_dir and os.path.exists(os.path.join(run_dir, "00_parameters.json")):
        params = json.load(open(os.path.join(run_dir, "00_parameters.json"), encoding="utf-8"))
    return run_dir, table, params


def read_table(path, header):
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise Stop(f"{os.path.basename(path)} is not valid UTF-8: {e}")
    rows = list(csv.reader(text.splitlines(keepends=True)))
    if not rows:
        raise Stop(f"{os.path.basename(path)} is empty")
    if rows[0] != header:
        missing = [c for c in header if c not in rows[0]]
        extra = [c for c in rows[0] if c not in header]
        raise Stop(f"{os.path.basename(path)} does not have the 29-column header of the database.\n"
                   f"  columns missing: {missing or 'none'}\n  unexpected columns: {extra or 'none'}\n"
                   "  (same columns in a different order also count as different)")
    data = [r for r in rows[1:] if any((v or "").strip() for v in r)]
    if not data:
        raise Stop(f"{os.path.basename(path)} has a header but no rows")
    return text, len(data)


# ----------------------------------------------------------------------------- registry edits
def _block_end(text, start):
    """Index of the line that closes a `"folder": {` block opened at `start`."""
    m = re.compile(r"^\s{0,2}\},\s*$", re.M).search(text, start)
    if not m:
        raise Stop("could not find the end of a block in scripts/registry.py; edit it by hand (see STRUCTURE.md)")
    return m.start()


def add_to_block(text, dict_name, folder, line):
    d = re.compile(rf"^{dict_name}\s*=\s*\{{\s*$", re.M).search(text)
    if not d:
        raise Stop(f"{dict_name} not found in scripts/registry.py")
    h = re.compile(rf'^"{re.escape(folder)}":\s*\{{\s*$', re.M).search(text, d.end())
    if not h:
        raise Stop(f'"{folder}" not found in {dict_name} of scripts/registry.py')
    end = _block_end(text, h.end())
    return text[:end] + line + "\n" + text[end:]


def add_block(text, dict_name, block):
    d = re.compile(rf"^{dict_name}\s*=\s*\{{\s*$", re.M).search(text)
    if not d:
        raise Stop(f"{dict_name} not found in scripts/registry.py")
    m = re.compile(r"^\}\s*$", re.M).search(text, d.end())
    if not m:
        raise Stop(f"could not find the end of {dict_name} in scripts/registry.py")
    return text[:m.start()] + block + "\n" + text[m.start():]


# ----------------------------------------------------------------------------- decisions
def find_analyte(R, texts):
    wanted = {norm(t) for t in texts if t}
    hits = []
    for folder, a in R.ANALYTES.items():
        names = {folder, folder.split("_")[0], a["prefix"], a["component"]}
        names.update(s for s in a.get("synonyms", "").split(";"))
        if wanted & {norm(n) for n in names if n.strip()}:
            hits.append(folder)
    return hits


def decide_analyte(R, args, params, table_name, interactive):
    if args.analyte_folder:
        if args.analyte_folder in R.ANALYTES:
            return args.analyte_folder, None
        folder = args.analyte_folder
    else:
        scope = params.get("scope", {})
        topic = params.get("folder", {}).get("topic", "").split("__")[0]
        texts = [params.get("analyte"), topic, table_name.split("_")[0], (scope.get("analyte_original") or "").split("(")[0]]
        hits = find_analyte(R, texts)
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            raise Stop(f"the analyte matches several analytes of the database: {hits}. Name one with --analyte-folder.")
        say(f"\nThe analyte \"{params.get('analyte') or table_name.split('_')[0]}\" is not in the database yet.")
        say("Existing analytes: " + ", ".join(sorted(R.ANALYTES)))
        folder = ask("Folder of an existing analyte, or a name for the new one (lower case, component_system, e.g. magnesium_serum)", interactive=interactive)
        if folder in R.ANALYTES:
            return folder, None
    if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)+", folder):
        raise Stop(f"\"{folder}\" is not a valid analyte folder name: use lower case, underscore separated, component then specimen")
    aps = args.aps if args.aps is not None else params.get("aps", {}).get("percent")
    need = lambda val, prompt, default=None: val if val else ask(prompt, default, interactive)
    new = dict(
        prefix=need(args.prefix, "Short prefix for ids, unique, lower case (e.g. mg)"),
        component=need(args.component, "Component name, IFCC/IUPAC style (e.g. Magnesium)", params.get("analyte")),
        system=need(args.system, "System / specimen (e.g. Serum)"),
        kind_of_property=need(args.kind_of_property, "Kind of property (e.g. Substance concentration)"),
        unit=need(args.unit, "Unit (e.g. mmol/L)"),
        aps_percent=float(aps if aps is not None else ask("APS in percent (e.g. 1.8)", interactive=interactive)),
        aps_note="",
        synonyms=args.synonyms if args.synonyms is not None else ask("Synonyms, separated by ';' (may be empty)", "", interactive),
    )
    if not re.fullmatch(r"[a-z][a-z0-9]*", new["prefix"]):
        raise Stop(f"prefix \"{new['prefix']}\" must be lower-case letters and digits, starting with a letter")
    if new["prefix"] in {a["prefix"] for a in R.ANALYTES.values()}:
        raise Stop(f"prefix \"{new['prefix']}\" is already used by another analyte")
    for k in ("component", "system", "kind_of_property", "unit"):
        if not new[k].strip():
            raise Stop(f"a new analyte needs a {k.replace('_', ' ')}")
    return folder, new


def decide_interferent(R, args, params, folder, dest_name, interactive, is_new_analyte):
    """Return (key, (name, concept) or None when the key already exists)."""
    canon = {} if is_new_analyte else R.CANON[folder]
    if not is_new_analyte and dest_name in R.TABLE_MAP[folder]:
        return R.TABLE_MAP[folder][dest_name], None        # an update of a table that is registered
    scope = params.get("scope", {})
    label = params.get("interferent") or scope.get("interferent_original") or ""
    key = args.interferent_key or slug(label)
    if key and key in canon:
        return key, None
    if not args.interferent_key and canon:
        names = {k: v[0] for k, v in canon.items()}
        close = difflib.get_close_matches(key, list(names), n=5, cutoff=0.5)
        close += [k for k, n in names.items() if k not in close and key and (norm(label) in norm(n) or norm(k) in norm(label))]
        if close and interactive:
            say(f"\nInterferent of this run: \"{label}\". Similar causes already defined for this analyte:")
            for i, k in enumerate(close, 1):
                say(f"  {i}. {k}  -  {names[k]}")
            pick = ask("Number to file the table under that cause, or Enter for a new cause", "", interactive)
            if pick.isdigit() and 1 <= int(pick) <= len(close):
                return close[int(pick) - 1], None
    if not key:
        key = slug(ask("Key for the new interferent (lower case, e.g. methylene_blue)", interactive=interactive))
    if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", key):
        raise Stop(f"\"{key}\" is not a valid interferent key")
    concepts = sorted({c for a in R.CANON.values() for _, c in a.values()})
    name = args.interferent_name or ask("Canonical name of the interferent, in English", scope.get("interferent_original") or label.capitalize(), interactive)
    if args.concept:
        concept = args.concept
    else:
        say("\nConcepts in use (reuse one where the cause is the same; that is what links analytes):")
        say("  " + ", ".join(concepts))
        guess = (difflib.get_close_matches(key, concepts, n=1, cutoff=0.6) or [None])[0]
        concept = slug(ask("Concept", guess, interactive))
    if not name.strip() or not concept:
        raise Stop("a new interferent needs a canonical name and a concept")
    if concept not in concepts:
        say(f"note: \"{concept}\" is a new concept; it will get its own row in the website's matrix")
    return key, (name.strip(), concept)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--table")
    ap.add_argument("--analyte-folder")
    ap.add_argument("--interferent-key")
    ap.add_argument("--interferent-name")
    ap.add_argument("--concept")
    for f in ("prefix", "component", "system", "kind-of-property", "unit", "synonyms"):
        ap.add_argument("--" + f)
    ap.add_argument("--aps", type=float)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--commit-only", action="store_true",
                    help="commit locally without asking, but do not push (used by the manager app)")
    ap.add_argument("--allow-duplicate-cause", action="store_true")
    ap.add_argument("--screen", action="store_true")
    ap.add_argument("--reject-json")
    args = ap.parse_args()
    interactive = sys.stdin.isatty()

    try:
        import pyarrow  # noqa: F401  (the build needs it for the Parquet web layer)
    except ImportError:
        raise Stop("pyarrow is not installed for this Python. Use the project's environment:\n"
                   "  .venv/bin/python scripts/import_archive.py <path>\n"
                   "or run: pip install -r requirements.txt")

    header = [r["column"] for r in csv.DictReader(open(os.path.join(ROOT, "meta", "data_dictionary.csv"), encoding="utf-8"))]
    run_dir, table, params = resolve_source(args.path, args.table)
    text, n_rows = read_table(table, header)
    src_name = os.path.basename(table)

    # One table per run: versions (_v2, _v3) replace each other under one stable file name, so
    # the row ids of a run do not change when a newer version of its table is imported.
    dest_name = re.sub(r"_extraction_table_v\d+\.csv$", "_extraction_table.csv", src_name)
    if " " in dest_name or any(ord(c) > 127 for c in dest_name) or re.search(r'[<>:"\\|?*]', dest_name):
        raise Stop(f"\"{dest_name}\" is not a portable file name (spaces, non-ASCII or reserved characters); rename the table first")

    R = load_registry()
    folder, new_analyte = decide_analyte(R, args, params, dest_name, interactive)
    key, new_cause = decide_interferent(R, args, params, folder, dest_name, interactive, bool(new_analyte))
    prefix = new_analyte["prefix"] if new_analyte else R.ANALYTES[folder]["prefix"]

    # ---- inclusion screening: rows that fail a rejection criterion do not enter the database
    rejected = []                      # [{"row", "criteria", "reason", "decided"}], row = 1-based data row of the source table
    if args.reject_json:
        rejected = json.load(open(args.reject_json, encoding="utf-8"))
    elif args.screen:
        sys.path.insert(0, HERE)
        import screening
        src_rows = list(csv.DictReader(io.StringIO(text, newline="")))
        info = dict(new_analyte or R.ANALYTES[folder], folder=folder)
        for res in screening.screen(src_rows, info, ROOT, exclude_file=dest_name):
            if res["reject"]:
                rejected.append({"row": res["row"], "criteria": "; ".join(f"{e['no']} {e['code']}" for e in res["reject"]),
                                 "reason": " | ".join(e["detail"] for e in res["reject"]), "decided": "automatic"})
    rejected_entries = []
    if rejected:
        all_rows = list(csv.reader(io.StringIO(text, newline="")))
        drop = {int(r["row"]) for r in rejected}
        if any(not (1 <= i < len(all_rows)) for i in drop):
            raise Stop("the list of rejected rows does not match the table; screen it again")
        today = datetime.date.today().isoformat()
        for r in rejected:
            rejected_entries.append({"source_file": f"{folder}/database/{dest_name}", "original_row": int(r["row"]),
                                     "criteria": r.get("criteria", ""), "reason": r.get("reason", ""),
                                     "decided": r.get("decided", "manual"), "date": today,
                                     "values": dict(zip(all_rows[0], all_rows[int(r["row"])]))})
        kept = [all_rows[0]] + [row for i, row in enumerate(all_rows[1:], 1) if i not in drop]
        buf = io.StringIO(newline="")
        csv.writer(buf).writerows(kept)
        text, n_source, n_rows = buf.getvalue(), n_rows, len(kept) - 1
        if n_rows == 0:
            raise Stop(f"every one of the {n_source} rows is rejected by the screening, so there is nothing to import")

    dest = os.path.join(ROOT, folder, "database", dest_name)
    updating = os.path.exists(dest)
    old_rows = None
    if updating:
        old_text = open(dest, encoding="utf-8-sig").read()
        if old_text.replace("\r\n", "\n") == text.replace("\r\n", "\n"):
            say(f"Nothing to do: {folder}/database/{dest_name} already holds exactly this table.")
            return 0
        old_rows = sum(1 for r in list(csv.reader(old_text.splitlines(keepends=True)))[1:] if any((v or "").strip() for v in r))

    same_cause = [] if new_analyte else [t for t, k in R.TABLE_MAP[folder].items() if k == key and t != dest_name]
    run_aps = params.get("aps", {}).get("percent")
    db_aps = new_analyte["aps_percent"] if new_analyte else R.ANALYTES[folder]["aps_percent"]

    say("\n" + "=" * 72)
    say("Import plan")
    say("=" * 72)
    say(f"  source table     : {table}")
    say(f"  rows             : {n_rows}" + (f"   (replaces {old_rows} rows of the current version)" if updating else ""))
    if rejected_entries:
        by = {}
        for e in rejected_entries:
            for c in e["criteria"].split("; "):
                by[c] = by.get(c, 0) + 1
        say(f"  rejected         : {len(rejected_entries)} of {n_rows + len(rejected_entries)} source rows do not pass the screening and are left out"
            " (archived with their reasons in meta/rejected_rows.csv)")
        for c, n in sorted(by.items(), key=lambda x: -x[1]):
            say(f"      {n:4d}  criterion {c}")
        if not args.reject_json:
            for e in rejected_entries[:30]:
                say(f"      row {e['original_row']:4d}: {e['reason'][:200]}")
            if len(rejected_entries) > 30:
                say(f"      ... and {len(rejected_entries) - 30} more")
    say(f"  analyte          : {folder}" + ("   NEW ANALYTE" if new_analyte else f"   ({R.ANALYTES[folder]['component']})"))
    if new_analyte:
        for k, v in new_analyte.items():
            say(f"      {k:17}: {v}")
    say(f"  interferent      : {prefix}.{key}" + (f"   NEW: \"{new_cause[0]}\", concept \"{new_cause[1]}\"" if new_cause else f"   ({R.CANON[folder][key][0]})"))
    say(f"  destination      : {folder}/database/{dest_name}" + ("   (UPDATE of an existing table)" if updating else ""))
    if run_aps is not None and abs(float(run_aps) - float(db_aps)) > 1e-9:
        say(f"  WARNING: this run was extracted against an APS of {run_aps} %, the database uses {db_aps} % for this analyte.\n"
            "           Verdict text inside the table refers to the run's APS; numeric verdicts are recomputed.")
    if updating:
        say("  WARNING: replacing a table can shift row numbers, so permalinks to its rows may point to other rows.")
        if old_rows is not None and n_rows < old_rows:
            say(f"  WARNING: the new version has FEWER rows ({n_rows}) than the table it replaces ({old_rows}). "
                f"{old_rows - n_rows} rows would disappear. Make sure this version is a complete table and not an addendum.")
    if same_cause:
        say(f"  WARNING: this interferent already has {len(same_cause)} other table(s): {', '.join(same_cause)}\n"
            "           If they hold the same studies, the evidence would be counted twice.")
        if not args.allow_duplicate_cause:
            if not interactive or ask("Import as an additional table for the same cause? (y/N)", "N", interactive).lower() not in ("y", "yes"):
                raise Stop("stopped: resolve the overlap first, or pass --allow-duplicate-cause if the tables hold different studies")
    if args.dry_run:
        say("\n--dry-run: nothing was changed.")
        return 0

    # ---- from here on files change; a clean tree makes a failed import fully reversible
    if changed_files():
        raise Stop("the repository has uncommitted changes. Commit or discard them first, so that a failed import can be undone cleanly.")
    before = json.load(open(os.path.join(ROOT, "build", "stats.json"), encoding="utf-8")) if os.path.exists(os.path.join(ROOT, "build", "stats.json")) else {}

    def undo(reason):
        say(f"\n{reason}\nUndoing every change of this import ...")
        git("checkout", "--", ".")
        for line in git("status", "--porcelain").splitlines():
            if line.startswith("??"):
                p = os.path.join(ROOT, line[3:].strip().strip('"'))
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        run([sys.executable, os.path.join(HERE, "build_all.py")], env=build_env, capture_output=True)
        say("The repository is back to its last commit.")

    build_env = dict(os.environ, CLED_ROOT=ROOT, CLED_REQUIRE_PARQUET="1", CLED_DISTRIBUTION="1")
    try:
        reg = open(REGISTRY, encoding="utf-8").read()
        if new_analyte:
            a = new_analyte
            reg = add_block(reg, "ANALYTES",
                            f' {pystr(folder)}: dict(\n    prefix={pystr(a["prefix"])}, component={pystr(a["component"])}, system={pystr(a["system"])},\n'
                            f'    kind_of_property={pystr(a["kind_of_property"])}, unit={pystr(a["unit"])},\n'
                            f'    aps_percent={a["aps_percent"]!r}, aps_note={pystr(a["aps_note"])},\n    synonyms={pystr(a["synonyms"])}),')
            reg = add_block(reg, "CANON", f'{pystr(folder)}: {{\n {pystr(key)}: ({pystr(new_cause[0])}, {pystr(new_cause[1])}),\n}},')
            reg = add_block(reg, "TABLE_MAP", f'{pystr(folder)}: {{\n {pystr(dest_name)}: {pystr(key)},\n}},')
            reg = add_block(reg, "OVERRIDES", f'{pystr(folder)}: {{}},')
        else:
            if new_cause:
                reg = add_to_block(reg, "CANON", folder, f' {pystr(key)}: ({pystr(new_cause[0])}, {pystr(new_cause[1])}),')
            if dest_name not in R.TABLE_MAP[folder]:
                reg = add_to_block(reg, "TABLE_MAP", folder, f' {pystr(dest_name)}: {pystr(key)},')
        if reg != open(REGISTRY, encoding="utf-8").read():
            open(REGISTRY, "w", encoding="utf-8").write(reg)
            # the edited registry must be exactly the old one plus the planned entries
            N = load_registry()
            exp_canon = {f: dict(v) for f, v in R.CANON.items()}
            exp_map = {f: dict(v) for f, v in R.TABLE_MAP.items()}
            exp_an = {f: dict(v) for f, v in R.ANALYTES.items()}
            if new_analyte:
                exp_an[folder] = new_analyte
            if new_cause:
                exp_canon.setdefault(folder, {})[key] = new_cause
            exp_map.setdefault(folder, {})[dest_name] = key
            if N.CANON != exp_canon or N.TABLE_MAP != exp_map or N.ANALYTES != exp_an:
                raise Stop("the edit of scripts/registry.py did not produce the expected registry")

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as fh:      # UTF-8 without BOM
            fh.write(text)
        if rejected_entries:
            sys.path.insert(0, HERE)
            import screening
            screening.archive_rejected(ROOT, header, rejected_entries)

        say("\nRemoving rows that carry no evidence ...")
        r = run([sys.executable, os.path.join(HERE, "prune_unevidenced_rows.py"), ROOT], capture_output=True)
        say("  " + (r.stdout.strip().splitlines() or ["(nothing reported)"])[-1])
        if r.returncode != 0:
            raise Stop("prune_unevidenced_rows.py failed:\n" + r.stderr)
        if not os.path.exists(dest):
            raise Stop("no row of this table carries any evidence (all 11 data fields are empty in every row), so there is nothing to import")

        say("Rebuilding the data layer and validating it (about half a minute) ...")
        r = run([sys.executable, os.path.join(HERE, "build_all.py")], env=build_env, capture_output=True)
        if r.returncode != 0 or "all checks passed" not in r.stdout:
            raise Stop("the build did not pass:\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-25:]))
        for line in r.stdout.splitlines():
            if line.startswith(("WARN", "parquet web layer", "evidence rows")):
                say("  " + line)
        r = run([sys.executable, os.path.join(HERE, "audit_evidence.py"), ROOT], capture_output=True)
        if r.returncode != 0:
            raise Stop("the evidence audit failed:\n" + (r.stdout + r.stderr)[-2000:])
        for line in r.stdout.splitlines()[:6]:
            say("  " + line.strip())
    except Stop as e:
        undo(f"IMPORT FAILED: {e}")
        return 1
    except Exception as e:                                   # never leave a half-finished import
        undo(f"IMPORT FAILED with an unexpected error: {e!r}")
        raise

    after = json.load(open(os.path.join(ROOT, "build", "stats.json"), encoding="utf-8"))
    imported = sum(1 for r in csv.reader(open(dest, encoding="utf-8", newline="")) if any((v or "").strip() for v in r)) - 1
    say("\n" + "=" * 72)
    say("Imported locally")
    say("=" * 72)
    say(f"  {folder}/database/{dest_name}: {imported} rows" + (f" ({n_rows - imported} without evidence were removed)" if imported != n_rows else ""))
    say(f"  evidence rows in the database: {before.get('generated_rows', '?')} -> {after['generated_rows']}")
    say(f"  analytes: {len(before.get('by_analyte', {})) or '?'} -> {len(after['by_analyte'])}")
    say("\nChanged files:")
    git("add", "-A")
    say("  " + git("diff", "--cached", "--stat").strip().replace("\n", "\n  "))
    bad = [f for f in git("diff", "--cached", "--name-only").splitlines()
           if re.search(r"\.(pdf|xlsx|numbers|sqlite|parquet)$", f, re.I) or f.startswith("build/")]
    if bad:
        git("reset", "-q")
        undo(f"IMPORT FAILED: files that must never be committed were staged: {bad}")
        return 1

    label = new_cause[0] if new_cause else R.CANON[folder][key][0]
    verb = "Update" if updating else "Add"
    msg = f"{verb} evidence: {folder} / {label} ({imported} rows)\n\nSource run: {params.get('run_id') or os.path.splitext(src_name)[0]}\nSource table: {src_name}"
    if new_analyte:
        msg += f"\nNew analyte: {folder} (prefix {prefix}, APS {new_analyte['aps_percent']} %)"
    if args.commit_only:
        git("commit", "-q", "-m", msg)
        say("\nCommitted locally. Not pushed: GitHub and the website are unchanged until you publish.")
        return 0
    if args.no_push:
        git("reset", "-q")
        say("\n--no-push: the changes are in the working tree, not committed. Review them with `git status`.")
        return 0
    if not args.yes:
        if not interactive or ask("\nCommit and push to GitHub? The repository is public; the website updates a few minutes later. (y/N)", "N", interactive).lower() not in ("y", "yes"):
            git("reset", "-q")
            say("Not pushed. The changes are in the working tree, not committed.\n"
                "  to publish later : git add -A && git commit -m \"...\" && git push\n"
                "  to discard them  : git checkout -- . && git clean -fd")
            return 0

    git("commit", "-q", "-m", msg)
    say("Committed. Pushing ...")
    r = run(["git", "push"], capture_output=True)
    if r.returncode != 0:
        say("The push failed; the commit is kept locally. Run `git push` once the problem is solved.\n" + r.stderr.strip())
        return 1
    origin = git("remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", origin)
    if m:
        owner, repo = m.groups()
        say(f"\nPushed. GitHub is now rebuilding the data and the website:\n  https://github.com/{owner}/{repo}/actions")
        say(f"When the run is green (a few minutes), the evidence is live at:\n  https://{owner}.github.io/{repo}/interferent/{prefix}.{key}/")
        if shutil.which("gh") and interactive and not args.yes:
            if ask("Wait here until the website is updated? (y/N)", "N", interactive).lower() in ("y", "yes"):
                run(["gh", "run", "watch", "--exit-status"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as e:
        print(f"\nSTOPPED: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
