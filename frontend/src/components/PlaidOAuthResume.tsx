import { useEffect, useRef, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { apiFetch } from '../api/client'
import {
  clearPlaidLinkToken,
  clearPlaidOAuthParams,
  exchangePlaidPublicToken,
  isPlaidOAuthRedirect,
  readPlaidLinkToken,
} from '../utils/plaidOAuth'

const MISSING_TOKEN_MSG =
  'Plaid session was lost after bank login (often caused by opening Ledger at a different URL than you started with, or by another Link button fetching a new token). Go to Settings and try again — use the same host (localhost vs 127.0.0.1) throughout.'

/**
 * After an OAuth institution (e.g. Chase, Robinhood) redirects back to the app,
 * Plaid Link must be re-opened with the original link token and receivedRedirectUri.
 */
export default function PlaidOAuthResume() {
  const isRedirect = isPlaidOAuthRedirect()
  const [token] = useState<string | null>(() =>
    isRedirect ? readPlaidLinkToken() : null,
  )
  const [error, setError] = useState<string | null>(() =>
    isRedirect && !readPlaidLinkToken() ? MISSING_TOKEN_MSG : null,
  )
  const openedRef = useRef(false)

  const { open, ready } = usePlaidLink({
    token: isRedirect ? token : null,
    receivedRedirectUri: isRedirect ? window.location.href : undefined,
    onSuccess: async (publicToken) => {
      try {
        await exchangePlaidPublicToken(publicToken)
        clearPlaidOAuthParams()
        try {
          await apiFetch('/api/plaid/sync', { method: 'POST' })
        } catch {
          // Account is linked; sync can be retried from Settings.
        }
        window.location.hash = 'settings'
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)
        clearPlaidOAuthParams()
      }
    },
    onExit: (err) => {
      clearPlaidOAuthParams()
      if (err) {
        setError(err.error_message || 'Plaid Link closed before finishing.')
      } else if (!error) {
        setError('Plaid Link closed before finishing. Try linking again from Settings.')
      }
      clearPlaidLinkToken()
    },
  })

  useEffect(() => {
    if (!isRedirect || !token || !ready || openedRef.current) return
    openedRef.current = true
    open()
  }, [isRedirect, token, ready, open])

  if (!isRedirect) return null

  if (error) {
    return (
      <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 max-w-md w-[calc(100%-2rem)] p-4 rounded-lg bg-red-500/20 border border-red-500/50 text-red-300 text-sm shadow-lg">
        {error}
      </div>
    )
  }

  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 px-4 py-2 rounded-lg bg-ledger-inset border border-ledger-border-subtle text-ledger-text-secondary text-sm shadow-lg">
      Finishing bank connection…
    </div>
  )
}
