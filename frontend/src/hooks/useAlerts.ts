import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

export interface BudgetExceededAlert {
  category: string
  spent: number
  limit: number
}

export interface LargeTransactionAlert {
  id: number
  merchant: string
  amount: number
  date: string
}

export interface ActiveAlerts {
  budget_exceeded: BudgetExceededAlert[]
  large_transactions: LargeTransactionAlert[]
}

export function useAlerts() {
  const [alerts, setAlerts] = useState<ActiveAlerts>({ budget_exceeded: [], large_transactions: [] })
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    try {
      const res = await apiFetch('/api/settings/alerts/active')
      const data = await res.json()
      setAlerts({
        budget_exceeded: data.budget_exceeded || [],
        large_transactions: data.large_transactions || [],
      })
    } catch (error) {
      console.error('Failed to fetch active alerts:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  return { alerts, loading, refetch }
}
