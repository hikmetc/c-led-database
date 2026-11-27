#!/bin/bash
# End-to-end test of the manager. It never touches this repository, the real archive or your
# settings: everything happens in a throwaway clone with its own origin, archive and config.
#   manager/tests/run.sh
# Needs the project's .venv and the site's node_modules (for Playwright). PW_CHANNEL=chrome uses
# an installed Chrome instead of Playwright's own Chromium.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/.venv/bin/python"
WORK="$(mktemp -d)"
SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT

git clone -q --bare "$REPO" "$WORK/origin.git"
git clone -q "$WORK/origin.git" "$WORK/repo"
cd "$WORK/repo"
git config user.name "Manager Test"; git config user.email "test@example.invalid"
# test the working tree as it is now, committed or not
rsync -a --delete "$REPO/manager/" manager/ && rsync -a "$REPO/scripts/" scripts/ --exclude __pycache__
git add -A >/dev/null 2>&1; git commit -q -m "state under test" >/dev/null 2>&1 || true; git push -q >/dev/null 2>&1 || true
CLED_REQUIRE_PARQUET=1 CLED_DISTRIBUTION=1 "$PY" scripts/build_all.py >/dev/null

"$PY" "$REPO/manager/tests/make_archive.py" "$WORK/repo" "$WORK/archive"
mkdir -p "$WORK/config" && echo "{\"archive\": \"$WORK/archive\"}" > "$WORK/config/config.json"

start_server() {   # $1 = extra environment assignment or empty
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null || true
  env MANAGER_CONFIG_DIR="$WORK/config" ${1:-X=1} "$PY" -u manager/server.py > "$WORK/server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 50); do grep -q "^URL " "$WORK/server.log" && break; sleep 0.2; done
  sed -n 's/^URL //p' "$WORK/server.log"
}
URL="$(start_server "")"
URL_FAIL_FILE="$WORK/url_fail"
export MANAGER_TEST_URL="$URL" MANAGER_TEST_REPO="$WORK/repo" MANAGER_TEST_ORIGIN="$WORK/origin.git"
cd "$REPO/site" && node "$REPO/manager/tests/e2e.mjs" main
# second pass: the build is forced to fail, and every change must be undone
cd "$WORK/repo"; URL="$(start_server "MANAGER_TEST_FAIL_BUILD=1")"
export MANAGER_TEST_URL="$URL"
cd "$REPO/site" && node "$REPO/manager/tests/e2e.mjs" rollback
echo "manager tests: all passed"
