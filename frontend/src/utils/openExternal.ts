/**
 * Open a URL in the user's real system browser.
 *
 * Desktop (Tauri): call the `open_external` command so the OS default browser
 * handles it — required for Plaid Hosted Link, since bank OAuth pages must run
 * in a real browser, not the app webview.
 * Web/dev: open a new tab.
 *
 * `withGlobalTauri` exposes `window.__TAURI__` only inside the packaged app, so
 * its presence doubles as the desktop-vs-web check.
 */
export async function openExternal(url: string): Promise<void> {
  const tauri = (
    window as unknown as {
      __TAURI__?: {
        core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
      }
    }
  ).__TAURI__

  if (tauri?.core?.invoke) {
    await tauri.core.invoke('open_external', { url })
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}
