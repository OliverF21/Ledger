// Prevent an extra console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

/// Fixed loopback port — must match the OAuth redirect URI registered in Plaid.
const PORT: u16 = 17384;
const HOST: &str = "127.0.0.1";

/// Hosts (and their subdomains) that should open in the user's real browser
/// instead of navigating the app window. Everything NOT listed here stays
/// in-webview — required for Plaid Link's cdn.plaid.com iframe and OAuth
/// institution redirects (Chase, Robinhood) to work at all.
const EXTERNAL_HOSTS: &[&str] = &["ko-fi.com", "dashboard.plaid.com"];

/// Holds the spawned backend process so we can kill it on exit.
struct Backend(Mutex<Option<Child>>);

/// Poll the backend's /health until it returns 200, or give up after `timeout`.
fn wait_for_health(timeout: Duration) -> bool {
    let addr = format!("{HOST}:{PORT}");
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Ok(mut stream) = TcpStream::connect(&addr) {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
            let req = format!("GET /health HTTP/1.0\r\nHost: {HOST}\r\n\r\n");
            if stream.write_all(req.as_bytes()).is_ok() {
                let mut buf = String::new();
                let _ = stream.read_to_string(&mut buf);
                if buf.contains("200") {
                    return true;
                }
            }
        }
        sleep(Duration::from_millis(300));
    }
    false
}

/// Resolve the bundled backend executable inside the app's Resources dir.
fn backend_exe(app: &tauri::App) -> Result<std::path::PathBuf, String> {
    let res = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;
    let bin = if cfg!(windows) { "ledger-backend.exe" } else { "ledger-backend" };
    // tauri.conf.json maps ../../backend/dist/ledger-backend → Resources/backend,
    // so the onedir contents (the exe + _internal) land directly under backend/.
    let candidates = [
        res.join("backend").join(bin),
        res.join("backend").join("ledger-backend").join(bin),
    ];
    for c in candidates.iter() {
        if c.exists() {
            return Ok(c.clone());
        }
    }
    Err(format!("backend executable not found under {}", res.display()))
}

/// Open a URL in the user's default system browser. Invoked from the frontend
/// for Plaid Hosted Link: bank OAuth must run in a real browser (Plaid hosts the
/// redirect on its own HTTPS domain), not inside this app's http://127.0.0.1
/// webview — which is exactly why the old in-webview OAuth flow could not work.
#[tauri::command]
fn open_external(url: String) -> Result<(), String> {
    open::that(url).map_err(|e| e.to_string())
}

/// Best-effort background update check. No-op unless the build was configured
/// with a release updater overlay (endpoints + pubkey) — otherwise `updater()`
/// errors and we simply skip. Never blocks or crashes the app.
fn spawn_update_check(app: &tauri::App) {
    use tauri_plugin_updater::UpdaterExt;
    let handle = app.handle().clone();
    tauri::async_runtime::spawn(async move {
        let updater = match handle.updater() {
            Ok(u) => u,
            Err(_) => return, // updater not configured in this build
        };
        match updater.check().await {
            Ok(Some(update)) => {
                eprintln!("[ledger] update available: {}", update.version);
                if let Err(e) = update
                    .download_and_install(|_chunk, _total| {}, || {})
                    .await
                {
                    eprintln!("[ledger] update install failed: {e}");
                } else {
                    handle.restart();
                }
            }
            Ok(None) => {}
            Err(e) => eprintln!("[ledger] update check skipped: {e}"),
        }
    });
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![open_external])
        .setup(|app| {
            let exe = backend_exe(app).map_err(|e| {
                eprintln!("[ledger] {e}");
                std::io::Error::new(std::io::ErrorKind::NotFound, e)
            })?;

            // Send the backend's output to a log file for troubleshooting.
            let log = std::fs::File::create(std::env::temp_dir().join("ledger-backend.log")).ok();
            let (out, err) = match &log {
                Some(f) => (
                    std::process::Stdio::from(f.try_clone().unwrap()),
                    std::process::Stdio::from(f.try_clone().unwrap()),
                ),
                None => (std::process::Stdio::inherit(), std::process::Stdio::inherit()),
            };
            let child = Command::new(&exe)
                .env("LEDGER_DESKTOP", "1")
                .env("PORT", PORT.to_string())
                .env("LEDGER_BIND_HOST", HOST)
                .stdout(out)
                .stderr(err)
                .spawn()
                .map_err(|e| {
                    eprintln!("[ledger] failed to spawn backend ({}): {e}", exe.display());
                    e
                })?;
            app.manage(Backend(Mutex::new(Some(child))));

            // First launch of an unsigned build validates every bundled dylib,
            // which can take ~30s cold — allow generous headroom so the window
            // reliably appears. Subsequent launches are fast (validation cached).
            if !wait_for_health(Duration::from_secs(120)) {
                eprintln!("[ledger] backend did not become healthy in time");
                return Err("backend health check timed out".into());
            }

            let url = format!("http://{HOST}:{PORT}/");
            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(url.parse().expect("valid url")),
            )
            .title("Ledger")
            .inner_size(1240.0, 840.0)
            .min_inner_size(900.0, 640.0)
            // Default to letting navigation happen in-webview: Plaid Link embeds
            // an iframe at cdn.plaid.com, and OAuth institutions (Chase,
            // Robinhood) do a full top-level navigation to the bank's own login
            // page and back — both must stay in-webview to work at all. Only an
            // explicit allowlist of "should leave the app" destinations gets
            // routed to the system browser instead.
            .on_navigation(|nav| {
                let host = nav.host_str().unwrap_or("");
                let leaves_app = EXTERNAL_HOSTS.iter().any(|h| host == *h || host.ends_with(&format!(".{h}")));
                if leaves_app {
                    let _ = open::that(nav.as_str());
                }
                !leaves_app
            })
            .build()?;

            spawn_update_check(app);

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Ledger")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<Backend>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}
