// Thin fetch wrapper that attaches the session token (Authorization: Bearer)
// issued by /api/auth/login|register. Use this instead of the global fetch()
// for every /api request.

const TOKEN_KEY = 'ledger_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // Ask caches not to reuse this response. The desktop webview is WebKit,
  // which will replay a GET for the same URL when the response omitted
  // Cache-Control (see the /api no-store middleware). `cache: 'no-store'`
  // is what actually skips an entry already sitting in that cache; the
  // response header only stops the next one from being stored.
  if (!headers.has('Cache-Control')) headers.set('Cache-Control', 'no-cache')

  const res = await fetch(path, { ...init, headers, cache: 'no-store' })

  // A 401 on a normal API call means the session is gone/expired. Drop the
  // stale token and let the app shell send the user back to the login screen.
  // Auth endpoints (login/register) handle their own 401s inline.
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    clearToken()
    window.dispatchEvent(new Event('ledger:unauthorized'))
  }

  return res
}

/** Same as apiFetch, but give up after `ms` so a hung backend cannot pin
 *  the boot spinner forever. */
export async function apiFetchTimeout(
  path: string,
  init: RequestInit = {},
  ms = 8_000,
): Promise<Response> {
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), ms)
  try {
    return await apiFetch(path, { ...init, signal: ctrl.signal })
  } finally {
    window.clearTimeout(timer)
  }
}
