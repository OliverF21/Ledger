# Ledger Desktop

A native desktop wrapper (Tauri v2) around Ledger. On launch it spawns the
bundled FastAPI backend on `127.0.0.1:17384`, waits for it to be healthy, opens
a window to the local app, and stops the backend on quit. Your data lives in the
OS app-data directory, not inside the app bundle:

- **macOS**: `~/Library/Application Support/Ledger/`
- **Windows**: `%APPDATA%\Ledger\`

The backend is bundled with PyInstaller (no Python install needed) and serves the
built frontend — the window is a thin native shell around the local app.

## Lost your password and recovery code

The one-time recovery code shown at registration is always a valid password
reset path (Login screen → "Forgot password?"). If you set a recovery email
in Settings *and* the app operator configured `RESET_EMERGENCY_RESEND_API_KEY`,
you can also request a one-time code by email instead. If you've lost the
recovery code and have no recovery email configured, the only way back in is
to wipe local data and start fresh:

1. Quit Ledger
2. Delete the app-data directory:
   - **macOS**: `rm -rf ~/"Library/Application Support/Ledger"`
   - **Windows**: delete the `Ledger` folder inside `%APPDATA%`
3. Relaunch — you'll land on the first-run setup screen and need to re-link
   your accounts

This permanently deletes all local transactions, budgets, and settings —
there is no backup to fall back on unless you made one yourself.

## First launch (unsigned builds)

Ledger ships **unsigned** (open-source freeware). The OS will warn on first open:

- **macOS 15+**: the first double-click is blocked. Open it once via
  **System Settings → Privacy & Security → “Open Anyway”**. (The old
  right-click → Open shortcut no longer works for unsigned apps.)
- **macOS, downloaded via browser**: instead of the prompt above, you may see
  **“Ledger” is damaged and can’t be opened. You should move it to the Trash.**
  This is misleading — the app isn’t actually corrupted. Browsers quarantine
  downloaded files, and Gatekeeper refuses to run an unsigned, quarantined app
  with this message instead of the usual “unidentified developer” prompt. Fix
  it by stripping the quarantine flag, then open normally:
  ```bash
  xattr -cr /Applications/Ledger.app
  ```
- **Windows**: SmartScreen shows “Windows protected your PC”. Click
  **More info → Run anyway**.

After the first launch it opens normally.

**First launch is slow (~30s).** Because the build is unsigned, macOS validates
every bundled Python library the first time the backend starts, so the window can
take ~30 seconds to appear on the very first run. Subsequent launches are fast
(validation is cached). Developer ID signing + notarization eliminates this delay
(deferred — see the plan). The shell waits up to 120s for the backend before
giving up.

## Build from source

Prereqs: Node 18+, Rust (via [rustup](https://rustup.rs)), Python 3.11+.

### macOS

```bash
bash desktop/scripts/build-mac.sh
# → desktop/src-tauri/target/release/bundle/macos/Ledger.app
# → desktop/Ledger_<version>_<arch>.dmg
```

### Windows (run on Windows)

```powershell
powershell -ExecutionPolicy Bypass -File desktop\scripts\build-windows.ps1
# → desktop\src-tauri\target\release\bundle\nsis\Ledger_<version>_x64-setup.exe
```

Cross-building Windows from macOS is not supported (PyInstaller can't
cross-compile, and Tauri needs the Windows SDK). Use a Windows machine or the
**Desktop build** GitHub Actions workflow (`.github/workflows/desktop-build.yml`),
which builds both platforms on their native runners and uploads the artifacts.

## How it fits together

```
Ledger.app / Ledger installer
  └─ Tauri shell (src-tauri/src/main.rs)
       ├─ spawns Resources/backend/ledger-backend  (LEDGER_DESKTOP=1, PORT=17384, loopback)
       ├─ polls /health, then opens the window → http://127.0.0.1:17384/
       └─ kills the backend on exit
  └─ bundled backend (PyInstaller onedir; backend/ledger.spec)
       └─ FastAPI + uvicorn, serves frontend/dist, SQLite in the OS app-data dir
```

## Auto-update (via GitHub Releases)

Updates are driven from Rust on launch (`tauri-plugin-updater`; the webview loads
an external URL, so there's no JS bridge). On start the app fetches the update
manifest, and if a newer signed version exists it downloads, verifies it against
the embedded public key, installs, and restarts. **User data is never touched** —
it lives in the OS app-data dir, not the app bundle.

- The updater public key + endpoint live in `src-tauri/tauri.conf.json`
  (`plugins.updater`). The endpoint is the GitHub Releases manifest:
  `https://github.com/OliverF21/Ledger/releases/latest/download/latest.json`.
- `src-tauri/tauri.release.conf.json` adds only `createUpdaterArtifacts: true`, so
  ordinary local builds need no signing key; release builds produce the signed
  update bundle + `latest.json`.

### One-time setup (required before updates work)

Add two repo secrets (**Settings → Secrets and variables → Actions**):

| Secret | Value |
|--------|-------|
| `TAURI_SIGNING_PRIVATE_KEY` | contents of `~/.ledger/updater.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | the key's password (empty string if none) |

**Keep the private key safe** (`~/.ledger/updater.key`, never committed). Losing it
means already-installed apps can't verify future updates and everyone must reinstall.

### Shipping an update

1. Bump `version` in `desktop/src-tauri/tauri.conf.json` (and `package.json`).
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
3. The **Release** workflow builds + signs on macOS and Windows and creates a
   **draft** GitHub Release with the installers + `latest.json`.
4. Review and **publish** the draft release. Once published,
   `releases/latest/...` resolves to it and installed apps update on next launch.

> Unsigned (no Developer ID) auto-updates work, but macOS re-shows the Gatekeeper
> "Open Anyway" prompt after each update. Developer ID signing + notarization
> (deferred) makes updates seamless.

### Local release build (optional, for testing signing)

```bash
TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.ledger/updater.key)" \
TAURI_SIGNING_PRIVATE_KEY_PASSWORD="" \
bash desktop/scripts/build-mac.sh
```

## Icon

`appicon.png` is the 1024×1024 source (from [Icon Kitchen](https://icon.kitchen/) or similar).
Regenerate Tauri bundle icons with:

```bash
bash desktop/scripts/render-icons.sh
```

This writes only the five files referenced in `tauri.conf.json` (`32x32.png`,
`128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico`).
