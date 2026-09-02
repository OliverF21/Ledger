import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'

export const SYNC_COMPLETE_EVENT = 'ledger:synced'

/** Minimum gap between automatic sync attempts (startup + visibility). */
const AUTO_SYNC_MIN_INTERVAL_MS = 5 * 60 * 1000

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

/** Re-run `handler` after any Plaid sync (manual or on startup). */
export function useOnSyncComplete(handler: (result: SyncResult) => void) {
  useEffect(() => {
    const listener = (event: Event) => {
      const result = (event as CustomEvent<SyncResult>).detail
      if (result) handler(result)
    }
    window.addEventListener(SYNC_COMPLETE_EVENT, listener)
    return () => window.removeEventListener(SYNC_COMPLETE_EVENT, listener)
  }, [handler])
}

// Module-level so React Strict Mode remounts share one in-flight request
// instead of cancelling the first effect and skipping the second.
let autoSyncInFlight: Promise<void> | null = null
let lastAutoSyncAt = 0

async function pullLatestTransactions(): Promise<SyncResult | null> {
  const statusRes = await apiFetch('/api/plaid/sync/status')
  if (!statusRes.ok) return null
  const status = await statusRes.json()
  if (!status.item_count) return null

  const response = await apiFetch('/api/plaid/sync', { method: 'POST' })
  if (!response.ok) return null
  const result: SyncResult = await response.json()
  notifySyncComplete(result)
  return result
}

function kickAutoSync(force = false): void {
  if (autoSyncInFlight) return
  if (!force && lastAutoSyncAt && Date.now() - lastAutoSyncAt < AUTO_SYNC_MIN_INTERVAL_MS) {
    return
  }

  autoSyncInFlight = (async () => {
    try {
      const result = await pullLatestTransactions()
      if (result) lastAutoSyncAt = Date.now()
    } catch (error) {
      console.debug('Startup sync skipped or failed:', error)
    } finally {
      autoSyncInFlight = null
    }
  })()
}

/**
 * Pull fresh transactions from Plaid when the main app opens, and again when
 * the window becomes visible after being hidden (throttled).
 *
 * Uses a module-level in-flight promise so React Strict Mode's mount → cleanup
 * → remount cycle cannot cancel the first attempt and then skip the second.
 */
export function useStartupSync(enabled: boolean) {
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  useEffect(() => {
    if (!enabled) return

    kickAutoSync(true)

    const onVisibility = () => {
      if (document.visibilityState === 'visible' && enabledRef.current) {
        kickAutoSync(false)
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
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
      lastAutoSyncAt = Date.now()
      return result
    } finally {
      setSyncing(false)
    }
  }

  return { syncing, sync }
}
