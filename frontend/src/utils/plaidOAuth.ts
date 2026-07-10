import { apiFetch } from '../api/client'

/** Saved when the user opens Link — must survive OAuth redirects (Chase, Robinhood). */
export const PLAID_LINK_TOKEN_KEY = 'ledger_plaid_link_token'

export function isPlaidOAuthRedirect(): boolean {
  return new URLSearchParams(window.location.search).has('oauth_state_id')
}

/** Plaid redirect URI must match the browser origin exactly (no hash). */
export function buildPlaidRedirectUri(): string {
  return `${window.location.origin}/`
}

/** Call immediately before open() so OAuth return can resume the same session. */
export function stagePlaidLinkTokenForOAuth(token: string): void {
  localStorage.setItem(PLAID_LINK_TOKEN_KEY, token)
}

export function readPlaidLinkToken(): string | null {
  return localStorage.getItem(PLAID_LINK_TOKEN_KEY)
}

export function clearPlaidLinkToken(): void {
  localStorage.removeItem(PLAID_LINK_TOKEN_KEY)
}

/** Remove oauth_state_id from the URL without reloading. */
export function clearPlaidOAuthParams(): void {
  const url = new URL(window.location.href)
  if (!url.searchParams.has('oauth_state_id')) return
  url.searchParams.delete('oauth_state_id')
  const query = url.searchParams.toString()
  const next = url.pathname + (query ? `?${query}` : '') + url.hash
  window.history.replaceState({}, '', next)
}

export function createLinkTokenBody(itemId?: number): Record<string, unknown> {
  const body: Record<string, unknown> = {
    redirect_uri: buildPlaidRedirectUri(),
  }
  if (itemId != null) {
    body.item_id = itemId
  }
  return body
}

export async function exchangePlaidPublicToken(publicToken: string): Promise<void> {
  const response = await apiFetch('/api/plaid/set_access_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ public_token: publicToken }),
  })
  const data = await response.json()
  if (!response.ok) {
    throw new Error(data.detail || 'Failed to link account')
  }
  if (!data.success) {
    throw new Error('Failed to link account')
  }
  clearPlaidLinkToken()
}
