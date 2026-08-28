import { useState, useMemo, useEffect, type ReactNode } from 'react'
import { RefreshCw, ArrowUp, ArrowDown, AlertTriangle } from 'lucide-react'
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
import {
  Eyebrow, GlassCard, Chip, StatTile, ChangeBadge, Tag, UnitToggle,
  EmptyState, LoadingRow,
} from '../components/ui/primitives'
import { AreaLineChart, Donut, DonutLegend, type AreaLineHover, type DonutSlice } from '../components/ui/charts'
import EfficientFrontierChart, { type ObjectiveMarker } from '../components/EfficientFrontierChart'
import OptimizationPreferencesPanel from '../components/OptimizationPreferencesPanel'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtWhole(n: number) {
  return `$${Math.round(n).toLocaleString('en-US')}`
}

/** Splits a dollar amount so the cents can be set smaller and dimmer than the
 *  dollars, matching Overview's hero figure. */
function splitAmount(value: number): { dollars: string; cents: string } {
  const abs = Math.abs(value)
  const dollars = Math.floor(abs).toLocaleString('en-US')
  const cents = (abs % 1).toFixed(2).slice(1)
  return { dollars: `${value < 0 ? '−' : ''}$${dollars}`, cents }
}

/** Typographic minus (U+2212), matching every other signed figure in the UI —
 *  a hyphen sits too high and too short next to tabular digits. */
function fmtPct(n: number | null): string {
  if (n === null) return '—'
  return `${n < 0 ? '−' : ''}${Math.abs(n).toFixed(2)}%`
}

function formatSecurityType(t: string | null): string {
  if (!t) return 'Other'
  if (t.toLowerCase() === 'etf') return 'ETF'
  return t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' ')
}

function formatActivityDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function deltaPp(current: number | null, suggested: number | null): number | null {
  return current === null || suggested === null ? null : suggested - current
}

function deltaRaw(current: number | null, suggested: number | null | undefined): number | null {
  return current == null || suggested == null ? null : suggested - current
}

function DeltaStatTile({ label, value, delta, deltaGoodDirection }: {
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

function LegendDot({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-[7px] text-[12px] font-semibold text-white/60">
      <span className="w-[9px] h-[9px] rounded-full inline-block border-[1.5px] border-white/70" style={{ background: color }} />
      {children}
    </div>
  )
}

const OPTIMIZATION_LOOKBACK_DAYS = 1095

const OBJECTIVE_LABELS: Record<string, string> = {
  max_sharpe: 'Max Sharpe',
  max_quadratic_utility: 'Max Quadratic Utility',
}

function buildMarkers(optimization: {
  objectives: ObjectiveResponse[]
  current_volatility_pct: number | null
  current_expected_return_pct: number | null
}): ObjectiveMarker[] {
  const colors: Record<string, string> = {
    max_sharpe: '#f4907f',
    max_quadratic_utility: '#e6bd79',
    current: '#adb8cb',
  }
  const markers: ObjectiveMarker[] = optimization.objectives
    .filter(o => o.volatility_pct != null && o.expected_return_pct != null)
    .map(o => ({ name: o.name, volatility_pct: o.volatility_pct!, return_pct: o.expected_return_pct!, color: colors[o.name] ?? '#82a9f2' }))
  if (optimization.current_volatility_pct != null && optimization.current_expected_return_pct != null) {
    markers.push({
      name: 'current',
      volatility_pct: optimization.current_volatility_pct,
      return_pct: optimization.current_expected_return_pct,
      color: colors.current,
    })
  }
  return markers
}


/** One column of the Current / Period change / Range triple beneath the
 *  portfolio figure. Same recipe as Overview's Assets / Liabilities columns. */
function BreakdownColumn({
  label,
  total,
  rows,
  labelWidth = 118,
}: {
  label: string
  total: ReactNode
  rows: { key: string | number; name: string; value: string }[]
  labelWidth?: number
}) {
  return (
    <div className="min-w-0">
      <Eyebrow size="sm">{label}</Eyebrow>
      <div className="mt-1.5 text-[15px] font-bold tracking-[-0.025em]">{total}</div>
      {rows.length > 0 && (
        <div className="mt-2 flex flex-col gap-[3px]">
          {rows.map(row => (
            <div key={row.key} className="flex gap-2.5 text-[11px]">
              <span className="text-ledger-text-faint truncate" style={{ width: labelWidth }}>{row.name}</span>
              <span className="text-white/80 font-medium whitespace-nowrap">{row.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Divider() {
  return (
    <div
      className="w-px self-stretch shrink-0"
      style={{ background: 'linear-gradient(180deg, transparent, rgba(255,255,255,0.14), transparent)' }}
    />
  )
}

/** Keep the hero donut to Overview's ~8-slice density; fold the rest into Other
 *  so the ring still represents the full portfolio. */
function collapseSlices(slices: DonutSlice[], limit = 8): DonutSlice[] {
  if (slices.length <= limit) return slices
  const head = slices.slice(0, limit - 1)
  const rest = slices.slice(limit - 1)
  const otherValue = rest.reduce((sum, slice) => sum + slice.value, 0)
  return [
    ...head,
    { key: '__other', label: 'Other', value: otherValue, color: '#adb8cb' },
  ]
}

/** Donut / legend cycling order from the V2 design tokens. */
const ALLOCATION_PALETTE = [
  '#82a9f2', '#63cfcc', '#e6bd79', '#f4907f',
  '#a196fa', '#adb8cb', '#74d8a8', '#95c8ff',
]

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

/* ── Screen ─────────────────────────────────────────────────────────────── */

export default function Investments() {
  const { data: summary, loading: summaryLoading, refetch: refetchSummary } = useInvestmentsSummary()
  const { accounts, loading: holdingsLoading, refetch: refetchHoldings } = useInvestmentsHoldings()
  const [historyRange, setHistoryRange] = useState<'6M' | '1Y'>('6M')
  const historyMonths = historyRange === '6M' ? 6 : 12
  const lookbackDays = historyRange === '6M' ? 182 : 365
  const { transactions, loading: txnsLoading } = useInvestmentTransactions(historyMonths)
  const { data: history } = useInvestmentsHistory(historyMonths)
  const { data: risk, loading: riskLoading } = useInvestmentsRisk(lookbackDays)
  const { data: optimization, loading: optimizationLoading, refetch: refetchOptimization } = useInvestmentsOptimization(OPTIMIZATION_LOOKBACK_DAYS)
  const { data: optimizationPrefs, update: updateOptimizationPrefs } = useOptimizationPreferences()
  const [allocationView, setAllocationView] = useState<AllocationView>('security')
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const [activityExpanded, setActivityExpanded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [runningOptimization, setRunningOptimization] = useState(false)
  const [selectedObjective, setSelectedObjective] = useState<string>('max_sharpe')
  const [varUnit, setVarUnit] = useState<'pct' | 'dollar'>('pct')
  const [hoverPoint, setHoverPoint] = useState<AreaLineHover | null>(null)

  const handleRunOptimization = async () => {
    setRunningOptimization(true)
    try {
      await refetchOptimization()
    } finally {
      setRunningOptimization(false)
    }
  }

  const showOptimizationResults = Boolean(optimizationPrefs?.advanced_enabled && optimization?.advanced_enabled)

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

  const allocationSlices: DonutSlice[] = useMemo(
    () => allocationData.map((slice, i) => ({
      key: slice.type,
      label: allocationView === 'type' ? formatSecurityType(slice.type) : slice.type,
      value: slice.value,
      // Type allocation arrives pre-coloured from the API; re-key security
      // slices onto the V2 palette so both views share one colour family.
      color: allocationView === 'type'
        ? ALLOCATION_PALETTE[i % ALLOCATION_PALETTE.length]
        : slice.color,
    })),
    [allocationData, allocationView],
  )
  const visibleAllocation = useMemo(
    () => collapseSlices(allocationSlices),
    [allocationSlices],
  )

  useEffect(() => {
    setActiveSlice(null)
  }, [allocationView, allocationData.length])

  useEffect(() => {
    setHoverPoint(null)
  }, [historyRange])

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

  if (!loading && (!summary || summary.account_count === 0)) {
    return (
      <GlassCard className="h-[420px] flex items-center justify-center">
        <EmptyState
          title="No investment accounts linked"
          body="Connect a brokerage account in Settings to see position-level holdings, risk metrics and allocation here."
        />
      </GlassCard>
    )
  }

  const hasHistory = Boolean(history && history.snapshots.length >= 2)
  const growthUp = (history?.change_amount ?? 0) >= 0
  const chartColor = growthUp ? '#74d8a8' : '#f4907f'
  const changeToneColor = growthUp ? '#b6ebcd' : '#f5b3a4'
  const hoverSnap = hoverPoint && history ? history.snapshots[hoverPoint.index] ?? null : null
  const currentValue = history?.snapshots[history.snapshots.length - 1]?.total ?? summary?.total_value ?? 0
  const displayValue = hoverSnap?.total ?? currentValue
  const { dollars, cents } = splitAmount(displayValue)
  const activeAlloc = activeSlice !== null ? visibleAllocation[activeSlice] ?? null : null
  const activeAllocShare = activeAlloc && currentValue > 0
    ? (activeAlloc.value / currentValue) * 100
    : null

  return (
    <div className="flex flex-col gap-4 min-w-0">
      {/* ── Hero: portfolio curve as the section floor, allocation over the fade.
          Same no-card treatment as Overview's net-worth + spending donut. */}
      <section className="relative h-[410px] shrink-0 mt-1.5 overflow-visible pr-14">
        {hasHistory && (
          <AreaLineChart
            values={history!.snapshots.map(s => s.total)}
            color={chartColor}
            width={1180}
            height={300}
            className="absolute top-[50px] z-[1] h-[268px]"
            style={{ left: -18, right: -18, width: 'calc(100% + 36px)' }}
            maskImage="linear-gradient(90deg, #000 0%, #000 44%, rgba(0,0,0,0.25) 58%, transparent 66%)"
            onHover={setHoverPoint}
          />
        )}

        <div className="absolute left-[2px] top-0 z-20 pointer-events-none ledger-rise-fast">
          <Eyebrow className="!tracking-[0.2em] !text-white/40">Portfolio value</Eyebrow>
          <div
            className="mt-2 text-[68px] leading-[0.92] font-bold tracking-[-0.05em]"
            style={{ textShadow: '0 0 46px rgba(200,220,255,0.3)' }}
          >
            {summaryLoading ? '—' : dollars}
            {!summaryLoading && (
              <span className="text-[34px] font-semibold tracking-[-0.025em] text-white/[0.46]">{cents}</span>
            )}
          </div>

          <div className="mt-[13px] flex items-center gap-2.5 whitespace-nowrap">
            {hoverSnap ? (
              <span className="text-[12.5px] text-white/40">{formatActivityDate(hoverSnap.date)}</span>
            ) : (
              <>
                {hasHistory && history!.change_amount !== 0 && (
                  <>
                    <ChangeBadge positive={growthUp}>
                      {Math.abs(history!.change_pct).toFixed(1)}%
                    </ChangeBadge>
                    <span className="text-[12.5px] font-semibold" style={{ color: chartColor }}>
                      {growthUp ? '+' : '−'}${fmt(Math.abs(history!.change_amount))}
                    </span>
                  </>
                )}
                <span className="text-[12.5px] text-white/40">
                  past {historyRange === '6M' ? '6 months' : '12 months'}
                </span>
              </>
            )}
            <span className="w-px h-[13px] bg-white/[0.14]" />
            <div className="flex gap-2.5 text-[11.5px] font-semibold pointer-events-auto">
              {(['6M', '1Y'] as const).map(range => (
                <button
                  key={range}
                  type="button"
                  onClick={() => setHistoryRange(range)}
                  className={historyRange === range ? 'text-white' : 'text-white/[0.36] hover:text-white/85'}
                >
                  {range}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-[5px] text-[11.5px] font-semibold text-white/[0.36] hover:text-white/85 disabled:opacity-60 pointer-events-auto"
            >
              <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} strokeWidth={2} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        <div
          className="absolute left-0 bottom-0 w-[600px] h-[200px] z-10 pointer-events-none"
          style={{
            background:
              'radial-gradient(60% 65% at 20% 100%, rgba(8,11,15,0.92) 0%, rgba(8,11,15,0.6) 45%, rgba(8,11,15,0) 78%)',
          }}
        />

        <div className="absolute left-[2px] bottom-1 z-20 flex items-start gap-[34px] pointer-events-none ledger-fade ledger-delay-1">
          <BreakdownColumn
            label="Current"
            total={`$${fmt(currentValue)}`}
            rows={[
              { key: 'accounts', name: 'Accounts', value: String(summary?.account_count ?? 0) },
              { key: 'positions', name: 'Positions', value: String(summary?.position_count ?? 0) },
            ]}
          />
          <Divider />
          <BreakdownColumn
            label="Period change"
            total={
              <span style={{ color: changeToneColor }}>
                {history ? `${growthUp ? '+' : '−'}$${fmt(Math.abs(history.change_amount))}` : '—'}
              </span>
            }
            labelWidth={72}
            rows={history ? [
              { key: 'pct', name: 'Return', value: `${Math.abs(history.change_pct).toFixed(1)}%` },
              { key: 'range', name: 'Range', value: historyRange === '6M' ? '6 months' : '12 months' },
            ] : []}
          />
          <Divider />
          <BreakdownColumn
            label="Last synced"
            total={
              summary?.last_synced_at
                ? new Date(summary.last_synced_at).toLocaleString('en-US', {
                    month: 'short', day: 'numeric',
                  })
                : '—'
            }
            labelWidth={72}
            rows={summary?.last_synced_at ? [
              {
                key: 'time',
                name: 'Time',
                value: new Date(summary.last_synced_at).toLocaleString('en-US', {
                  hour: 'numeric', minute: '2-digit',
                }),
              },
            ] : []}
          />
        </div>

        {/* `right-14` matches section `pr-14`. Absolute `right-0` ignores that
            padding and clips the donut halo against the page's overflow-x. */}
        <div className="absolute right-14 top-5 z-20 flex items-center gap-5 ledger-rise">
          <div className="flex flex-col items-end gap-px">
            <div className="flex items-center gap-2.5 mb-1.5">
              <Eyebrow size="sm">Allocation</Eyebrow>
              <div className="flex gap-2.5 text-[11.5px] font-semibold">
                {(['security', 'type'] as const).map(view => (
                  <button
                    key={view}
                    type="button"
                    onClick={() => setAllocationView(view)}
                    className={allocationView === view ? 'text-white' : 'text-white/[0.36] hover:text-white/85'}
                  >
                    {view === 'type' ? 'Type' : 'Security'}
                  </button>
                ))}
              </div>
            </div>
            {loading ? (
              <span className="text-[11.5px] text-ledger-text-faint">Loading…</span>
            ) : visibleAllocation.length === 0 ? (
              <span className="text-[11.5px] text-ledger-text-faint">No positions yet</span>
            ) : (
              <DonutLegend
                slices={visibleAllocation}
                activeIndex={activeSlice}
                onHover={setActiveSlice}
                formatValue={fmtWhole}
              />
            )}
          </div>

          <Donut
            slices={visibleAllocation}
            size={258}
            radius={84}
            strokeWidth={24}
            activeIndex={activeSlice}
            onHover={setActiveSlice}
          >
            {activeAlloc ? (
              <>
                <div className="text-[9px] uppercase tracking-[0.18em] font-semibold text-white/[0.38] max-w-[110px] truncate">
                  {activeAlloc.label}
                </div>
                <div className="mt-1 text-[30px] font-bold tracking-[-0.04em]">
                  {fmtWhole(activeAlloc.value)}
                </div>
                {activeAllocShare !== null && (
                  <div className="mt-[3px] text-[10.5px] font-semibold text-white/50">
                    {activeAllocShare.toFixed(0)}% of portfolio
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="text-[9px] uppercase tracking-[0.18em] font-semibold text-white/[0.38]">Portfolio</div>
                <div className="mt-1 text-[30px] font-bold tracking-[-0.04em]">
                  {fmtWhole(summary?.total_value ?? 0)}
                </div>
                <div className="mt-[3px] text-[10.5px] font-medium text-white/[0.44]">Total value</div>
              </>
            )}
          </Donut>
        </div>
      </section>

      {/* ── Risk & performance ─────────────────────────────────────────── */}
      {!riskLoading && risk && risk.data_points >= 5 && (
        <GlassCard className="px-5 py-[18px]">
          <div className="flex items-start justify-between gap-4 mb-3.5">
            <div>
              <div className="text-[13px] font-bold">Risk &amp; performance</div>
              <div className="text-[11px] text-white/[0.44] mt-[3px]">
                Trailing {risk.lookback_days} days · time-weighted return basis · risk-free rate {risk.risk_free_rate_pct.toFixed(2)}%
              </div>
            </div>
          </div>

          <div className="grid grid-cols-5 gap-2.5 mb-3.5">
            <StatTile label="Volatility" value={fmtPct(risk.volatility_pct)} />
            <StatTile label="Portfolio Sharpe" value={risk.sharpe_ratio === null ? '—' : risk.sharpe_ratio.toFixed(2)} />
            <StatTile label="Max drawdown" value={fmtPct(risk.max_drawdown_pct)} tone="negative" />
            <StatTile label="Beta vs. SPY" value={risk.beta_vs_spy === null ? '—' : risk.beta_vs_spy.toFixed(2)} />
            <StatTile
              label="CAGR"
              value={fmtPct(risk.cagr_pct)}
              tone={risk.cagr_pct !== null && risk.cagr_pct < 0 ? 'negative' : 'positive'}
            />
          </div>

          {risk.var_horizons.length > 0 && (
            <Chip className="px-3 py-2.5 mb-3.5">
              <div className="flex items-center justify-between mb-2">
                <Eyebrow size="sm" className="!tracking-[0.14em] !text-white/40">Value at risk (backtest)</Eyebrow>
                <UnitToggle
                  options={[{ value: 'pct', label: '%' }, { value: 'dollar', label: '$' }] as const}
                  value={varUnit}
                  onChange={setVarUnit}
                />
              </div>
              <div className="grid grid-cols-3 text-[12px] text-white/[0.44] pb-1.5">
                <span>Horizon</span>
                <span className="text-right">95%</span>
                <span className="text-right">99%</span>
              </div>
              {risk.var_horizons.map(horizon => (
                <div key={horizon.days} className="grid grid-cols-3 text-[12.5px] py-1 border-t border-white/[0.06]">
                  <span className="text-white/70">{horizon.days}d</span>
                  <span className="text-right font-semibold tabular-nums">
                    {varUnit === 'pct'
                      ? fmtPct(horizon.var_95_pct)
                      : (horizon.var_95_dollar === null ? '—' : `$${fmt(horizon.var_95_dollar)}`)}
                  </span>
                  <span className="text-right font-semibold tabular-nums">
                    {varUnit === 'pct'
                      ? fmtPct(horizon.var_99_pct)
                      : (horizon.var_99_dollar === null ? '—' : `$${fmt(horizon.var_99_dollar)}`)}
                  </span>
                </div>
              ))}
              <div className="text-[10px] text-white/40 mt-2">
                Backtested from current holdings across {risk.var_data_points} days of price history
                {risk.var_coverage_pct !== null && risk.var_coverage_pct < 99.5 && (
                  <> · covers {risk.var_coverage_pct.toFixed(0)}% of portfolio value ({risk.var_excluded_tickers.join(', ')} excluded — no price history)</>
                )}
              </div>
            </Chip>
          )}

          <div className="grid grid-cols-2 gap-2.5 mb-3">
            <StatTile
              label="Time-weighted return"
              value={<span className="text-[13.5px]">{fmtPct(risk.twr_pct)}</span>}
              hint="Strategy performance, excludes deposit/withdrawal timing"
            />
            <StatTile
              label="Money-weighted return (XIRR)"
              value={<span className="text-[13.5px]">{fmtPct(risk.mwr_pct)}</span>}
              hint="What you actually earned, includes your deposit/withdrawal timing"
            />
          </div>

          <div className="text-[10px] text-white/40 leading-relaxed">
            Portfolio Sharpe is time-weighted return on total account equity (includes cash drag). It won&rsquo;t match the
            Sharpe figures below, which cover held tickers only.
          </div>
        </GlassCard>
      )}

      {/* Suggested allocation — Black-Litterman engine on main. */}
      {!optimizationLoading && optimization && (
        optimizationPrefs?.advanced_enabled ? (
          <div className="flex gap-4 items-stretch">
            <OptimizationPreferencesPanel
              className="w-[520px] shrink-0"
              prefs={optimizationPrefs}
              updatePrefs={updateOptimizationPrefs}
              onRun={handleRunOptimization}
              running={runningOptimization}
              heldTickers={optimization.tickers.map(t => t.ticker)}
            />
            <GlassCard className="flex-1 min-w-0 flex flex-col px-6 py-5 max-h-[760px]" overflow="visible">
              <div className="shrink-0">
                <div className="text-[15px] font-bold tracking-[-0.02em]">Efficient frontier</div>
                <div className="text-[12px] text-white/50 mt-2 max-w-[640px] leading-relaxed">
                  The line is the best return available at each level of risk given your position cap ({optimization.position_cap_pct.toFixed(0)}%)
                  and sector limits. The markers are the suggested portfolios. The faint dots are random portfolios
                  shown only for scale — they ignore your limits.
                </div>
              </div>
              <div className="flex items-center gap-[22px] mt-4 shrink-0 flex-wrap">
                <div className="flex items-center gap-[7px] text-[12px] font-semibold text-white/60">
                  <svg width="16" height="10" viewBox="0 0 16 10"><path d="M1 8 L15 2" stroke="#82a9f2" strokeWidth="2" strokeLinecap="round" /></svg>
                  Efficient frontier
                </div>
                <LegendDot color="#f4907f">Max Sharpe</LegendDot>
                <LegendDot color="#e6bd79">Max quadratic utility</LegendDot>
                <LegendDot color="#adb8cb">Current</LegendDot>
              </div>
              {runningOptimization && !showOptimizationResults ? (
                <div className="flex items-center justify-center h-[420px] text-[12.5px] text-ledger-text-faint">
                  Sweeping the frontier…
                </div>
              ) : !showOptimizationResults ? (
                <div className="flex flex-col items-center justify-center text-center px-6 h-[420px]">
                  <div className="text-[14px] font-semibold">Set your constraints, then run</div>
                  <div className="mt-1.5 text-[12.5px] text-ledger-text-faint max-w-[380px] leading-relaxed">
                    The frontier is a constrained sweep, so it runs on demand rather than on every slider move.
                  </div>
                </div>
              ) : optimization.insufficient_data ? (
                <div className="flex flex-col items-center justify-center text-center px-6 h-[420px]">
                  <div className="text-[14px] font-semibold">Not enough price history</div>
                  <div className="mt-1.5 text-[12.5px] text-ledger-text-faint max-w-[380px] leading-relaxed">
                    The optimizer needs at least 30 days of daily closes across two or more priced holdings.
                  </div>
                </div>
              ) : (
                <>
                  <EfficientFrontierChart
                    frontierPoints={optimization.frontier_points ?? []}
                    markers={buildMarkers(optimization)}
                    randomPortfolios={optimization.random_portfolios ?? []}
                  />
                  <div className="grid grid-cols-3 gap-2.5 mt-3 shrink-0">
                    {[
                      { label: 'Current', ret: optimization.current_expected_return_pct, vol: optimization.current_volatility_pct, sharpe: optimization.current_sharpe },
                      { label: 'Max Sharpe', ret: optimization.objectives.find(o => o.name === 'max_sharpe')?.expected_return_pct ?? null, vol: optimization.objectives.find(o => o.name === 'max_sharpe')?.volatility_pct ?? null, sharpe: optimization.objectives.find(o => o.name === 'max_sharpe')?.sharpe ?? null },
                      { label: 'Max utility', ret: optimization.objectives.find(o => o.name === 'max_quadratic_utility')?.expected_return_pct ?? null, vol: optimization.objectives.find(o => o.name === 'max_quadratic_utility')?.volatility_pct ?? null, sharpe: optimization.objectives.find(o => o.name === 'max_quadratic_utility')?.sharpe ?? null },
                    ].map(({ label, ret, vol, sharpe }) => (
                      <div key={label} className="glass-chip px-3 py-2">
                        <div className="text-[9.5px] uppercase tracking-[0.14em] font-semibold text-white/40">{label}</div>
                        <div className="mt-1 text-[13px] font-bold tabular-nums">
                          {ret != null && vol != null ? `${ret.toFixed(1)}% / ${vol.toFixed(1)}%` : '—'}
                        </div>
                        <div className="mt-0.5 text-[10px] text-white/40">
                          return / vol{sharpe != null ? ` · Sharpe ${sharpe.toFixed(2)}` : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </GlassCard>
          </div>
        ) : (
          <OptimizationPreferencesPanel
            prefs={optimizationPrefs}
            updatePrefs={updateOptimizationPrefs}
            onRun={handleRunOptimization}
            running={runningOptimization}
            heldTickers={optimization.tickers.map(t => t.ticker)}
          />
        )
      )}
      {showOptimizationResults && !optimization?.insufficient_data && optimization && (
        <GlassCard className="px-5 py-[18px]">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="text-[13px] font-bold">Suggested allocation</div>
            {optimization.objectives.length > 1 && (
              <div className="flex gap-[5px] shrink-0">
                {optimization.objectives.map(o => (
                  <button
                    key={o.name}
                    type="button"
                    onClick={() => setSelectedObjective(o.name)}
                    className={`text-[11.5px] px-[8px] py-[3px] rounded-[6px] font-semibold transition-all ${
                      (activeObjective?.name ?? optimization.objectives[0].name) === o.name
                        ? 'bg-white text-ledger-accent-on'
                        : 'glass-chip text-ledger-text-faint hover:text-ledger-text-primary'
                    }`}
                  >
                    {OBJECTIVE_LABELS[o.name] ?? o.name}
                  </button>
                ))}
              </div>
            )}
          </div>

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
                {optimization.clip_log.map((entry, i) => (
                  <li key={i} className="text-[11.5px] text-ledger-text-secondary leading-snug">
                    {entry.sector && entry.requested_floor != null
                      ? `${entry.sector} floor clipped from ${(entry.requested_floor * 100).toFixed(1)}% to ${((entry.clipped_to ?? 0) * 100).toFixed(1)}% — not achievable within the position cap`
                      : entry.reason ?? 'A constraint was auto-adjusted'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {activeObjective && (
            <>
              <div className="space-y-3 mb-4">
                <div className="grid grid-cols-3 gap-2.5">
                  <DeltaStatTile
                    label="Expected return" value={fmtPct(activeObjective.expected_return_pct)}
                    delta={deltaPp(optimization.current_expected_return_pct, activeObjective.expected_return_pct)} deltaGoodDirection="up"
                  />
                  <DeltaStatTile
                    label="Volatility" value={fmtPct(activeObjective.volatility_pct)}
                    delta={deltaPp(optimization.current_volatility_pct, activeObjective.volatility_pct)} deltaGoodDirection="down"
                  />
                  <DeltaStatTile
                    label="Sharpe" value={activeObjective.sharpe?.toFixed(2) ?? '—'}
                    delta={deltaRaw(optimization.current_sharpe, activeObjective.sharpe)} deltaGoodDirection="up"
                  />
                </div>
              </div>

              <div>
                <div className="text-[11px] font-semibold text-ledger-text-faint uppercase tracking-wide mb-1.5">
                  {OBJECTIVE_LABELS[activeObjective.name] ?? activeObjective.name} suggested weights
                </div>
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
        </GlassCard>
      )}

      {/* ── Per-account holdings ───────────────────────────────────────── */}
      {!holdingsLoading && accounts.map(account => (
        <GlassCard key={account.id} className="flex flex-col">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/10">
            <div className="min-w-0">
              <div className="text-[13px] font-bold truncate">{account.name}</div>
              <div className="text-[11px] text-white/[0.44] mt-0.5 truncate">
                {account.institution_name ?? 'Unknown institution'}{account.subtype ? ` · ${account.subtype}` : ''}
              </div>
            </div>
            <div className="text-[15px] font-bold shrink-0">${fmt(account.total_value)}</div>
          </div>

          {account.positions.length === 0 ? (
            <EmptyState title="No positions in this account" />
          ) : (
            <div className="overflow-x-auto soft-scrollbar">
              <div className="min-w-[860px]">
                <div className="grid grid-cols-[80px_minmax(0,1fr)_90px_110px_120px_190px] text-[10px] uppercase tracking-[0.1em] text-white/[0.36] font-bold px-5 py-2.5 border-b border-white/[0.08]">
                  <span>Ticker</span>
                  <span>Name</span>
                  <span className="text-right">Qty</span>
                  <span className="text-right">Price</span>
                  <span className="text-right">Value</span>
                  <span className="text-right">Gain</span>
                </div>
                {account.positions.map((position, i) => (
                  <div
                    key={`${position.ticker ?? position.name ?? 'row'}-${i}`}
                    className="grid grid-cols-[80px_minmax(0,1fr)_90px_110px_120px_190px] text-[12.5px] px-5 py-[9px] border-b border-white/[0.06] last:border-0 row-hover-soft"
                  >
                    <span className="font-bold">{position.ticker ?? '—'}</span>
                    <span className="text-white/70 truncate pr-3">{position.name ?? '—'}</span>
                    <span className="text-right tabular-nums">
                      {position.quantity.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                    </span>
                    <span className="text-right tabular-nums">
                      {position.price !== null ? `$${fmt(position.price)}` : '—'}
                    </span>
                    <span className="text-right tabular-nums font-medium">${fmt(position.value)}</span>
                    <span
                      className="text-right tabular-nums font-semibold whitespace-nowrap pl-3"
                      style={{
                        color: position.gain === null
                          ? 'rgba(255,255,255,0.46)'
                          : position.gain >= 0 ? '#b6ebcd' : '#f5b3a4',
                      }}
                    >
                      {position.gain === null ? '—' : (
                        <>
                          {position.gain >= 0 ? '+' : '−'}${fmt(Math.abs(position.gain))}
                          {position.gain_pct !== null && (
                            <span className="ml-1.5 font-medium opacity-60">
                              {position.gain_pct >= 0 ? '+' : '−'}{Math.abs(position.gain_pct).toFixed(1)}%
                            </span>
                          )}
                        </>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </GlassCard>
      ))}

      {/* ── Recent activity ────────────────────────────────────────────── */}
      <GlassCard className="flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <div>
            <div className="text-[13px] font-bold">Recent activity</div>
            <div className="text-[10px] text-white/[0.44] mt-0.5">Last {historyMonths} months</div>
          </div>
          {!txnsLoading && transactions.length > 4 && (
            <button
              type="button"
              onClick={() => setActivityExpanded(expanded => !expanded)}
              className="text-[11px] font-bold text-white/70 hover:text-white"
            >
              {activityExpanded ? 'Collapse' : `Show all (${transactions.length})`}
            </button>
          )}
        </div>

        {txnsLoading ? (
          <LoadingRow />
        ) : transactions.length === 0 ? (
          <EmptyState title={`No investment activity in the last ${historyMonths} months`} />
        ) : (
          visibleTransactions.map(txn => (
            <div
              key={txn.id}
              className="flex items-center gap-3 px-5 py-[9px] border-b border-white/[0.06] last:border-0 row-hover-soft"
            >
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-semibold truncate">
                  {txn.name}{txn.ticker ? ` · ${txn.ticker}` : ''}
                </div>
                <div className="text-[10px] text-white/[0.44] mt-px truncate">
                  {txn.account_name} · {formatActivityDate(txn.date)}
                </div>
              </div>
              <Tag className="capitalize">{txn.type}</Tag>
              <span
                className="text-[12px] font-bold w-[90px] text-right tabular-nums shrink-0"
                style={txn.amount < 0 ? { color: '#b6ebcd' } : undefined}
              >
                {txn.amount < 0 ? '+' : '−'}${fmt(Math.abs(txn.amount))}
              </span>
            </div>
          ))
        )}
      </GlassCard>
    </div>
  )
}
