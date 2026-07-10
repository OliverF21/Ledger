import { usePlaidLink } from 'react-plaid-link'
import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../api/client'
import {
  createLinkTokenBody,
  exchangePlaidPublicToken,
  stagePlaidLinkTokenForOAuth,
} from '../utils/plaidOAuth'

interface PlaidLinkProps {
  onSuccess: () => void
  onError?: (error: string) => void
}

function PlaidLinkContent({
  linkToken,
  onSuccess,
  onError,
  label,
  className,
  onOpen,
}: {
  linkToken: string
  onSuccess: () => void
  onError?: (error: string) => void
  label: string
  className?: string
  onOpen?: () => void
}) {
  const [loading, setLoading] = useState(false)
  const onSuccessRef = useRef(onSuccess)
  const onErrorRef = useRef(onError)
  onSuccessRef.current = onSuccess
  onErrorRef.current = onError

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: async (publicToken) => {
      setLoading(true)
      try {
        await exchangePlaidPublicToken(publicToken)
        onSuccessRef.current()
      } catch (error) {
        onErrorRef.current?.(
          `Failed to link account: ${error instanceof Error ? error.message : String(error)}`,
        )
      } finally {
        setLoading(false)
      }
    },
    onExit: (err) => {
      if (err) {
        onErrorRef.current?.(`Plaid error: ${err.error_message}`)
      }
    },
  })

  const handleOpen = () => {
    stagePlaidLinkTokenForOAuth(linkToken)
    onOpen?.()
    open()
  }

  return (
    <button
      type="button"
      onClick={handleOpen}
      disabled={!ready || loading}
      className={
        className ??
        'w-full bg-ledger-accent text-ledger-accent-on rounded-lg px-4 py-2 font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed'
      }
    >
      {!ready ? 'Initializing...' : loading ? 'Linking...' : label}
    </button>
  )
}

/** Link a new bank/brokerage institution. */
const OAUTH_REDIRECT_HINT =
  'OAuth banks (Chase, Robinhood) need this URL in Plaid Dashboard → Allowed redirect URIs (with trailing slash). Stay on the same host for the whole flow.'

export default function PlaidLinkButton({ onSuccess, onError }: PlaidLinkProps) {
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [oauthWarning, setOauthWarning] = useState<string | null>(null)
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError

  useEffect(() => {
    let cancelled = false

    const fetchLinkToken = async () => {
      try {
        const response = await apiFetch('/api/plaid/create_link_token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(createLinkTokenBody()),
        })
        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          throw new Error(data.detail || `HTTP ${response.status}`)
        }
        const data = await response.json()
        if (!data.link_token) {
          throw new Error('No link_token in response')
        }
        if (!cancelled) {
          setLinkToken(data.link_token)
          setError(null)
          setOauthWarning(data.oauth_redirect_configured ? null : OAUTH_REDIRECT_HINT)
        }
      } catch (err) {
        if (!cancelled) {
          const msg = `Error: ${err instanceof Error ? err.message : String(err)}`
          setError(msg)
          onErrorRef.current?.(msg)
        }
      }
    }

    fetchLinkToken()
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <div className="w-full p-3 rounded-lg bg-red-500/20 border border-red-500/50 text-red-400 text-sm">
        {error}
      </div>
    )
  }

  if (!linkToken) {
    return (
      <button disabled className="w-full bg-ledger-accent/50 text-ledger-accent-on rounded-lg px-4 py-2 font-semibold text-sm cursor-not-allowed">
        Loading Plaid...
      </button>
    )
  }

  return (
    <div className="space-y-[10px]">
      <PlaidLinkContent
        linkToken={linkToken}
        onSuccess={onSuccess}
        onError={onError}
        label="+ Link new account"
      />
      {oauthWarning && (
        <p className="text-[11px] text-ledger-warning leading-snug">{oauthWarning}</p>
      )}
    </div>
  )
}

interface PlaidUpdateProps extends PlaidLinkProps {
  itemId: number
  label?: string
  className?: string
}

/** Re-authenticate or grant additional consent for an existing Item. */
export function PlaidUpdateButton({
  itemId,
  onSuccess,
  onError,
  label = 'Update connection',
  className,
}: PlaidUpdateProps) {
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingOpen, setPendingOpen] = useState(false)
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError

  const fetchLinkToken = useCallback(async (): Promise<string | null> => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch('/api/plaid/create_link_token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(createLinkTokenBody(itemId)),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`)
      }
      if (!data.link_token) {
        throw new Error('No link_token in response')
      }
      setLinkToken(data.link_token)
      return data.link_token
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      onErrorRef.current?.(msg)
      setLinkToken(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [itemId])

  if (error) {
    return (
      <button
        type="button"
        onClick={() => { void fetchLinkToken() }}
        className="text-[11.5px] text-ledger-negative hover:opacity-70 transition-opacity"
      >
        Retry update
      </button>
    )
  }

  if (!linkToken) {
    return (
      <button
        type="button"
        disabled={loading}
        onClick={() => {
          setPendingOpen(true)
          void fetchLinkToken()
        }}
        className={
          className ??
          'text-[11.5px] text-ledger-accent hover:opacity-70 transition-opacity disabled:opacity-40 font-medium'
        }
      >
        {loading ? 'Loading…' : label}
      </button>
    )
  }

  return (
    <PlaidUpdateOpener
      linkToken={linkToken}
      pendingOpen={pendingOpen}
      onPendingOpenHandled={() => setPendingOpen(false)}
      onSuccess={() => {
        setLinkToken(null)
        onSuccess()
      }}
      onError={onError}
      label={label}
      className={className}
    />
  )
}

function PlaidUpdateOpener({
  linkToken,
  pendingOpen,
  onPendingOpenHandled,
  onSuccess,
  onError,
  label,
  className,
}: {
  linkToken: string
  pendingOpen: boolean
  onPendingOpenHandled: () => void
  onSuccess: () => void
  onError?: (error: string) => void
  label: string
  className?: string
}) {
  const openedRef = useRef(false)
  const onSuccessRef = useRef(onSuccess)
  const onErrorRef = useRef(onError)
  onSuccessRef.current = onSuccess
  onErrorRef.current = onError

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: async (publicToken) => {
      try {
        await exchangePlaidPublicToken(publicToken)
        onSuccessRef.current()
      } catch (error) {
        onErrorRef.current?.(
          `Failed to update connection: ${error instanceof Error ? error.message : String(error)}`,
        )
      }
    },
    onExit: (err) => {
      if (err) {
        onErrorRef.current?.(`Plaid error: ${err.error_message}`)
      }
    },
  })

  useEffect(() => {
    if (!pendingOpen || !ready || openedRef.current) return
    openedRef.current = true
    onPendingOpenHandled()
    stagePlaidLinkTokenForOAuth(linkToken)
    open()
  }, [pendingOpen, ready, open, linkToken, onPendingOpenHandled])

  return (
    <button
      type="button"
      onClick={() => {
        openedRef.current = false
        stagePlaidLinkTokenForOAuth(linkToken)
        open()
      }}
      disabled={!ready}
      className={
        className ??
        'text-[11.5px] text-ledger-accent hover:opacity-70 transition-opacity disabled:opacity-40 font-medium'
      }
    >
      {ready ? label : 'Loading…'}
    </button>
  )
}
