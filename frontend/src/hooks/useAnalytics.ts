import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import { useOnSyncComplete } from './useSync'

export interface CategorySpend {
  name: string
  value: number
  color: string
}

export interface RecentTransaction {
  id: number
  merchant: string
  account_name: string | null
  date: string
  category: string | null
  amount: number
  initials: string
}

export interface MonthlySummary {
  month: string
  total_spending: number
  total_income: number
  savings_rate: number
  spending_by_category: CategorySpend[]
  recent_transactions: RecentTransaction[]
  prev_month_spending: number
}

export function useAnalytics(month?: string) {
  const [data, setData] = useState<MonthlySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    setLoading(true)
    setError(null)
    const url = month ? `/api/analytics/summary?month=${month}` : '/api/analytics/summary'
    apiFetch(url)
      .then(r => {
        if (!r.ok) return r.json().then(e => Promise.reject(e.detail || 'Failed to load'))
        return r.json()
      })
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [month])

  useEffect(() => { refetch() }, [refetch])

  useOnSyncComplete(refetch)

  return { data, loading, error }
}
