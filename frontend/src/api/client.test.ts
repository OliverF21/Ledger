import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './client'

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
})
