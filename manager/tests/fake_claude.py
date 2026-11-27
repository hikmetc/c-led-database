#!/usr/bin/env python3
"""A stand-in for Claude Code in the manager tests. It behaves like an unattended pipeline
session: it prints stream-json events, creates a run folder with an extraction table in the
archive it is started in, and ends with a result event. It uses no network and no model."""
import csv, datetime, glob, json, os, sys, time

args = sys.argv[1:]
prompt = args[args.index("-p") + 1]
archive = os.getcwd()


def emit(event):
    print(json.dumps(event), flush=True)


def say(text):
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


def tool(name, **inp):
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})


say("Parametreler alındı. Çalışma klasörü açılıyor.")
tool("Bash", command="python3 literature_archive.py init-run")
if "interferent: slow" in prompt:
    say("Uzun bir tarama başlıyor.")
    time.sleep(600)                      # the test stops this session
    sys.exit(0)

now = datetime.datetime.now().astimezone()
run_id = f"potassium_research-stub_{now:%Y%m%d-%H%M}_APS0.4"
run_dir = os.path.join(archive, "potassium__research-stub", f"{now:%Y-%m-%d_%H%M}__APS-0.4")
os.makedirs(os.path.join(run_dir, "04_extraction"), exist_ok=True)
json.dump({"run_id": run_id, "analyte": "Potassium", "interferent": "research stub", "aps": {"text": "%0.4", "percent": 0.4},
           "created": now.isoformat(timespec="seconds"), "scope": {"interferent_original": "Research stub"},
           "folder": {"topic": "potassium__research-stub"},
           "stages": {"screening": {"status": "completed", "shortlist": 3}, "extraction": {"status": "completed", "rows": 3}}},
          open(os.path.join(run_dir, "00_parameters.json"), "w"))
tool("mcp__pubmed-search__pubmed_search", query="potassium AND research stub")
time.sleep(1.5)
src = sorted(glob.glob(os.path.join(archive, "potassium__testcause", "*", "04_extraction", "*.csv")))[0]
rows = list(csv.reader(open(src, encoding="utf-8", newline="")))
out = [rows[0]]
for i, r in enumerate(rows[1:4]):
    r = list(r)
    r[rows[0].index("Baseline analyte concentration")] += f" [research {i}]"
    out.append(r)
with open(os.path.join(run_dir, "04_extraction", f"{run_id}_extraction_table.csv"), "w", encoding="utf-8", newline="") as fh:
    csv.writer(fh).writerows(out)
say("Tablo hazır: 3 satır. Rapor yazıldı.")
emit({"type": "result", "subtype": "success", "is_error": False, "result": "Tamamlandı: 3 satır.", "num_turns": 4,
      "total_cost_usd": 0.0, "duration_ms": 2000})
