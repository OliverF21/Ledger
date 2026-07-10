#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f appicon.png ]]; then
  echo "appicon.png missing — add a 1024×1024 source (e.g. IconKitchen ios/AppIcon~ios-marketing.png)" >&2
  exit 1
fi

npx tauri icon appicon.png

# Drop AppX / iOS / Android extras — bundle.icon only needs the five below.
rm -rf src-tauri/icons/android src-tauri/icons/ios
rm -f src-tauri/icons/64x64.png src-tauri/icons/icon.png src-tauri/icons/StoreLogo.png
rm -f src-tauri/icons/Square*.png

echo "Icons updated in src-tauri/icons/"
