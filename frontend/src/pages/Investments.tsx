import { useState, useMemo, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
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
import {
  Eyebrow, GlassCard, Chip, StatTile, ChangeBadge, Tag, SegmentedToggle, UnitToggle, Switch,
  EmptyState, LoadingRow, ProgressBar,
} from '../components/ui/primitives'
import { AreaLineChart, Donut, DonutLegend, type DonutSlice } from '../components/ui/charts'
import OptimizerPanel from '../components/ui/OptimizerPanel'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtWhole(n: number) {
  return `$${Math.round(n).toLocaleString('en-US')}`
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
  const { transactions, loading: txnsLoading } = useInvestmentTransactions(6)
  const [historyRange, setHistoryRange] = useState<'6M' | '1Y'>('6M')
  const { data: history, loading: historyLoading } = useInvestmentsHistory(historyRange === '6M' ? 6 : 12)
  const { data: risk, loading: riskLoading } = useInvestmentsRisk(365)
  const { data: optimization, loading: optimizationLoading } = useInvestmentsOptimization(365)
  const [allocationView, setAllocationView] = useState<AllocationView>('security')
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const [activityExpanded, setActivityExpanded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [varUnit, setVarUnit] = useState<'pct' | 'dollar'>('pct')
  const [advancedOpen, setAdvancedOpen] = useState(false)

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

  useEffect(() => {
    setActiveSlice(null)
  }, [allocationView, allocationData.length])

  const visibleTransactions = activityExpanded ? transactions : transactions.slice(0, 4)

  // The GET summary carries no sectors (classifying them costs a provider call
  // per ticker), so the panel starts with none and fills them in from its own
  // first run.
  const optimizerSectors = optimization?.sectors ?? []

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
  const currentValue = history?.snapshots[history.snapshots.length - 1]?.total ?? summary?.total_value ?? 0

  return (
    <div className="flex flex-col gap-4 min-w-0">
      {/* ── Portfolio value + allocation ───────────────────────────────── */}
      <div className="grid grid-cols-[1.85fr_1.15fr] gap-4 items-stretch">
        <GlassCard className="flex flex-col px-[22px] pt-5 pb-[18px]">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <Eyebrow className="!text-white/40">Portfolio value</Eyebrow>
              <div
                /* See Overview's hero: tabular-nums pads the thousands comma. */
                className="mt-2 text-[44px] leading-[0.95] font-bold tracking-[-0.04em]"
                style={{ textShadow: '0 0 40px rgba(200,220,255,0.28)' }}
              >
                ${fmt(currentValue)}
              </div>
              <div className="mt-2.5 flex items-center gap-[9px] whitespace-nowrap">
                {hasHistory && history!.change_amount !== 0 && (
                  <>
                    <ChangeBadge positive={growthUp}>{Math.abs(history!.change_pct).toFixed(1)}%</ChangeBadge>
                    <span className="text-[12px] font-semibold" style={{ color: changeToneColor }}>
                      {growthUp ? '+' : '−'}${fmt(Math.abs(history!.change_amount))}
                    </span>
                  </>
                )}
                <span className="text-[11.5px] text-white/40">past {historyRange}</span>
              </div>
              <div className="mt-1 text-[10.5px] text-white/[0.36]">
                {summary?.account_count ?? 0} accounts · {summary?.position_count ?? 0} positions
                {summary?.last_synced_at && (
                  <> · Last synced {new Date(summary.last_synced_at).toLocaleString('en-US', {
                    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                  })}</>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2.5 shrink-0">
              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshing}
                className="flex items-center gap-[5px] text-[11.5px] font-semibold px-[9px] py-1 rounded-[8px] text-white/[0.68] bg-white/[0.07] border border-white/[0.13] hover:text-white disabled:opacity-60"
              >
                <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} strokeWidth={2} />
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
              <SegmentedToggle
                options={[{ value: '6M', label: '6M' }, { value: '1Y', label: '1Y' }] as const}
                value={historyRange}
                onChange={setHistoryRange}
              />
            </div>
          </div>

          {/* Chart bleeds to the card's edges — the curve is the card's floor,
              not a framed object sitting inside it. */}
          <div className="relative h-[180px] shrink-0 mt-3.5 -mx-[22px]">
            {historyLoading ? (
              <LoadingRow className="h-full" />
            ) : !hasHistory ? (
              <div className="h-full flex items-center justify-center text-[12.5px] text-ledger-text-faint">
                No history yet — snapshots build up after your first few syncs
              </div>
            ) : (
              <AreaLineChart
                values={history!.snapshots.map(s => s.total)}
                color={chartColor}
                width={940}
                height={180}
                padding={16}
                className="absolute inset-0 w-full h-full"
                maskImage="linear-gradient(90deg, #000 0%, #000 78%, rgba(0,0,0,0.25) 88%, transparent 96%)"
              />
            )}
          </div>

          <div className="grid grid-cols-3 gap-2.5 mt-2 pt-3.5 border-t border-white/10">
            <div>
              <Eyebrow size="sm">Current</Eyebrow>
              <div className="mt-1 text-[16px] font-bold tracking-[-0.02em] tabular-nums">${fmt(currentValue)}</div>
            </div>
            <div>
              <Eyebrow size="sm">Period change</Eyebrow>
              <div className="mt-1 text-[16px] font-bold tracking-[-0.02em] tabular-nums" style={{ color: changeToneColor }}>
                {history ? `${growthUp ? '+' : '−'}$${fmt(Math.abs(history.change_amount))}` : '—'}
              </div>
            </div>
            <div>
              <Eyebrow size="sm">Range</Eyebrow>
              <div className="mt-1 text-[16px] font-bold tracking-[-0.02em]">{historyRange}</div>
            </div>
          </div>
        </GlassCard>

        <GlassCard className="flex flex-col px-5 py-[18px]">
          <div className="flex items-start justify-between gap-3 mb-1.5">
            <div>
              <div className="text-[13px] font-bold">Allocation</div>
              <div className="text-[11px] text-white/[0.44] mt-[3px]">
                {allocationView === 'type' ? 'By security type' : 'By security'}
              </div>
            </div>
            <SegmentedToggle
              options={[{ value: 'security', label: 'Security' }, { value: 'type', label: 'Type' }] as const}
              value={allocationView}
              onChange={setAllocationView}
            />
          </div>

          {loading ? (
            <LoadingRow className="flex-1" />
          ) : allocationSlices.length === 0 ? (
            <EmptyState className="flex-1" title="No positions yet" />
          ) : (
            <div className="relative flex-1 flex flex-col items-center justify-center gap-3 mt-1">
              <Donut
                slices={allocationSlices}
                size={210}
                radius={82}
                strokeWidth={22}
                activeIndex={activeSlice}
                onHover={setActiveSlice}
              >
                {activeSlice !== null && allocationSlices[activeSlice] ? (
                  <>
                    <div className="text-[9px] uppercase tracking-[0.18em] font-semibold text-white/[0.38] max-w-[100px] truncate">
                      {allocationSlices[activeSlice].label}
                    </div>
                    <div className="mt-1 text-[26px] font-bold tracking-[-0.04em] tabular-nums">
                      {fmtWhole(allocationSlices[activeSlice].value)}
                    </div>
                    <div className="mt-[3px] text-[10px] font-medium text-white/[0.44]">
                      {allocationData[activeSlice]?.pct.toFixed(1)}% of portfolio
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-[9px] uppercase tracking-[0.18em] font-semibold text-white/[0.38]">Portfolio</div>
                    <div className="mt-1 text-[26px] font-bold tracking-[-0.04em] tabular-nums">
                      {fmtWhole(summary?.total_value ?? 0)}
                    </div>
                    <div className="mt-[3px] text-[10px] font-medium text-white/[0.44]">Total value</div>
                  </>
                )}
              </Donut>

              <DonutLegend
                className="w-full max-h-[120px] overflow-y-auto soft-scrollbar"
                slices={allocationSlices}
                activeIndex={activeSlice}
                onHover={setActiveSlice}
                formatValue={fmtWhole}
                labelWidth={70}
              />
            </div>
          )}
        </GlassCard>
      </div>

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
            <Switch
              id="advanced-optimization-label"
              label="Advanced optimization"
              checked={advancedOpen}
              onChange={setAdvancedOpen}
            />
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

      {/* ── Advanced optimization ──────────────────────────────────────── */}
      {advancedOpen && (
        <OptimizerPanel
          sectors={optimizerSectors}
          tickers={optimization?.tickers.map(t => t.ticker) ?? []}
        />
      )}

      {/* ── Suggested allocation ───────────────────────────────────────── */}
      {!optimizationLoading && optimization && !optimization.insufficient_data && (
        <GlassCard className="px-5 py-[18px]">
          <div className="text-[13px] font-bold mb-1">Suggested allocation (max Sharpe)</div>
          <div className="text-[11px] text-white/[0.44] mb-3">
            Current Sharpe (holdings only) {optimization.current_sharpe?.toFixed(2) ?? '—'} ·
            Suggested Sharpe (holdings only) {optimization.suggested_sharpe?.toFixed(2) ?? '—'}
          </div>
          <div className="grid grid-cols-[1fr_1fr_1fr_1.4fr] text-[11.5px] text-white/[0.44] pb-2">
            <span>Ticker</span>
            <span className="text-right">Current</span>
            <span className="text-right">Suggested</span>
            <span className="text-right pl-6">Shift</span>
          </div>
          {optimization.tickers.map(ticker => {
            const delta = ticker.suggested_weight_pct - ticker.current_weight_pct
            return (
              <div
                key={ticker.ticker}
                className="grid grid-cols-[1fr_1fr_1fr_1.4fr] items-center text-[12.5px] py-[7px] border-t border-white/[0.08]"
              >
                <span className="font-bold">{ticker.ticker}</span>
                <span className="text-right tabular-nums text-white/70">{ticker.current_weight_pct.toFixed(1)}%</span>
                <span className="text-right tabular-nums font-bold">{ticker.suggested_weight_pct.toFixed(1)}%</span>
                <div className="flex items-center justify-end gap-2.5 pl-6">
                  <div className="w-[120px]">
                    <ProgressBar
                      pct={Math.min(100, Math.abs(delta) * 2)}
                      color={delta >= 0 ? '#74d8a8' : '#f4907f'}
                    />
                  </div>
                  <span
                    className="w-[52px] text-right tabular-nums text-[11.5px] font-semibold"
                    style={{ color: delta >= 0 ? '#b6ebcd' : '#f5b3a4' }}
                  >
                    {delta >= 0 ? '+' : '−'}{Math.abs(delta).toFixed(1)}%
                  </span>
                </div>
              </div>
            )
          })}
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
            <div className="text-[15px] font-bold tabular-nums shrink-0">${fmt(account.total_value)}</div>
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
            <div className="text-[10px] text-white/[0.44] mt-0.5">Last 6 months</div>
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
          <EmptyState title="No investment activity in the last 6 months" />
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
