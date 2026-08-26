import { useState, useMemo, useEffect } from 'react'
import { ArrowUp, ArrowDown, RefreshCw } from 'lucide-react'
import { PieChart, Pie, Cell, Sector, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../api/client'
import {
  useInvestmentsSummary,
  useInvestmentsHoldings,
  useInvestmentsHistory,
  useInvestmentTransactions,
  useInvestmentsRisk,
  useInvestmentsOptimization,
  type AllocationSlice,
} from '../hooks/useInvestments'

import { alphaColor, mixHex } from '../utils/color'
import {
  AXIS_STROKE,
  CATEGORY_PALETTE,
  CHART_ACCENT,
  CHART_SURFACE,
  GRID_STROKE,
  tooltipItemStyle,
  tooltipLabelStyle,
  tooltipStyle,
} from '../utils/chartTheme'

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

function formatActivityDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const ALLOCATION_PALETTE = CATEGORY_PALETTE

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
  const { transactions, loading: txnsLoading } = useInvestmentTransactions(6)
  const [historyRange, setHistoryRange] = useState<'6M' | '1Y'>('6M')
  const { data: history, loading: historyLoading } = useInvestmentsHistory(historyRange === '6M' ? 6 : 12)
  const { data: risk, loading: riskLoading } = useInvestmentsRisk(365)
  const { data: optimization, loading: optimizationLoading } = useInvestmentsOptimization(365)
  const [allocationView, setAllocationView] = useState<AllocationView>('security')
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const [activityExpanded, setActivityExpanded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

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
  const latestValue = history?.snapshots[history.snapshots.length - 1]?.total ?? summary?.total_value ?? 0

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
          <div className="flex items-start justify-between mb-3">
            <div className="min-w-0">
              <div className="metric-label">Portfolio value</div>
              {/* The value is the headline. It used to sit in a stat chip below
                  the chart, at the same weight as the range toggle's own label. */}
              <div className="flex items-baseline gap-2.5 mt-[3px]">
                <span className="text-stat font-bold font-mono text-ledger-text-heading">
                  ${fmt(latestValue)}
                </span>
                {!historyLoading && history && history.snapshots.length >= 2 && history.change_amount !== 0 && (
                  <span className={`text-[12.5px] font-semibold font-mono ${
                    history.change_amount >= 0 ? 'text-ledger-positive' : 'text-ledger-negative'
                  }`}>
                    {history.change_amount >= 0 ? '+' : '−'}${fmt(Math.abs(history.change_amount))}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-ledger-text-faint mt-[3px] truncate">
                {summary?.account_count ?? 0} accounts · {summary?.position_count ?? 0} positions
                {hasAccounts && summary?.last_synced_at && (
                  <> · Last synced {new Date(summary.last_synced_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
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
                      <stop offset="0%" stopColor={CHART_ACCENT} stopOpacity={0.28} />
                      <stop offset="100%" stopColor={CHART_ACCENT} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="0" stroke={GRID_STROKE} horizontal={true} vertical={false} />
                  <XAxis
                    dataKey="date"
                    stroke={AXIS_STROKE}
                    axisLine={false}
                    tickLine={false}
                    style={{ fontSize: '12px' }}
                    tickFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  />
                  <YAxis
                    stroke={AXIS_STROKE}
                    axisLine={false}
                    tickLine={false}
                    style={{ fontSize: '12px' }}
                    tickFormatter={v => `$${fmt(v)}`}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={tooltipLabelStyle}
                    itemStyle={tooltipItemStyle}
                    labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    formatter={(val: number) => [`$${fmt(val)}`, 'Value']}
                  />
                  <Area type="monotone" dataKey="total" stroke={CHART_ACCENT} strokeWidth={2.5} fill="url(#investmentHistoryFill)" dot={history.snapshots.length === 1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

        </div>

        {/* Allocation donut — matches overview visual language */}
        <div className="glass-card p-4 flex flex-col">
          <div className="flex items-start justify-between gap-3 mb-[2px]">
            <div>
              <div className="text-title font-semibold">Allocation</div>
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
                          <stop offset="100%" stopColor={mixHex(entry.color, CHART_SURFACE.bg, 0.12)} stopOpacity={0.88} />
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
                        <span className="relative z-10 mt-[4px] text-[17px] font-bold font-mono tracking-tight">
                          ${fmt(activeAllocation.value)}
                        </span>
                        <span className="relative z-10 mt-[2px] text-[9px] font-semibold uppercase tracking-caps text-ledger-text-faintest">
                          {activeAllocation.pct.toFixed(0)}% of portfolio
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="relative z-10 text-[9px] font-semibold uppercase tracking-caps text-ledger-text-faintest">
                          Portfolio
                        </span>
                        <span className="relative z-10 mt-[4px] text-[16px] font-bold font-mono tracking-tight">
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
                      <div className="text-[10.5px] text-ledger-text-faint font-mono mt-[2px]">
                        {slice.pct.toFixed(0)}% of portfolio
                      </div>
                    </div>
                    <span
                      className={`text-[11.5px] font-mono font-semibold ${activeSlice === i ? '' : 'text-ledger-text-muted'}`}
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
              <div className="text-title font-semibold">Risk & performance</div>
              <div className="text-[11px] text-ledger-text-faint mt-[2px]">
                Trailing {risk.lookback_days} days · time-weighted return basis · risk-free rate {risk.risk_free_rate_pct.toFixed(2)}%
              </div>
            </div>
          </div>

          {/* The two returns are the headline of this card, so they carry the
              larger type. They previously rendered smaller than the six risk
              stats below, which inverted the hierarchy. */}
          <div className="grid grid-cols-2 gap-3 mb-3">
            {[
              {
                label: 'Time-weighted return',
                value: fmtPct(risk.twr_pct),
                raw: risk.twr_pct,
                note: 'Strategy performance, excludes deposit/withdrawal timing',
              },
              {
                label: 'Money-weighted return (XIRR)',
                value: fmtPct(risk.mwr_pct),
                raw: risk.mwr_pct,
                note: 'What you actually earned, includes your deposit/withdrawal timing',
              },
            ].map(item => (
              <div key={item.label} className="inset-panel px-3.5 py-2.5">
                <div className="metric-label">{item.label}</div>
                <div className={`text-[22px] leading-none font-bold font-mono mt-1.5 ${
                  item.raw !== null ? (item.raw >= 0 ? 'text-ledger-positive' : 'text-ledger-negative') : ''
                }`}>
                  {item.value}
                </div>
                <div className="text-[10.5px] text-ledger-text-faint mt-1.5">{item.note}</div>
              </div>
            ))}
          </div>

          {/* Supporting risk stats. A hairline-divided row rather than six
              free-floating tiles: at this density the divider is enough
              structure, and a tile per number gave each one panel weight. */}
          <div className="inset-panel grid grid-cols-3 md:grid-cols-6 overflow-hidden divide-x divide-ledger-border-input">
            {[
              { label: 'Volatility', value: fmtPct(risk.volatility_pct), tone: '' },
              { label: 'Portfolio Sharpe', value: risk.sharpe_ratio === null ? '—' : risk.sharpe_ratio.toFixed(2), tone: '' },
              {
                label: 'Max drawdown',
                value: fmtPct(risk.max_drawdown_pct),
                tone: risk.max_drawdown_pct !== null && risk.max_drawdown_pct < 0 ? 'text-ledger-negative' : '',
              },
              { label: 'VaR (95%, 1d)', value: fmtPct(risk.var_95_pct), tone: '' },
              { label: 'Beta vs. SPY', value: risk.beta_vs_spy === null ? '—' : risk.beta_vs_spy.toFixed(2), tone: '' },
              {
                label: 'CAGR',
                value: fmtPct(risk.cagr_pct),
                tone: risk.cagr_pct !== null ? (risk.cagr_pct >= 0 ? 'text-ledger-positive' : 'text-ledger-negative') : '',
              },
            ].map(stat => (
              <div key={stat.label} className="px-3 py-2.5">
                <div className="metric-label truncate">{stat.label}</div>
                <div className={`text-[15px] font-semibold font-mono mt-1 ${stat.tone}`}>{stat.value}</div>
              </div>
            ))}
          </div>

          <div className="text-[10.5px] text-ledger-text-faint mt-3 max-w-[80ch]">
            Portfolio Sharpe is time-weighted return on total account equity (includes cash drag). It won't match the "Current Sharpe" below, which covers held tickers only.
          </div>
        </div>
      )}

      {/* Suggested allocation — depends only on Holding + MarketPrice data (populated
          after the first nightly sync), not on the BalanceSnapshot history the risk
          card above needs, so it's gated independently rather than nested inside it. */}
      {!optimizationLoading && optimization && !optimization.insufficient_data && (
        <div className="glass-card p-4">
          <div className="text-title font-semibold">Suggested allocation (max Sharpe)</div>
          <div className="text-[11px] text-ledger-text-faint mt-[2px] mb-3">
            Current Sharpe (holdings only) {optimization.current_sharpe?.toFixed(2) ?? '—'} · Suggested Sharpe (holdings only) {optimization.suggested_sharpe?.toFixed(2) ?? '—'}
          </div>
          <table className="w-full max-w-[560px] text-[12.5px]">
            <thead>
              <tr className="border-b border-ledger-border-subtle">
                <th className="metric-label text-left pb-2">Ticker</th>
                <th className="metric-label text-right pb-2">Current</th>
                <th className="metric-label text-right pb-2">Suggested</th>
              </tr>
            </thead>
            <tbody>
              {optimization.tickers.map(t => (
                <tr key={t.ticker} className="border-b border-ledger-border-subtle last:border-0 hover:bg-ledger-hover">
                  <td className="py-[7px] font-semibold font-mono">{t.ticker}</td>
                  <td className="py-[7px] text-right font-mono text-ledger-text-muted">{t.current_weight_pct.toFixed(1)}%</td>
                  <td className="py-[7px] text-right font-mono font-semibold">{t.suggested_weight_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Per-account holdings */}
      {!holdingsLoading && accounts.map(account => (
        <div key={account.id} className="glass-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-ledger-border-subtle">
            <div>
              <div className="text-title font-semibold">{account.name}</div>
              <div className="text-[11px] text-ledger-text-faint">
                {account.institution_name ?? 'Unknown institution'}{account.subtype ? ` · ${account.subtype}` : ''}
              </div>
            </div>
            <div className="text-[16px] font-bold font-mono text-ledger-text-heading">${fmt(account.total_value)}</div>
          </div>

          {account.positions.length === 0 ? (
            <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">No positions in this account</div>
          ) : (
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-ledger-border-subtle">
                  <th className="metric-label text-left px-4 py-2">Ticker</th>
                  <th className="metric-label text-left px-2 py-2">Name</th>
                  <th className="metric-label text-right px-2 py-2">Qty</th>
                  <th className="metric-label text-right px-2 py-2">Price</th>
                  <th className="metric-label text-right px-2 py-2">Value</th>
                  <th className="metric-label text-right px-4 py-2">Gain</th>
                </tr>
              </thead>
              <tbody>
                {account.positions.map((p, i) => (
                  <tr key={i} className="border-b border-ledger-border-subtle last:border-0 hover:bg-ledger-hover">
                    <td className="px-4 py-2 font-semibold font-mono">{p.ticker ?? '—'}</td>
                    <td className="px-2 py-2 text-ledger-text-secondary truncate max-w-[220px]">{p.name ?? '—'}</td>
                    <td className="px-2 py-2 text-right font-mono text-ledger-text-muted">{p.quantity.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
                    <td className="px-2 py-2 text-right font-mono text-ledger-text-muted">{p.price !== null ? `$${fmt(p.price)}` : '—'}</td>
                    <td className="px-2 py-2 text-right font-mono font-medium">${fmt(p.value)}</td>
                    <td className={`px-4 py-2 text-right font-mono ${p.gain !== null ? (p.gain >= 0 ? 'text-ledger-positive' : 'text-ledger-negative') : 'text-ledger-text-faint'}`}>
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
            <div className="text-title font-semibold">Recent activity</div>
            <div className="text-[10px] text-ledger-text-faint mt-[2px]">Last 6 months</div>
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
          <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">No investment activity in the last 6 months</div>
        ) : (
          visibleTransactions.map(t => (
            <div key={t.id} className="flex items-center gap-3 px-4 py-[8px] border-b border-ledger-border-subtle last:border-0 hover:bg-ledger-hover">
              <div className="flex-1 min-w-0">
                <div className="text-[12.5px] font-semibold truncate leading-tight">
                  {t.name}{t.ticker ? ` · ${t.ticker}` : ''}
                </div>
                <div className="text-[10.5px] text-ledger-text-faint leading-tight mt-[1px]">
                  {t.account_name} · {formatActivityDate(t.date)}
                </div>
              </div>
              {/* A flat tint, not the control surface: this badge is a label, and
                  glass-chip now signals something you can click. */}
              <span className="text-[10px] px-[7px] py-[2px] rounded-[5px] bg-ledger-inset border border-ledger-border text-ledger-text-muted whitespace-nowrap capitalize">
                {t.type}
              </span>
              <span className={`text-[12.5px] font-semibold font-mono w-[92px] text-right flex-shrink-0 ${t.amount < 0 ? 'text-ledger-positive' : ''}`}>
                {t.amount < 0 ? '+' : '−'}${fmt(Math.abs(t.amount))}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
