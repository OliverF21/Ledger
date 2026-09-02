import type { SyncResult } from '../hooks/useSync'

export type ToastTone = 'success' | 'warning' | 'error'

export interface SyncToastCopy {
  tone: ToastTone
  title: string
  detail: string
}

function fallbackDetail(result: SyncResult): string {
  const n = result.transactions_synced ?? 0
  return n === 1 ? 'Synced 1 new transaction' : `Synced ${n} new transactions`
}

/** Copy for the in-app toast after a Plaid sync finishes. */
export function syncToastFromResult(result: SyncResult): SyncToastCopy {
  const detail = (result.message || '').trim() || fallbackDetail(result)
  const failed = result.failed_count > 0 || result.success === false
  if (!failed) {
    return { tone: 'success', title: 'Sync complete', detail }
  }
  const anyOk = (result.items ?? []).some(item => item.status === 'ok')
  if (anyOk) {
    return { tone: 'warning', title: 'Sync finished with issues', detail }
  }
  return { tone: 'error', title: 'Sync failed', detail }
}

export function syncToastFromError(error: unknown): SyncToastCopy {
  return {
    tone: 'error',
    title: 'Sync failed',
    detail: error instanceof Error && error.message
      ? error.message
      : 'Something went wrong while syncing.',
  }
}
