import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

export interface AllocationSlice {
  type: string
  value: number
  pct: number
  color: string
}

export interface InvestmentsSummary {
  total_value: number
  total_cost_basis: number | null
  unrealized_gain: number | null
  allocation: AllocationSlice[]
  account_count: number
  position_count: number
  last_synced_at: string | null
}

export function useInvestmentsSummary() {
  const [data, setData] = useState<InvestmentsSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/api/investments/summary')
      setData(await res.json())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  return { data, loading, refetch }
}

export interface Position {
  ticker: string | null
  name: string | null
  type: string | null
  quantity: number
  price: number | null
  value: number
  cost_basis: number | null
  gain: number | null
  gain_pct: number | null
  currency: string | null
}

export interface AccountHoldings {
  id: number
  name: string
  institution_name: string | null
  subtype: string | null
  total_value: number
  positions: Position[]
}

export function useInvestmentsHoldings() {
  const [accounts, setAccounts] = useState<AccountHoldings[]>([])
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/api/investments/holdings')
      const data = await res.json()
      setAccounts(data.accounts ?? [])
    } catch {
      setAccounts([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  return { accounts, loading, refetch }
}

export interface HistoryPoint {
  date: string
  total: number
}

export interface InvestmentsHistory {
  snapshots: HistoryPoint[]
  change_amount: number
  change_pct: number
}

export function useInvestmentsHistory(months: number) {
  const [data, setData] = useState<InvestmentsHistory | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/investments/history?months=${months}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [months])

  return { data, loading }
}

export interface InvestmentActivityItem {
  id: number
  account_name: string
  ticker: string | null
  name: string
  type: string
  subtype: string | null
  amount: number
  quantity: number | null
  price: number | null
  date: string
}

export function useInvestmentTransactions(months: number) {
  const [transactions, setTransactions] = useState<InvestmentActivityItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/investments/transactions?months=${months}`)
      .then(r => r.json())
      .then(d => setTransactions(d.transactions ?? []))
      .catch(() => setTransactions([]))
      .finally(() => setLoading(false))
  }, [months])

  return { transactions, loading }
}
