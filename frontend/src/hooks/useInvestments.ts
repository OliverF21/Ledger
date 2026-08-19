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

export interface RiskMetrics {
  lookback_days: number
  as_of: string
  volatility_pct: number | null
  sharpe_ratio: number | null
  var_95_pct: number | null
  var_99_pct: number | null
  max_drawdown_pct: number | null
  drawdown_duration_days: number | null
  beta_vs_spy: number | null
  cagr_pct: number | null
  twr_pct: number | null
  mwr_pct: number | null
  risk_free_rate_pct: number
  data_points: number
}

export function useInvestmentsRisk(lookbackDays: number = 365) {
  const [data, setData] = useState<RiskMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/investments/risk/metrics?lookback_days=${lookbackDays}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [lookbackDays])

  return { data, loading }
}

export interface AllocationWeight {
  ticker: string
  current_weight_pct: number
  suggested_weight_pct: number
}

export interface ObjectiveResponse {
  name: string
  tickers: AllocationWeight[]
  expected_return_pct: number | null
  volatility_pct: number | null
  sharpe: number | null
}

export interface FrontierPoint {
  volatility_pct: number
  return_pct: number
}

export interface SectorBreakdownRow {
  sector: string
  weight_pct: number
  floor_pct: number
  cap_pct: number
}

// Shared by cap_relaxed (a single entry-or-null, from relax_position_cap_if_needed)
// and clip_log (a list of entries, from clip_sector_bounds) -- two different
// producers with different shapes, hence every field is optional rather than
// this being two types. Mirrors backend ClipLogEntry (routes/portfolio_risk.py).
export interface ClipLogEntry {
  sector: string | null
  requested_floor: number | null
  clipped_to: number | null
  requested_cap: number | null
  relaxed_to: number | null
  reason: string | null
}

export interface OptimizationSuggestion {
  tickers: AllocationWeight[]
  current_expected_return_pct: number | null
  current_volatility_pct: number | null
  current_sharpe: number | null
  suggested_expected_return_pct: number | null
  suggested_volatility_pct: number | null
  suggested_sharpe: number | null
  data_points: number
  insufficient_data: boolean
  advanced_enabled: boolean
  position_cap_pct: number
  cap_relaxed: ClipLogEntry | null
  objectives: ObjectiveResponse[]
  frontier_points: FrontierPoint[] | null
  sector_breakdown: SectorBreakdownRow[] | null
  clip_log: ClipLogEntry[]
}

export function useInvestmentsOptimization(lookbackDays: number = 365) {
  const [data, setData] = useState<OptimizationSuggestion | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/investments/risk/optimize?lookback_days=${lookbackDays}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [lookbackDays])

  return { data, loading }
}

export interface OptimizationSettings {
  advanced_enabled: boolean
  position_cap_pct: number
  concentration_strength: number
}

export function useOptimizationPreferences() {
  const [data, setData] = useState<OptimizationSettings | null>(null)
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(() => {
    setLoading(true)
    apiFetch('/api/investments/optimization-settings')
      .then(r => r.json()).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const update = useCallback(async (patch: Partial<OptimizationSettings>) => {
    const response = await apiFetch('/api/investments/optimization-settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    })
    const updated = await response.json()
    setData(updated)
    return updated
  }, [])

  return { data, loading, update, refetch }
}

export interface SectorConstraint {
  id: number
  sector: string
  floor_pct: number
  cap_pct: number
}

export function useSectorConstraints() {
  const [data, setData] = useState<SectorConstraint[]>([])
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(() => {
    setLoading(true)
    return apiFetch('/api/investments/sector-constraints')
      .then(r => r.json()).then(setData).catch(() => setData([])).finally(() => setLoading(false))
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const create = useCallback(async (input: Omit<SectorConstraint, 'id'>): Promise<SectorConstraint> => {
    const res = await apiFetch('/api/investments/sector-constraints', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.detail || `Create failed (HTTP ${res.status})`)
    await refetch()
    return json as SectorConstraint
  }, [refetch])

  const update = useCallback(async (id: number, input: Omit<SectorConstraint, 'id'>): Promise<SectorConstraint> => {
    const res = await apiFetch(`/api/investments/sector-constraints/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.detail || `Update failed (HTTP ${res.status})`)
    await refetch()
    return json as SectorConstraint
  }, [refetch])

  const remove = useCallback(async (id: number): Promise<void> => {
    const res = await apiFetch(`/api/investments/sector-constraints/${id}`, { method: 'DELETE' })
    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.detail || `Delete failed (HTTP ${res.status})`)
    }
    await refetch()
  }, [refetch])

  return { data, loading, create, update, remove, refetch }
}

export interface TickerConstraint {
  id: number
  ticker: string
  floor_pct: number
  cap_pct: number
}

export function useTickerConstraints() {
  const [data, setData] = useState<TickerConstraint[]>([])
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(() => {
    setLoading(true)
    return apiFetch('/api/investments/ticker-constraints')
      .then(r => r.json()).then(setData).catch(() => setData([])).finally(() => setLoading(false))
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const create = useCallback(async (input: Omit<TickerConstraint, 'id'>): Promise<TickerConstraint> => {
    const res = await apiFetch('/api/investments/ticker-constraints', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.detail || `Create failed (HTTP ${res.status})`)
    await refetch()
    return json as TickerConstraint
  }, [refetch])

  const update = useCallback(async (id: number, input: Omit<TickerConstraint, 'id'>): Promise<TickerConstraint> => {
    const res = await apiFetch(`/api/investments/ticker-constraints/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.detail || `Update failed (HTTP ${res.status})`)
    await refetch()
    return json as TickerConstraint
  }, [refetch])

  const remove = useCallback(async (id: number): Promise<void> => {
    const res = await apiFetch(`/api/investments/ticker-constraints/${id}`, { method: 'DELETE' })
    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.detail || `Delete failed (HTTP ${res.status})`)
    }
    await refetch()
  }, [refetch])

  return { data, loading, create, update, remove, refetch }
}
