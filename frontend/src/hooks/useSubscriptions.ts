import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

export interface SubscriptionItem {
  merchant: string
  category: string
  cadence: string
  average_amount: number
  last_date: string
  next_expected_date: string
  occurrence_count: number
}

export function useSubscriptions() {
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([])
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    try {
      const res = await apiFetch('/api/subscriptions')
      const data = await res.json()
      setSubscriptions(data.subscriptions || [])
    } catch (error) {
      console.error('Failed to fetch subscriptions:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  return { subscriptions, loading, refetch }
}
