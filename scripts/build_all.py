#!/usr/bin/env python3
"""Rebuild the whole derived data layer from the source CSVs.

Usage:  python3 scripts/build_all.py
        CLED_ROOT=/path/to/repo python3 scripts/build_all.py

Reads : <root>/<analyte>/database/*.csv  (never modified)
Writes: <root>/meta/*   and  <root>/build/*
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLED_ROOT") or os.path.dirname(HERE)
env = dict(os.environ, CLED_ROOT=ROOT)
for step in ("build_vocab.py", "build_meta.py", "build_dataset.py", "mk_docs.py", "mk_structure_doc.py", "validate.py"):
    print("\n=== " + step + " ===", flush=True)
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, step)], env=env)
    if r.returncode != 0:
        sys.exit("build failed at " + step)
print("\nbuild complete ->", os.path.join(ROOT, "build"))
