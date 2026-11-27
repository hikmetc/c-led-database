#!/bin/bash
# Build the macOS app for the database manager.
#   manager/build_app.sh [destination folder]        (default: ~/Applications)
# Needs the Xcode command line tools (swiftc) and the project's Python environment (.venv).
# The app remembers where this repository is; run this again if the folder is moved.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
DEST="${1:-$HOME/Applications}"
APP="$DEST/EFLM Database Manager.app"
PY="$REPO/.venv/bin/python"

[ -x "$PY" ] || { echo "Python environment not found: $PY
Create it first:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
"$PY" -c "import pyarrow" 2>/dev/null || { echo "pyarrow is missing in .venv; run: .venv/bin/pip install -r requirements.txt"; exit 1; }
command -v swiftc >/dev/null || { echo "swiftc not found; install the Xcode command line tools: xcode-select --install"; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -o "$APP/Contents/MacOS/Manager" "$HERE/macos/Main.swift" -framework Cocoa -framework WebKit

# where git and gh live on this Mac (an app started from the Finder has a minimal PATH)
TOOLS=""
for t in git gh; do d="$(dirname "$(command -v $t 2>/dev/null || echo /usr/bin/$t)")"; TOOLS="$TOOLS:$d"; done
"$PY" - "$REPO" "$PY" "${TOOLS#:}" "$APP/Contents/Resources/config.json" <<'PYEOF'
import json, sys
json.dump({"repo": sys.argv[1], "python": sys.argv[2], "path": sys.argv[3]}, open(sys.argv[4], "w"), indent=2)
PYEOF

if [ -f "$HERE/macos/icon.png" ]; then
  SET="$(mktemp -d)/icon.iconset"; mkdir -p "$SET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$HERE/macos/icon.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$HERE/macos/icon.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$SET" -o "$APP/Contents/Resources/icon.icns"
fi

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>EFLM Database Manager</string>
  <key>CFBundleDisplayName</key><string>EFLM Database Manager</string>
  <key>CFBundleIdentifier</key><string>local.laboratory-error-database.manager</string>
  <key>CFBundleExecutable</key><string>Manager</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
codesign --force -s - "$APP" >/dev/null 2>&1 || true
echo "Built: $APP"
