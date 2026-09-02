import { describe, expect, it } from 'vitest'
import type { SyncResult } from '../hooks/useSync'
import { syncToastFromError, syncToastFromResult } from './syncToast'

function result(partial: Partial<SyncResult> = {}): SyncResult {
  return {
    success: true,
    message: 'Synced 4 new transactions',
    transactions_synced: 4,
    enrichment_backfilled: 0,
    failed_count: 0,
    items: [],
    ...partial,
  }
}

describe('syncToastFromResult', () => {
  it('announces a clean sync as complete', () => {
    expect(syncToastFromResult(result())).toEqual({
      tone: 'success',
      title: 'Sync complete',
      detail: 'Synced 4 new transactions',
    })
  })

  it('falls back to a transaction count when the server message is empty', () => {
    expect(syncToastFromResult(result({ message: '  ', transactions_synced: 1 }))).toEqual({
      tone: 'success',
      title: 'Sync complete',
      detail: 'Synced 1 new transaction',
    })
  })

  it('warns when some institutions succeeded and others failed', () => {
    expect(syncToastFromResult(result({
      success: false,
      failed_count: 1,
      message: 'Synced 2 new transactions, 1 institution failed',
      items: [
        { item_id: 1, institution_name: 'Chase', status: 'ok', synced: 2 },
        { item_id: 2, institution_name: 'Amex', status: 'login_required', error: 'login required' },
      ],
    }))).toEqual({
      tone: 'warning',
      title: 'Sync finished with issues',
      detail: 'Synced 2 new transactions, 1 institution failed',
    })
  })

  it('treats an all-failed run as an error', () => {
    expect(syncToastFromResult(result({
      success: false,
      failed_count: 1,
      transactions_synced: 0,
      message: '0 institution failed',
      items: [{ item_id: 1, institution_name: 'Chase', status: 'error', error: 'timeout' }],
    })).tone).toBe('error')
  })
})

describe('syncToastFromError', () => {
  it('uses the thrown Error message', () => {
    expect(syncToastFromError(new Error('Plaid is not configured. Add your keys in Settings → Plaid.'))).toEqual({
      tone: 'error',
      title: 'Sync failed',
      detail: 'Plaid is not configured. Add your keys in Settings → Plaid.',
    })
  })

  it('uses a generic line when the thrown value has no message', () => {
    expect(syncToastFromError({}).detail).toBe('Something went wrong while syncing.')
  })
})
