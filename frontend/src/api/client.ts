// Thin fetch wrapper that attaches the session token (Authorization: Bearer)
// issued by /api/auth/login|register. Use this instead of the global fetch()
// for every /api request.

const TOKEN_KEY = 'ledger_token'
const REMEMBER_KEY = 'ledger_remember_account'
const USERNAME_KEY = 'ledger_remembered_username'

function browserStore(name: 'localStorage' | 'sessionStorage'): Storage | null {
  const candidate = (globalThis as typeof globalThis & Record<string, unknown>)[name]
  if (
    !candidate
    || typeof (candidate as Storage).getItem !== 'function'
    || typeof (candidate as Storage).setItem !== 'function'
    || typeof (candidate as Storage).removeItem !== 'function'
  ) {
    return null
  }
  return candidate as Storage
}

function readKey(name: 'localStorage' | 'sessionStorage', key: string): string | null {
  return browserStore(name)?.getItem(key) ?? null
}

function writeKey(name: 'localStorage' | 'sessionStorage', key: string, value: string): boolean {
  const store = browserStore(name)
  if (!store) return false
  store.setItem(key, value)
  return true
}

function deleteKey(name: 'localStorage' | 'sessionStorage', key: string): void {
  browserStore(name)?.removeItem(key)
}

/** True unless "Remember this account" has been turned off. */
export function isAccountRemembered(): boolean {
  return readKey('localStorage', REMEMBER_KEY) !== '0'
}

/** Username to prefill on the login form. Empty when remembering is off. */
export function rememberedUsername(): string {
  if (!isAccountRemembered()) return ''
  return readKey('localStorage', USERNAME_KEY) ?? ''
}

export function getToken(): string | null {
  return readKey('localStorage', TOKEN_KEY) || readKey('sessionStorage', TOKEN_KEY)
}

/**
 * Store a session. Remembered sessions live in localStorage and survive
 * quitting the app. A session with remembering off lives in sessionStorage
 * and is dropped when the app closes. The saved username is kept only while
 * remembering is on.
 */
export function setToken(token: string, remember: boolean = isAccountRemembered(), username?: string): void {
  if (remember) {
    writeKey('localStorage', TOKEN_KEY, token)
    deleteKey('sessionStorage', TOKEN_KEY)
    writeKey('localStorage', REMEMBER_KEY, '1')
    const savedName = (username ?? '').trim()
    if (savedName) writeKey('localStorage', USERNAME_KEY, savedName)
    return
  }
  const stored = writeKey('sessionStorage', TOKEN_KEY, token)
  if (stored) deleteKey('localStorage', TOKEN_KEY)
  writeKey('localStorage', REMEMBER_KEY, '0')
  deleteKey('localStorage', USERNAME_KEY)
}

/**
 * Move the current session between durable storage and quit-to-sign-out
 * storage. Used by Settings while already signed in.
 */
export function setAccountRemembered(remember: boolean, username?: string | null): void {
  const token = getToken()
  if (!token) {
    writeKey('localStorage', REMEMBER_KEY, remember ? '1' : '0')
    if (!remember) deleteKey('localStorage', USERNAME_KEY)
    else if ((username ?? '').trim()) writeKey('localStorage', USERNAME_KEY, (username ?? '').trim())
    return
  }
  setToken(token, remember, username ?? undefined)
}

export function clearToken(): void {
  deleteKey('localStorage', TOKEN_KEY)
  deleteKey('sessionStorage', TOKEN_KEY)
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
