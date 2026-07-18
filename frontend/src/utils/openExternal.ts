/**
 * Open a URL in the user's real system browser.
 *
 * Desktop: navigate the window to the URL. main.rs's on_navigation hook
 * intercepts navigation to allowlisted external hosts — including Plaid
 * Hosted Link's domain, secure.plaid.com — opens them in the system browser,
 * and cancels the in-app navigation, so the Ledger window itself never
 * actually moves. Bank OAuth needs a real browser; Plaid production also
 * won't accept this app's http://127.0.0.1 webview as an OAuth redirect
 * target, which is why the flow must leave the webview at all.
 *
 * Web/dev: open a new tab (no on_navigation hook exists outside the app).
 *
 * Desktop vs. web is detected via GET /health's `desktop` flag (mirrors the
 * LEDGER_DESKTOP env var) rather than Tauri's `window.__TAURI__` JS bridge —
 * that bridge is unreliable for this window, since it loads an external
 * http://127.0.0.1 URL (WebviewUrl::External) rather than Tauri's own
 * bundled/asset-protocol content, and Tauri's IPC layer does not treat
 * External-URL windows as a trusted local origin.
 */
let cachedIsDesktop: boolean | null = null

async function isDesktop(): Promise<boolean> {
  if (cachedIsDesktop !== null) return cachedIsDesktop
  try {
    const res = await fetch('/health')
    const data = await res.json()
    cachedIsDesktop = Boolean(data.desktop)
  } catch {
    cachedIsDesktop = false
  }
  return cachedIsDesktop
}

export async function openExternal(url: string): Promise<void> {
  if (await isDesktop()) {
    window.location.href = url
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}
