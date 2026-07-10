import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'

export const SYNC_COMPLETE_EVENT = 'ledger:synced'

export interface SyncItemResult {
  item_id: number
  institution_name: string | null
  status: 'ok' | 'login_required' | 'error'
  synced?: number
  removed?: number
  enrichment_backfilled?: number
  error?: string | null
}

export interface SyncResult {
  success: boolean
  message: string
  transactions_synced: number
  enrichment_backfilled: number
  failed_count: number
  items: SyncItemResult[]
}

export function notifySyncComplete(result: SyncResult) {
  window.dispatchEvent(new CustomEvent(SYNC_COMPLETE_EVENT, { detail: result }))
}

/** Re-run `handler` after any successful Plaid sync (manual or on startup). */
export function useOnSyncComplete(handler: () => void) {
  useEffect(() => {
    window.addEventListener(SYNC_COMPLETE_EVENT, handler)
    return () => window.removeEventListener(SYNC_COMPLETE_EVENT, handler)
  }, [handler])
}

/** Pull fresh transactions from Plaid once per app session after login. */
export function useStartupSync(enabled: boolean) {
  const ran = useRef(false)

  useEffect(() => {
    if (!enabled) {
      ran.current = false
      return
    }
    if (ran.current) return
    ran.current = true

    let cancelled = false
    ;(async () => {
      try {
        const statusRes = await apiFetch('/api/plaid/sync/status')
        if (!statusRes.ok || cancelled) return
        const status = await statusRes.json()
        if (!status.item_count) return

        const response = await apiFetch('/api/plaid/sync', { method: 'POST' })
        if (!response.ok || cancelled) return
        const result: SyncResult = await response.json()
        notifySyncComplete(result)
      } catch (error) {
        console.debug('Startup sync skipped or failed:', error)
      }
    })()

    return () => { cancelled = true }
  }, [enabled])
}

export function useSync() {
  const [syncing, setSyncing] = useState(false)

  const sync = async (): Promise<SyncResult | null> => {
    setSyncing(true)
    try {
      const response = await apiFetch('/api/plaid/sync', { method: 'POST' })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `Sync failed (${response.status})`)
      }
      const result: SyncResult = await response.json()
      notifySyncComplete(result)
      return result
    } finally {
      setSyncing(false)
    }
  }

  return { syncing, sync }
}
