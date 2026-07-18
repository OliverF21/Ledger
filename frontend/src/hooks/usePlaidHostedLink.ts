import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'
import { openExternal } from '../utils/openExternal'

/**
 * Drives a Plaid Hosted Link flow end to end:
 *   1. create a link token (Plaid returns a hosted_link_url)
 *   2. open that URL in the system browser
 *   3. poll GET /api/plaid/link_session until Plaid reports the session done
 *
 * The backend exchanges the public_token server-side on completion, so this
 * hook only reacts to the reported status. Works identically for a new link and
 * update-mode re-auth (pass an itemId to start()).
 */
export type HostedLinkStatus = 'idle' | 'starting' | 'waiting' | 'error'

interface UseHostedLinkOptions {
  onSuccess: () => void
  onError?: (message: string) => void
}

const POLL_INTERVAL_MS = 3000
// Give the user plenty of time to log in at their bank before we give up.
const POLL_TIMEOUT_MS = 10 * 60 * 1000

export function usePlaidHostedLink({ onSuccess, onError }: UseHostedLinkOptions) {
  const [status, setStatus] = useState<HostedLinkStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  const timerRef = useRef<number | null>(null)
  const deadlineRef = useRef(0)
  const hostedUrlRef = useRef<string | null>(null)
  const onSuccessRef = useRef(onSuccess)
  const onErrorRef = useRef(onError)
  onSuccessRef.current = onSuccess
  onErrorRef.current = onError

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const fail = useCallback(
    (message: string) => {
      stopPolling()
      setStatus('error')
      setError(message)
      onErrorRef.current?.(message)
    },
    [stopPolling],
  )

  const poll = useCallback(
    async (linkToken: string) => {
      try {
        const res = await apiFetch(
          `/api/plaid/link_session?link_token=${encodeURIComponent(linkToken)}`,
        )
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)

        if (data.status === 'complete') {
          stopPolling()
          setStatus('idle')
          setError(null)
          onSuccessRef.current()
          return
        }
        if (data.status === 'error') {
          fail(data.message || 'Bank connection was not completed.')
          return
        }
        // still pending
        if (Date.now() > deadlineRef.current) {
          fail('Timed out waiting for the bank connection to finish. Please try again.')
          return
        }
        timerRef.current = window.setTimeout(() => void poll(linkToken), POLL_INTERVAL_MS)
      } catch (err) {
        // Transient network error while polling — keep trying until the deadline.
        if (Date.now() > deadlineRef.current) {
          fail(err instanceof Error ? err.message : String(err))
          return
        }
        timerRef.current = window.setTimeout(() => void poll(linkToken), POLL_INTERVAL_MS)
      }
    },
    [fail, stopPolling],
  )

  const start = useCallback(
    async (itemId?: number) => {
      stopPolling()
      setStatus('starting')
      setError(null)
      try {
        const res = await apiFetch('/api/plaid/create_link_token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(itemId != null ? { item_id: itemId } : {}),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
        if (!data.hosted_link_url || !data.link_token) {
          throw new Error('Plaid did not return a hosted link URL.')
        }
        hostedUrlRef.current = data.hosted_link_url
        await openExternal(data.hosted_link_url)
        setStatus('waiting')
        deadlineRef.current = Date.now() + POLL_TIMEOUT_MS
        timerRef.current = window.setTimeout(
          () => void poll(data.link_token),
          POLL_INTERVAL_MS,
        )
      } catch (err) {
        fail(err instanceof Error ? err.message : String(err))
      }
    },
    [fail, poll, stopPolling],
  )

  /** Re-open the hosted URL (e.g. the user closed the tab before finishing). */
  const reopen = useCallback(() => {
    if (hostedUrlRef.current) void openExternal(hostedUrlRef.current)
  }, [])

  const cancel = useCallback(() => {
    stopPolling()
    setStatus('idle')
    setError(null)
  }, [stopPolling])

  useEffect(() => stopPolling, [stopPolling])

  return { status, error, start, reopen, cancel }
}
