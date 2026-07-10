#!/usr/bin/env bash
# Build a plain .dmg from the built Ledger.app using hdiutil.
#
# Tauri's own DMG step (bundle_dmg.sh) drives Finder via AppleScript to lay out
# the window, which fails in headless/CI/no-GUI sessions. This produces an
# equivalent drag-to-Applications .dmg without that dependency.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
APP="$ROOT/desktop/src-tauri/target/release/bundle/macos/Ledger.app"
VERSION=$(/usr/bin/plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist" 2>/dev/null || echo "0.1.0")
ARCH=$(uname -m)  # arm64 / x86_64
OUT="$ROOT/desktop/Ledger_${VERSION}_${ARCH}.dmg"

[ -d "$APP" ] || { echo "error: $APP not found — run the Tauri build first" >&2; exit 1; }

STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

rm -f "$OUT"
hdiutil create -volname "Ledger" -srcfolder "$STAGING" -ov -format UDZO "$OUT" >/dev/null
echo "built $OUT"
