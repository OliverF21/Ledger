import { useState, useMemo, useEffect } from 'react'
import { ArrowUp, ArrowDown, RefreshCw, AlertTriangle } from 'lucide-react'
import { PieChart, Pie, Cell, Sector, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../api/client'
import {
  useInvestmentsSummary,
  useInvestmentsHoldings,
  useInvestmentsHistory,
  useInvestmentTransactions,
  useInvestmentsRisk,
  useInvestmentsOptimization,
  useOptimizationPreferences,
  type AllocationSlice,
  type ObjectiveResponse,
} from '../hooks/useInvestments'
import EfficientFrontierChart, { type ObjectiveMarker } from '../components/EfficientFrontierChart'
import OptimizationPreferencesPanel from '../components/OptimizationPreferencesPanel'

import { alphaColor, mixHex } from '../utils/color'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number | null): string {
  if (n === null) return '—'
  return `${n >= 0 ? '' : ''}${n.toFixed(2)}%`
}

function formatSecurityType(t: string | null): string {
  if (!t) return 'Other'
  if (t.toLowerCase() === 'etf') return 'ETF'
  return t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' ')
}

function deltaPp(current: number | null, suggested: number | null): number | null {
  return current === null || suggested === null ? null : suggested - current
}

function deltaRaw(current: number | null, suggested: number | null | undefined): number | null {
  return current == null || suggested == null ? null : suggested - current
}

// Matches the "Risk & performance" card's glass-chip stat tiles above --
// headline value + a colored delta badge instead of a bare "X% -> Y%"
// string, reusing the same ArrowUp/ArrowDown + tinted-pill language already
// used for the portfolio-value header's period-change badge.
function StatTile({ label, value, delta, deltaGoodDirection }: {
  label: string; value: string; delta: number | null; deltaGoodDirection: 'up' | 'down'
}) {
  const deltaIsGood = delta !== null && ((delta >= 0) === (deltaGoodDirection === 'up'))
  return (
    <div className="glass-chip px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">{label}</div>
      <div className="flex items-baseline gap-[6px] mt-0.5">
        <div className="text-[15px] font-bold tabular-nums">{value}</div>
        {delta !== null && Math.abs(delta) >= 0.005 && (
          <span className={`inline-flex items-center gap-[1px] text-[10.5px] font-semibold ${deltaIsGood ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
            {delta >= 0 ? <ArrowUp className="w-[9px] h-[9px]" strokeWidth={3} /> : <ArrowDown className="w-[9px] h-[9px]" strokeWidth={3} />}
            {Math.abs(delta).toFixed(2)}
          </span>
        )}
      </div>
    </div>
  )
}

function formatActivityDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const ALLOCATION_PALETTE = [
  '#5b8def', '#4fc4c4', '#8a7df0', '#4ec38a', '#d9a85b',
  '#e7705f', '#f0a87d', '#7fb0ff', '#a8d8a8', '#c084fc',
]

// 3 years, matching the backend's own DEFAULT_LOOKBACK_DAYS (optimization_service.py)
// -- deliberately NOT the page's 6M/1Y history-chart toggle (lookbackDays below).
// That toggle controls how much of the net-worth chart to show; the optimizer's
// statistical estimation window is a different concern that should stay long and
// stable regardless of which period the user happens to be glancing at.
const OPTIMIZATION_LOOKBACK_DAYS = 1095

// Mirrors EfficientFrontierChart's internal OBJECTIVE_LABELS (not exported from
// there) -- used here for the per-objective comparison table's row/section labels.
const OBJECTIVE_LABELS: Record<string, string> = {
  max_sharpe: 'Max Sharpe',
  max_quadratic_utility: 'Max Quadratic Utility',
}

function buildMarkers(objectives: ObjectiveResponse[]): ObjectiveMarker[] {
  const colors: Record<string, string> = { max_sharpe: '#e7705f', max_quadratic_utility: '#d9a85b' }
  return objectives
    .filter(o => o.volatility_pct != null && o.expected_return_pct != null)
    .map(o => ({ name: o.name, volatility_pct: o.volatility_pct!, return_pct: o.expected_return_pct!, color: colors[o.name] ?? '#5b8def' }))
}

type AllocationView = 'type' | 'security'

function buildSecurityAllocation(
  accounts: { positions: { ticker: string | null; name: string | null; value: number }[] }[],
  totalValue: number,
): AllocationSlice[] {
  const bySecurity = new Map<string, number>()

  for (const account of accounts) {
    for (const position of account.positions) {
      const key = position.ticker ?? position.name ?? 'Unknown'
      bySecurity.set(key, (bySecurity.get(key) ?? 0) + position.value)
    }
  }

  return [...bySecurity.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, value], i) => ({
      type: label,
      value: Math.round(value * 100) / 100,
      pct: totalValue ? Math.round((value / totalValue) * 1000) / 10 : 0,
      color: ALLOCATION_PALETTE[i % ALLOCATION_PALETTE.length],
    }))
}

export default function Investments() {
  const { data: summary, loading: summaryLoading, refetch: refetchSummary } = useInvestmentsSummary()
  const { accounts, loading: holdingsLoading, refetch: refetchHoldings } = useInvestmentsHoldings()
  const [historyRange, setHistoryRange] = useState<'6M' | '1Y'>('6M')
  const historyMonths = historyRange === '6M' ? 6 : 12
  const lookbackDays = historyRange === '6M' ? 182 : 365
  const { transactions, loading: txnsLoading } = useInvestmentTransactions(historyMonths)
  const { data: history, loading: historyLoading } = useInvestmentsHistory(historyMonths)
  const { data: risk, loading: riskLoading } = useInvestmentsRisk(lookbackDays)
  const { data: optimization, loading: optimizationLoading, refetch: refetchOptimization } = useInvestmentsOptimization(OPTIMIZATION_LOOKBACK_DAYS)
  const { data: optimizationPrefs, update: updateOptimizationPrefs } = useOptimizationPreferences()
  const [allocationView, setAllocationView] = useState<AllocationView>('security')
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const [activityExpanded, setActivityExpanded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [runningOptimization, setRunningOptimization] = useState(false)
  const [selectedObjective, setSelectedObjective] = useState<string>('max_sharpe')

  // Distinct from optimizationLoading, which useInvestmentsOptimization only
  // ever sets true for the INITIAL mount fetch (deliberately -- flipping it
  // during a background refresh would unmount the panel mid-edit). A manual
  // "Run optimization" click is a deliberate action, not a background
  // side-effect, so it gets its own loading flag to drive the button.
  const handleRunOptimization = async () => {
    setRunningOptimization(true)
    try {
      await refetchOptimization()
    } finally {
      setRunningOptimization(false)
    }
  }

  // Gates the results section below the panel: BOTH the live toggle
  // (optimizationPrefs, updates instantly on flip) and the last actually-run
  // result (optimization.advanced_enabled, only updates after Run) must
  // agree -- otherwise flipping the toggle off would leave stale advanced
  // results on screen until the next manual Run, and flipping it on would
  // briefly show the previous OFF-state's empty result.
  const showOptimizationResults = Boolean(optimizationPrefs?.advanced_enabled && optimization?.advanced_enabled)

  // Falls back to the first objective the backend actually returned (rather
  // than assuming 'max_sharpe' is present) so a stale selectedObjective from
  // a previous run -- e.g. advanced mode was toggled off and back on with a
  // different objective set -- can't leave the panel showing nothing.
  const activeObjective = useMemo(
    () => optimization?.objectives.find(o => o.name === selectedObjective) ?? optimization?.objectives[0] ?? null,
    [optimization, selectedObjective],
  )

  const loading = summaryLoading || holdingsLoading
  const typeAllocationData = summary?.allocation ?? []
  const securityAllocationData = useMemo(
    () => (summary ? buildSecurityAllocation(accounts, summary.total_value) : []),
    [accounts, summary],
  )
  const allocationData = allocationView === 'type' ? typeAllocationData : securityAllocationData
  const activeAllocation = activeSlice !== null ? allocationData[activeSlice] ?? null : null

  useEffect(() => {
    setActiveSlice(null)
  }, [allocationView, allocationData.length])
  const visibleTransactions = activityExpanded ? transactions : transactions.slice(0, 4)

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await apiFetch('/api/investments/refresh', { method: 'POST' })
      await Promise.all([refetchSummary(), refetchHoldings()])
    } catch (error) {
      console.error('Failed to refresh investments:', error)
    } finally {
      setRefreshing(false)
    }
  }

  const hasAccounts = !loading && summary && summary.account_count > 0

  if (!loading && (!summary || summary.account_count === 0)) {
    return (
      <div className="flex flex-col items-center justify-center h-[420px] glass-card text-center px-6">
        <div className="text-[15px] font-semibold mb-1.5">No investment accounts linked</div>
        <div className="text-[13px] text-ledger-text-faint max-w-[360px]">
          Connect a brokerage account in Settings to see position-level holdings here.
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Portfolio value over time + allocation */}
      <div className="grid grid-cols-[1.85fr_1.15fr] gap-3 items-stretch">
        <div className="glass-card p-4">
          <div className="flex items-start justify-between mb-2.5">
            <div>
              <div className="text-[13px] font-semibold">Portfolio value</div>
              <div className="text-[11px] text-ledger-text-faint mt-[2px]">
                {summary?.account_count ?? 0} accounts · {summary?.position_count ?? 0} positions
                {hasAccounts && summary?.last_synced_at && (
                  <> · Last synced {new Date(summary.last_synced_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="inline-flex items-center gap-[5px] text-[11.5px] px-[8px] py-[3px] rounded-[6px] font-semibold glass-chip text-ledger-text-faint hover:text-ledger-text-primary transition-all disabled:opacity-60"
              >
                <RefreshCw className={`w-[12px] h-[12px] ${refreshing ? 'animate-spin' : ''}`} strokeWidth={2} />
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
              {!historyLoading && history && history.snapshots.length >= 2 && history.change_amount !== 0 && (
                <span className={`inline-flex items-center gap-[3px] text-[11.5px] font-semibold px-[6px] py-[2px] rounded-[6px] ${
                  history.change_amount >= 0
                    ? 'bg-[rgba(78,195,138,0.13)] text-ledger-positive'
                    : 'bg-[rgba(231,112,95,0.13)] text-ledger-negative'
                }`}>
                  {history.change_amount >= 0
                    ? <ArrowUp className="w-[11px] h-[11px]" strokeWidth={2.5} />
                    : <ArrowDown className="w-[11px] h-[11px]" strokeWidth={2.5} />}
                  {Math.abs(history.change_pct).toFixed(1)}%
                </span>
              )}
              <div className="flex gap-[5px]">
                {(['6M', '1Y'] as const).map(r => (
                  <button
                    key={r}
                    onClick={() => setHistoryRange(r)}
                    className={`text-[11.5px] px-[8px] py-[3px] rounded-[6px] font-semibold transition-all ${
                      historyRange === r
                        ? 'bg-ledger-accent text-ledger-accent-on'
                        : 'glass-chip text-ledger-text-faint hover:text-ledger-text-primary'
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {historyLoading ? (
            <div className="h-[240px] flex items-center justify-center text-ledger-text-faint text-[13px]">Loading…</div>
          ) : !history || history.snapshots.length === 0 ? (
            <div className="h-[240px] flex items-center justify-center text-ledger-text-faint text-[13px]">No history yet</div>
          ) : (
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history.snapshots}>
                  <defs>
                    <linearGradient id="investmentHistoryFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#5b8def" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#5b8def" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="0" stroke="rgba(255,255,255,0.06)" horizontal={true} vertical={false} />
                  <XAxis
                    dataKey="date"
                    stroke="#5c626f"
                    axisLine={false}
                    tickLine={false}
                    style={{ fontSize: '12px' }}
                    tickFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  />
                  <YAxis
                    stroke="#5c626f"
                    axisLine={false}
                    tickLine={false}
                    style={{ fontSize: '12px' }}
                    tickFormatter={v => `$${fmt(v)}`}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#11141a', border: '1px solid #1c2029', borderRadius: '8px' }}
                    labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    formatter={(val: number) => [`$${fmt(val)}`, 'Value']}
                  />
                  <Area type="monotone" dataKey="total" stroke="#5b8def" strokeWidth={2.5} fill="url(#investmentHistoryFill)" dot={history.snapshots.length === 1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {!historyLoading && history && history.snapshots.length > 0 && (
            <div className="grid grid-cols-3 gap-2.5 mt-3 pt-3 border-t border-ledger-border-subtle">
              <div className="glass-chip px-3 py-2">
                <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Current</div>
                <div className="text-[15px] font-bold tabular-nums mt-[2px]">
                  ${fmt(history.snapshots[history.snapshots.length - 1]?.total ?? 0)}
                </div>
              </div>
              <div className="glass-chip px-3 py-2">
                <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Period change</div>
                <div className={`text-[15px] font-bold tabular-nums mt-[2px] ${history.change_amount >= 0 ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
                  {history.change_amount >= 0 ? '+' : '−'}${fmt(Math.abs(history.change_amount))}
                </div>
              </div>
              <div className="glass-chip px-3 py-2">
                <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Range</div>
                <div className="text-[15px] font-bold tabular-nums mt-[2px]">
                  {historyRange}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Allocation donut — matches overview visual language */}
        <div className="glass-card p-4 flex flex-col">
          <div className="flex items-start justify-between gap-3 mb-[2px]">
            <div>
              <div className="text-[13px] font-semibold">Allocation</div>
              <div className="text-[11px] text-ledger-text-faint mt-[2px]">
                {allocationView === 'type' ? 'By security type' : 'By security'}
              </div>
            </div>
            <div className="flex gap-[5px] shrink-0">
              {(['security', 'type'] as const).map(view => (
                <button
                  key={view}
                  onClick={() => setAllocationView(view)}
                  className={`text-[11.5px] px-[8px] py-[3px] rounded-[6px] font-semibold transition-all ${
                    allocationView === view
                      ? 'bg-ledger-accent text-ledger-accent-on'
                      : 'glass-chip text-ledger-text-faint hover:text-ledger-text-primary'
                  }`}
                >
                  {view === 'type' ? 'Type' : 'Security'}
                </button>
              ))}
            </div>
          </div>
          {loading ? (
            <div className="flex-1 flex items-center justify-center text-ledger-text-faint text-[13px]">Loading…</div>
          ) : allocationData.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-ledger-text-faint text-[12px]">No positions yet</div>
          ) : (
            <div className="relative flex-1 mt-1 min-h-[252px] pr-[214px]">
              <div className="relative h-[248px] w-[244px] overflow-visible">
                <div
                  className="absolute left-1/2 top-1/2 h-[220px] w-[220px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[28px] pointer-events-none"
                  style={{
                    background: `radial-gradient(circle, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', activeAllocation ? 0.28 : 0.16)} 0%, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', activeAllocation ? 0.18 : 0.10)} 28%, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', 0.08)} 54%, transparent 82%)`,
                  }}
                />
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <defs>
                      {allocationData.map((entry, i) => (
                        <radialGradient
                          id={`investment-allocation-slice-${i}`}
                          key={entry.type}
                          cx="42%"
                          cy="42%"
                          r="78%"
                          fx="36%"
                          fy="36%"
                        >
                          <stop offset="0%" stopColor={mixHex(entry.color, '#ffffff', 0.22)} stopOpacity={0.98} />
                          <stop offset="48%" stopColor={entry.color} stopOpacity={0.94} />
                          <stop offset="100%" stopColor={mixHex(entry.color, '#0d0f14', 0.12)} stopOpacity={0.88} />
                        </radialGradient>
                      ))}
                    </defs>
                    <Pie
                      data={allocationData}
                      cx="50%" cy="50%"
                      innerRadius={78} outerRadius={114}
                      paddingAngle={1}
                      dataKey="value"
                      activeIndex={activeSlice ?? undefined}
                      activeShape={(props: unknown) => (
                        <Sector {...props as any} outerRadius={(props as any).outerRadius + 4} style={{ outline: 'none' }} />
                      )}
                      onMouseEnter={(_, i) => setActiveSlice(i)}
                      onMouseLeave={() => setActiveSlice(null)}
                      style={{ outline: 'none' }}
                      isAnimationActive={false}
                    >
                      {allocationData.map((entry, i) => (
                        <Cell
                          key={entry.type}
                          fill={`url(#investment-allocation-slice-${i})`}
                          stroke={activeSlice === i ? alphaColor(entry.color, 0.34) : 'rgba(255,255,255,0.06)'}
                          strokeWidth={activeSlice === i ? 0.9 : 0.4}
                          style={{
                            outline: 'none',
                            cursor: 'default',
                            filter: activeSlice === i ? `drop-shadow(0 0 12px ${alphaColor(entry.color, 0.22)})` : undefined,
                          }}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <div
                    className="absolute left-1/2 top-1/2 h-[196px] w-[196px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[18px]"
                    style={{
                      background: `radial-gradient(circle, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', activeAllocation ? 0.42 : 0.28)} 0%, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', activeAllocation ? 0.30 : 0.18)} 18%, rgba(54,60,92,0.24) 34%, rgba(26,30,44,0.10) 56%, rgba(18,21,30,0.04) 72%, rgba(18,21,30,0) 100%)`,
                    }}
                  />
                  <div
                    className="absolute left-1/2 top-1/2 h-[130px] w-[130px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[12px]"
                    style={{
                      background: `radial-gradient(circle, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', activeAllocation ? 0.30 : 0.20)} 0%, ${alphaColor(activeAllocation?.color ?? '#8ea5ff', activeAllocation ? 0.14 : 0.10)} 42%, rgba(20,24,34,0) 78%)`,
                    }}
                  />
                  <div className="relative flex h-[108px] w-[108px] flex-col items-center justify-center">
                    {activeAllocation ? (
                      <>
                        <span className="relative z-10 w-[82px] text-center text-[10px] font-medium leading-snug text-ledger-text-faint break-words">
                          {allocationView === 'type' ? formatSecurityType(activeAllocation.type) : activeAllocation.type}
                        </span>
                        <span className="relative z-10 mt-[4px] text-[17px] font-bold tabular-nums tracking-tight">
                          ${fmt(activeAllocation.value)}
                        </span>
                        <span className="relative z-10 mt-[2px] text-[9px] font-semibold uppercase tracking-[0.12em] text-ledger-text-faintest">
                          {activeAllocation.pct.toFixed(0)}% of portfolio
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="relative z-10 text-[9px] font-semibold uppercase tracking-[0.14em] text-ledger-text-faintest">
                          Portfolio
                        </span>
                        <span className="relative z-10 mt-[4px] text-[16px] font-bold tabular-nums tracking-tight">
                          ${fmt(summary?.total_value ?? 0)}
                        </span>
                        <span className="relative z-10 mt-[2px] text-[9px] font-medium text-ledger-text-faint">
                          Total value
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="absolute right-0 top-0 flex w-[206px] max-h-[252px] flex-col gap-[12px] items-stretch overflow-y-auto pr-1">
                {allocationData.map((slice, i) => (
                  <div
                    key={slice.type}
                    className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-[12px] px-3 py-[9px] min-h-[42px] cursor-default transition-all ${
                      activeSlice === i ? 'border' : 'border border-transparent'
                    }`}
                    style={{
                      opacity: activeSlice === null || activeSlice === i ? 1 : 0.62,
                      borderColor: activeSlice === i ? alphaColor(slice.color, 0.36) : 'transparent',
                      background: activeSlice === i
                        ? `linear-gradient(135deg, ${alphaColor(slice.color, 0.24)} 0%, ${alphaColor(slice.color, 0.12)} 52%, rgba(255,255,255,0.04) 100%)`
                        : 'transparent',
                      boxShadow: activeSlice === i
                        ? `inset 0 1px 0 rgba(255,255,255,0.12), 0 0 20px ${alphaColor(slice.color, 0.12)}`
                        : 'none',
                    }}
                    onMouseEnter={() => setActiveSlice(i)}
                    onMouseLeave={() => setActiveSlice(null)}
                  >
                    <div className="min-w-0">
                      <div
                        className={`min-w-0 truncate text-[12.5px] leading-tight transition-colors ${activeSlice === i ? 'font-semibold' : 'font-medium text-ledger-text-secondary'}`}
                        style={activeSlice === i ? { color: slice.color } : undefined}
                      >
                        {allocationView === 'type' ? formatSecurityType(slice.type) : slice.type}
                      </div>
                      <div className="text-[10px] text-ledger-text-faint tabular-nums mt-[2px]">
                        {slice.pct.toFixed(0)}% of portfolio
                      </div>
                    </div>
                    <span
                      className={`text-[11px] tabular-nums font-semibold ${activeSlice === i ? '' : 'text-ledger-text-faint'}`}
                      style={activeSlice === i ? { color: slice.color } : undefined}
                    >
                      ${fmt(slice.value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Risk & performance */}
      {!riskLoading && risk && risk.data_points >= 5 && (
        <div className="glass-card p-4">
          <div className="flex items-start justify-between mb-2.5">
            <div>
              <div className="text-[13px] font-semibold">Risk & performance</div>
              <div className="text-[11px] text-ledger-text-faint mt-[2px]">
                Trailing {risk.lookback_days} days · time-weighted return basis · risk-free rate {risk.risk_free_rate_pct.toFixed(2)}%
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 md:grid-cols-6 gap-2.5 mb-3">
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Volatility</div>
              <div className="text-[15px] font-bold tabular-nums mt-0.5">{fmtPct(risk.volatility_pct)}</div>
            </div>
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Portfolio Sharpe</div>
              <div className="text-[15px] font-bold tabular-nums mt-0.5">{risk.sharpe_ratio === null ? '—' : risk.sharpe_ratio.toFixed(2)}</div>
            </div>
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Max drawdown</div>
              <div className={`text-[15px] font-bold tabular-nums mt-0.5 ${risk.max_drawdown_pct !== null && risk.max_drawdown_pct < 0 ? 'text-ledger-negative' : ''}`}>
                {fmtPct(risk.max_drawdown_pct)}
              </div>
            </div>
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">VaR (95%, 1d)</div>
              <div className="text-[15px] font-bold tabular-nums mt-0.5">{fmtPct(risk.var_95_pct)}</div>
            </div>
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Beta vs. SPY</div>
              <div className="text-[15px] font-bold tabular-nums mt-0.5">{risk.beta_vs_spy === null ? '—' : risk.beta_vs_spy.toFixed(2)}</div>
            </div>
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">CAGR</div>
              <div className={`text-[15px] font-bold tabular-nums mt-0.5 ${risk.cagr_pct !== null ? (risk.cagr_pct >= 0 ? 'text-ledger-positive' : 'text-ledger-negative') : ''}`}>
                {fmtPct(risk.cagr_pct)}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5 mb-3">
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Time-weighted return</div>
              <div className="text-[13px] font-semibold tabular-nums mt-0.5">{fmtPct(risk.twr_pct)}</div>
              <div className="text-[10px] text-ledger-text-faint mt-0.5">Strategy performance, excludes deposit/withdrawal timing</div>
            </div>
            <div className="glass-chip px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-semibold text-ledger-text-faintest">Money-weighted return (XIRR)</div>
              <div className="text-[13px] font-semibold tabular-nums mt-0.5">{fmtPct(risk.mwr_pct)}</div>
              <div className="text-[10px] text-ledger-text-faint mt-0.5">What you actually earned, includes your deposit/withdrawal timing</div>
            </div>
          </div>

          <div className="text-[10px] text-ledger-text-faint">
            Portfolio Sharpe is time-weighted return on total account equity (includes cash drag). It won't match the "Current Sharpe" below, which covers held tickers only.
          </div>
        </div>
      )}

      {/* Suggested allocation — depends only on Holding + MarketPrice data (populated
          after the first nightly sync), not on the BalanceSnapshot history the risk
          card above needs, so it's gated independently rather than nested inside it.
          There is exactly one optimizer engine (Black-Litterman); the preferences
          panel's toggle turns its output on/off entirely rather than choosing between
          engines. The panel itself (which owns that toggle) always renders here so
          it's reachable from a cold start. Settings/constraint edits inside the panel
          persist immediately but do NOT recompute a suggestion by themselves -- only
          the panel's own "Run optimization" button (onRun below) does, via
          handleRunOptimization.

          Toggle OFF: just the (collapsed) settings card, full width -- no second
          column, since there's nothing to show there yet. Toggle ON: grows into two
          side-by-side halves -- settings (left, self-contained height via its own
          internal scroll on the sector grid) and the frontier chart or a "run it"
          placeholder (right) -- so configuring and seeing the result read as one
          glance rather than a long vertical scroll. The detail tables (objective
          comparison, per-objective suggested weights, clip-log) run full-width below
          both, since they're read top-to-bottom rather than side-by-side with
          anything. */}
      {!optimizationLoading && optimization && (
        optimizationPrefs?.advanced_enabled ? (
          <div className="grid grid-cols-2 gap-3 items-stretch">
            <OptimizationPreferencesPanel
              prefs={optimizationPrefs}
              updatePrefs={updateOptimizationPrefs}
              onRun={handleRunOptimization}
              running={runningOptimization}
            />
            {showOptimizationResults && optimization.insufficient_data && (
              <div className="glass-card p-4 flex items-center justify-center text-center text-[12px] text-ledger-text-faint">
                Not enough price history yet to run the optimizer. This needs at least 30 days
                of overlapping synced price data across your held tickers.
              </div>
            )}
            {showOptimizationResults && !optimization.insufficient_data && (
              <div className="glass-card p-4 flex flex-col">
                <div className="text-[15px] font-semibold mb-1">Efficient frontier</div>
                <div className="text-[12px] text-ledger-text-secondary mb-3 leading-snug">
                  The line shows the best return possible at each level of risk, given your
                  position cap ({optimization.position_cap_pct.toFixed(0)}%) and sector limits.
                  The two markers are the portfolios suggested below. The faint dots are
                  thousands of random portfolios shown only for comparison. They ignore your
                  limits, so they're not suggestions, just a sense of scale.
                </div>
                <div className="flex-1 min-h-0">
                  <EfficientFrontierChart
                    frontierPoints={optimization.frontier_points ?? []}
                    markers={buildMarkers(optimization.objectives)}
                    randomPortfolios={optimization.random_portfolios ?? []}
                  />
                </div>
              </div>
            )}
            {!showOptimizationResults && (
              <div className="glass-card p-4 flex items-center justify-center text-center text-[12px] text-ledger-text-faint">
                Click "Run optimization" to see the efficient frontier.
              </div>
            )}
          </div>
        ) : (
          <OptimizationPreferencesPanel
            prefs={optimizationPrefs}
            updatePrefs={updateOptimizationPrefs}
            onRun={handleRunOptimization}
            running={runningOptimization}
          />
        )
      )}
      {showOptimizationResults && !optimization?.insufficient_data && optimization && (
        <div className="glass-card p-4">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="text-[12px] font-semibold">Suggested allocation</div>
            {optimization.objectives.length > 1 && (
              <div className="flex gap-[5px] shrink-0">
                {optimization.objectives.map(o => (
                  <button
                    key={o.name}
                    onClick={() => setSelectedObjective(o.name)}
                    className={`text-[11.5px] px-[8px] py-[3px] rounded-[6px] font-semibold transition-all ${
                      (activeObjective?.name ?? optimization.objectives[0].name) === o.name
                        ? 'bg-ledger-accent text-ledger-accent-on'
                        : 'glass-chip text-ledger-text-faint hover:text-ledger-text-primary'
                    }`}
                  >
                    {OBJECTIVE_LABELS[o.name] ?? o.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Minimal v1 surfacing of auto-adjusted constraints -- full clip-log
              UI polish (e.g. per-entry dismissal, linking back to the offending
              constraint row in the panel above) is an explicit follow-up. */}
          {(optimization.cap_relaxed || optimization.clip_log.length > 0) && (
            <div className="mb-3">
              <div className="flex items-center gap-[6px] text-[12px] font-semibold text-ledger-warning">
                <AlertTriangle className="w-[13px] h-[13px] flex-shrink-0" strokeWidth={2} />
                Some constraints were auto-adjusted
              </div>
              <ul className="mt-[6px] space-y-[4px]">
                {optimization.cap_relaxed && (
                  <li className="text-[11.5px] text-ledger-text-secondary leading-snug">
                    Position cap relaxed from {((optimization.cap_relaxed.requested_cap ?? 0) * 100).toFixed(1)}% to {((optimization.cap_relaxed.relaxed_to ?? 0) * 100).toFixed(1)}%
                    {optimization.cap_relaxed.reason ? ` (${optimization.cap_relaxed.reason})` : ''}
                  </li>
                )}
                {/* ClipLogEntry is a union-by-optional-fields shape: a
                    sector-floor clip fills sector/requested_floor/clipped_to,
                    while the solver-level notes (risk-aversion substitution,
                    a non-convergent objective solve) carry only a
                    human-readable `reason`. Branch on which one this is --
                    rendering a reason-only entry through the floor-clip
                    template printed "Unknown sector floor clipped from 0.0%
                    to 0.0% — not achievable within the position cap", which
                    is simply false. */}
                {optimization.clip_log.map((entry, i) => (
                  <li key={i} className="text-[11.5px] text-ledger-text-secondary leading-snug">
                    {entry.sector !== null && entry.sector !== undefined
                      ? `${entry.sector} floor clipped from ${((entry.requested_floor ?? 0) * 100).toFixed(1)}% to ${((entry.clipped_to ?? 0) * 100).toFixed(1)}% — not achievable within the position cap`
                      : entry.reason ?? 'A constraint was auto-adjusted'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Mirrors the "Risk & performance" card's glass-chip stat-tile pattern
              above, rather than a plain HTML table -- same numbers deserve the
              same visual language elsewhere on this exact page. Each tile pairs
              its headline value with a colored delta badge (reusing the ArrowUp/
              ArrowDown + tinted-pill pattern from the portfolio-value header)
              instead of a bare "X% → Y%" string. */}
          {activeObjective && (
            <>
              <div className="space-y-3 mb-4">
                <div className="grid grid-cols-3 gap-2.5">
                  <StatTile
                    label="Expected return" value={fmtPct(activeObjective.expected_return_pct)}
                    delta={deltaPp(optimization.current_expected_return_pct, activeObjective.expected_return_pct)} deltaGoodDirection="up"
                  />
                  <StatTile
                    label="Volatility" value={fmtPct(activeObjective.volatility_pct)}
                    delta={deltaPp(optimization.current_volatility_pct, activeObjective.volatility_pct)} deltaGoodDirection="down"
                  />
                  <StatTile
                    label="Sharpe" value={activeObjective.sharpe?.toFixed(2) ?? '—'}
                    delta={deltaRaw(optimization.current_sharpe, activeObjective.sharpe)} deltaGoodDirection="up"
                  />
                </div>
              </div>

              <div>
                <div className="text-[11px] font-semibold text-ledger-text-faint uppercase tracking-wide mb-1.5">
                  {OBJECTIVE_LABELS[activeObjective.name] ?? activeObjective.name} suggested weights
                </div>
                {/* Plain Current/Suggested columns, not a weight bar -- a bar's
                    fill+tick only encodes the two values as relative
                    positions on a track, which reads as "some blue and a
                    white line" rather than telling you anything concrete.
                    Sorted by signed change (suggested minus current), so the
                    list reads as one line from biggest cut to biggest add. */}
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-left text-ledger-text-faint">
                      <th className="font-medium pb-1.5">Ticker</th>
                      <th className="font-medium pb-1.5 text-right">Current</th>
                      <th className="font-medium pb-1.5 text-right">Suggested</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...activeObjective.tickers]
                      .sort(
                        (a, b) =>
                          (a.suggested_weight_pct - a.current_weight_pct) -
                          (b.suggested_weight_pct - b.current_weight_pct),
                      )
                      .map(t => (
                        <tr key={t.ticker} className="border-t border-ledger-border-subtle/50">
                          <td className="py-1.5 font-medium">{t.ticker}</td>
                          <td className="py-1.5 text-right tabular-nums text-ledger-text-faint">
                            ${fmt(t.current_dollar)} ({t.current_weight_pct.toFixed(1)}%)
                          </td>
                          <td className="py-1.5 text-right tabular-nums font-semibold">
                            ${fmt(t.suggested_dollar)} ({t.suggested_weight_pct.toFixed(1)}%)
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* Per-account holdings */}
      {!holdingsLoading && accounts.map(account => (
        <div key={account.id} className="glass-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-ledger-border-subtle">
            <div>
              <div className="text-[13px] font-semibold">{account.name}</div>
              <div className="text-[11px] text-ledger-text-faint">
                {account.institution_name ?? 'Unknown institution'}{account.subtype ? ` · ${account.subtype}` : ''}
              </div>
            </div>
            <div className="text-[15px] font-bold tabular-nums">${fmt(account.total_value)}</div>
          </div>

          {account.positions.length === 0 ? (
            <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">No positions in this account</div>
          ) : (
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-ledger-text-faintest border-b border-ledger-border-subtle">
                  <th className="text-left font-semibold px-4 py-2">Ticker</th>
                  <th className="text-left font-semibold px-2 py-2">Name</th>
                  <th className="text-right font-semibold px-2 py-2">Qty</th>
                  <th className="text-right font-semibold px-2 py-2">Price</th>
                  <th className="text-right font-semibold px-2 py-2">Value</th>
                  <th className="text-right font-semibold px-4 py-2">Gain</th>
                </tr>
              </thead>
              <tbody>
                {account.positions.map((p, i) => (
                  <tr key={i} className="border-b border-ledger-border-subtle last:border-0">
                    <td className="px-4 py-2 font-semibold">{p.ticker ?? '—'}</td>
                    <td className="px-2 py-2 text-ledger-text-secondary truncate max-w-[220px]">{p.name ?? '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.quantity.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.price !== null ? `$${fmt(p.price)}` : '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums font-medium">${fmt(p.value)}</td>
                    <td className={`px-4 py-2 text-right tabular-nums ${p.gain !== null ? (p.gain >= 0 ? 'text-ledger-positive' : 'text-ledger-negative') : 'text-ledger-text-faint'}`}>
                      {p.gain !== null ? `${p.gain >= 0 ? '+' : '−'}$${fmt(Math.abs(p.gain))}${p.gain_pct !== null ? ` (${p.gain_pct.toFixed(1)}%)` : ''}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}

      {/* Recent activity */}
      <div className="glass-card overflow-hidden">
        <div className="px-4 py-2.5 border-b border-ledger-border-subtle flex items-center justify-between gap-3">
          <div>
            <div className="text-[13px] font-semibold">Recent activity</div>
            <div className="text-[10px] text-ledger-text-faint mt-[2px]">Last {historyMonths} months</div>
          </div>
          {!txnsLoading && transactions.length > 4 && (
            <button
              onClick={() => setActivityExpanded(expanded => !expanded)}
              className="text-[11px] font-semibold text-ledger-text-secondary hover:text-ledger-text-primary transition-colors"
            >
              {activityExpanded ? 'Collapse' : `Show all (${transactions.length})`}
            </button>
          )}
        </div>
        {txnsLoading ? (
          <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">Loading…</div>
        ) : transactions.length === 0 ? (
          <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">No investment activity in the last {historyMonths} months</div>
        ) : (
          visibleTransactions.map(t => (
            <div key={t.id} className="flex items-center gap-3 px-4 py-[8px] border-b border-ledger-border-subtle last:border-0">
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-semibold truncate leading-tight">
                  {t.name}{t.ticker ? ` · ${t.ticker}` : ''}
                </div>
                <div className="text-[10px] text-ledger-text-faint leading-tight">
                  {t.account_name} · {formatActivityDate(t.date)}
                </div>
              </div>
              <span className="text-[9.5px] px-[6px] py-[1px] rounded-[5px] glass-chip text-ledger-text-secondary whitespace-nowrap capitalize">
                {t.type}
              </span>
              <span className={`text-[12px] font-semibold w-[88px] text-right tabular-nums flex-shrink-0 ${t.amount < 0 ? 'text-ledger-positive' : ''}`}>
                {t.amount < 0 ? '+' : '−'}${fmt(Math.abs(t.amount))}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
