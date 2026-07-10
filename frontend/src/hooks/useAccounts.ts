import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import { useOnSyncComplete } from './useSync'

export interface AccountItem {
  id: number
  item_id: number
  institution_name: string | null
  institution_logo?: string | null
  institution_color?: string | null
  name: string
  type: string
  subtype: string
  current_balance: number
}

export function useAccounts(enabled = true) {
  const [accounts, setAccounts] = useState<AccountItem[]>([])
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    if (!enabled) return
    try {
      const res = await apiFetch('/api/plaid/accounts')
      const data = await res.json()
      setAccounts(data.accounts || [])
    } catch (error) {
      console.error('Failed to fetch accounts:', error)
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) {
      setAccounts([])
      setLoading(false)
      return
    }
    setLoading(true)
    refetch()
  }, [enabled, refetch])

  useOnSyncComplete(refetch)

  return { accounts, loading, refetch }
}
