import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  apiFetch,
  clearToken,
  getToken,
  isAccountRemembered,
  rememberedUsername,
  resumeLocalSession,
  setAccountRemembered,
  setToken,
} from './client'

function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (key) => (data.has(key) ? data.get(key)! : null),
    key: (index) => Array.from(data.keys())[index] ?? null,
    removeItem: (key) => { data.delete(key) },
    setItem: (key, value) => { data.set(key, String(value)) },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiFetch', () => {
  it('bypasses the HTTP cache on every API call', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    })
    const fetchMock = vi.fn(async (...args: [RequestInfo | URL, RequestInit?]) => {
      return new Response(JSON.stringify({ received: args.length }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/investments/risk/optimize?lookback_days=1095')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/investments/risk/optimize?lookback_days=1095')
    expect(init?.cache).toBe('no-store')
    expect(new Headers(init?.headers).get('Cache-Control')).toBe('no-cache')
  })

  it('renews a no-account session and retries once after a 401', async () => {
    const { local } = installRememberStorage()
    setToken('expired', true)
    let accountCalls = 0
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/auth/local-session') {
        return new Response(JSON.stringify({ token: 'fresh' }), { status: 200 })
      }
      accountCalls += 1
      const auth = new Headers(init?.headers).get('Authorization')
      if (accountCalls === 1) {
        expect(auth).toBe('Bearer expired')
        return new Response('no', { status: 401 })
      }
      expect(auth).toBe('Bearer fresh')
      return new Response(JSON.stringify({ ok: true }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('window', { dispatchEvent: vi.fn() })

    const res = await apiFetch('/api/plaid/accounts')
    expect(res.status).toBe(200)
    expect(getToken()).toBe('fresh')
    expect(local.getItem('ledger_token')).toBe('fresh')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('drops the token when a 401 cannot be renewed', async () => {
    installRememberStorage()
    setToken('expired', true)
    const dispatch = vi.fn()
    vi.stubGlobal('window', { dispatchEvent: dispatch })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/auth/local-session') return new Response('{}', { status: 404 })
      return new Response('no', { status: 401 })
    }))

    const res = await apiFetch('/api/plaid/accounts')
    expect(res.status).toBe(401)
    expect(getToken()).toBeNull()
    expect(dispatch).toHaveBeenCalled()
  })

  it('resumeLocalSession ignores a response with no token', async () => {
    installRememberStorage()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: true }), { status: 200 })))
    expect(await resumeLocalSession()).toBe(false)
    expect(getToken()).toBeNull()
  })
})

function installRememberStorage() {
  const local = memoryStorage()
  const session = memoryStorage()
  vi.stubGlobal('localStorage', local)
  vi.stubGlobal('sessionStorage', session)
  return { local, session }
}

describe('remember account', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function install() {
    const local = memoryStorage()
    const session = memoryStorage()
    vi.stubGlobal('localStorage', local)
    vi.stubGlobal('sessionStorage', session)
    return { local, session }
  }

  it('defaults to remembering when the preference has never been set', () => {
    install()
    expect(isAccountRemembered()).toBe(true)
    expect(rememberedUsername()).toBe('')
  })

  it('keeps the session and username when remembering is on', () => {
    const { local, session } = install()
    setToken('tok', true, 'ada')
    expect(getToken()).toBe('tok')
    expect(local.getItem('ledger_token')).toBe('tok')
    expect(session.getItem('ledger_token')).toBeNull()
    expect(local.getItem('ledger_remembered_username')).toBe('ada')
    expect(rememberedUsername()).toBe('ada')
    expect(isAccountRemembered()).toBe(true)
  })

  it('keeps the session only until the app closes when remembering is off', () => {
    const { local, session } = install()
    setToken('tok', false, 'ada')
    expect(getToken()).toBe('tok')
    expect(local.getItem('ledger_token')).toBeNull()
    expect(session.getItem('ledger_token')).toBe('tok')
    expect(local.getItem('ledger_remembered_username')).toBeNull()
    expect(rememberedUsername()).toBe('')
    expect(isAccountRemembered()).toBe(false)
    session.removeItem('ledger_token')
    expect(getToken()).toBeNull()
  })

  it('moves an existing session when the setting changes', () => {
    const { local, session } = install()
    setToken('tok', true, 'ada')
    setAccountRemembered(false)
    expect(local.getItem('ledger_token')).toBeNull()
    expect(session.getItem('ledger_token')).toBe('tok')
    expect(rememberedUsername()).toBe('')
    expect(isAccountRemembered()).toBe(false)
    setAccountRemembered(true, 'ada')
    expect(local.getItem('ledger_token')).toBe('tok')
    expect(session.getItem('ledger_token')).toBeNull()
    expect(rememberedUsername()).toBe('ada')
    expect(isAccountRemembered()).toBe(true)
  })

  it('sign-out keeps a remembered username and drops a session-only token', () => {
    const { local, session } = install()
    setToken('tok', true, 'ada')
    clearToken()
    expect(getToken()).toBeNull()
    expect(local.getItem('ledger_remembered_username')).toBe('ada')
    expect(isAccountRemembered()).toBe(true)

    setToken('tok-2', false, 'ada')
    clearToken()
    expect(session.getItem('ledger_token')).toBeNull()
    expect(local.getItem('ledger_token')).toBeNull()
    expect(rememberedUsername()).toBe('')
  })
})
