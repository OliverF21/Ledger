import { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowUp, ArrowDown, ChevronDown } from 'lucide-react'
import { AreaChart, Area, PieChart, Pie, Cell, Sector, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../api/client'
import { useAnalytics, type CategorySpend } from '../hooks/useAnalytics'
import { useOnSyncComplete } from '../hooks/useSync'
import AlertsPanel from '../components/AlertsPanel'
import { formatCategory, formatTransactionCategory, transactionDisplayIcon } from '../utils/categories'
import { getMonthOptions, resolveSelectedMonth, storeMonth, setMonthInUrl, getMonthFromUrl, formatMonthLabel } from '../utils/months'
import { alphaColor, mixHex } from '../utils/color'
import { groupAssetAccounts, type AssetGroup, type AssetAccount } from '../utils/accountGroups'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function lerp(start: number, end: number, progress: number) {
  return start + (end - start) * progress
}

function easeOutCubic(progress: number) {
  return 1 - Math.pow(1 - progress, 3)
}

function buildAnimatedSpendFrame(
  startData: CategorySpend[],
  targetData: CategorySpend[],
  progress: number,
) {
  const startMap = new Map(startData.map(item => [item.name, item]))
  const targetMap = new Map(targetData.map(item => [item.name, item]))
  const orderedNames = [
    ...targetData.map(item => item.name),
    ...startData.map(item => item.name).filter(name => !targetMap.has(name)),
  ]

  return orderedNames
    .map(name => {
      const startItem = startMap.get(name)
      const targetItem = targetMap.get(name)
      const startValue = startItem?.value ?? 0
      const targetValue = targetItem?.value ?? 0
      const value = lerp(startValue, targetValue, progress)

      return {
        name,
        value,
        color: targetItem?.color ?? startItem?.color ?? '#8ea5ff',
      }
    })
    .filter(item => item.value > 0.5 || targetMap.has(item.name))
}

interface ActiveSpendingShapeProps {
  cx: number
  cy: number
  innerRadius: number
  outerRadius: number
  startAngle: number
  endAngle: number
  fill: string
  payload?: { color?: string }
}

function renderActiveSpendingShape(rawProps: unknown) {
  const props = rawProps as ActiveSpendingShapeProps
  return (
    <Sector
      {...props}
      outerRadius={props.outerRadius + 4}
      style={{ outline: 'none' }}
    />
  )
}

interface AccountBreakdown {
  id: number
  name: string
  type: string
  subtype: string | null
  balance: number
  is_liability: boolean
}

interface NetWorthData {
  current_net_worth: number
  total_assets: number
  total_liabilities: number
  accounts: AccountBreakdown[]
  snapshots: { date: string; total: number }[]
  change_amount: number
  change_pct: number
}

function useNetWorth(months: number, refresh = 0) {
  const [data, setData] = useState<NetWorthData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/analytics/net-worth?months=${months}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [months, refresh])

  return { data, loading }
}

const OVERVIEW_MONTH_KEY = 'ledger:overview-month-v2'

interface OverviewProps {
  onNavigate: (screen: 'transactions' | 'budgets') => void
}

interface BudgetItem {
  id: number
  category: string
  limit: number
  spent: number
  color: string
  virtual?: boolean
}

interface BudgetsData {
  month: string
  budgets: BudgetItem[]
  total_limit: number
  total_spent: number
}

function useBudgets(month: string, refresh = 0) {
  const [data, setData] = useState<BudgetsData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/budgets?month=${month}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [month, refresh])

  return { data, loading }
}

interface EnrichedTransaction {
  id: number
  merchant: string
  account_name: string | null
  date: string
  amount: number
  merchant_logo_url?: string | null
  category_user?: string | null
  category_plaid?: string | null
  category_plaid_detailed?: string | null
}

function useRecentTransactions(month: string, limit = 5, refresh = 0) {
  const [transactions, setTransactions] = useState<EnrichedTransaction[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/transactions?limit=${limit}&month=${month}&exclude_hidden=true`)
      .then(r => r.json())
      .then(d => setTransactions(d.transactions ?? []))
      .catch(() => setTransactions([]))
      .finally(() => setLoading(false))
  }, [month, limit, refresh])

  return { transactions, loading }
}

function txnInitials(merchant: string, amount: number) {
  if (amount < 0) return '+'
  const words = (merchant || '').split(' ')
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return '??'
}

function formatChartDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatTxnDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  if (d.getTime() === today.getTime()) return 'Today'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: d.getFullYear() !== today.getFullYear() ? 'numeric' : undefined })
}

function AssetGroupDropdown({
  group,
  label,
  accounts,
  total,
  expanded,
  onToggle,
}: {
  group: AssetGroup
  label: string
  accounts: AssetAccount[]
  total: number
  expanded: boolean
  onToggle: (group: AssetGroup) => void
}) {
  return (
    <div>
      <button
        type="button"
        onClick={() => onToggle(group)}
        className="w-full flex items-center justify-between gap-2 text-[11.5px] leading-tight rounded-[6px] px-[2px] py-[1px] -mx-[2px] hover:bg-white/[0.03] transition-colors"
      >
        <span className="flex items-center gap-[4px] min-w-0 text-ledger-text-secondary">
          <ChevronDown
            className={`w-[11px] h-[11px] flex-shrink-0 text-ledger-text-faint transition-transform ${expanded ? 'rotate-180' : ''}`}
            strokeWidth={2.2}
          />
          <span className="truncate">{label}</span>
          <span className="text-[10px] text-ledger-text-faintest flex-shrink-0">({accounts.length})</span>
        </span>
        <span className="text-ledger-text-primary tabular-nums font-medium flex-shrink-0">${fmt(total)}</span>
      </button>
      {expanded && (
        <div className="mt-[3px] ml-[15px] flex flex-col gap-[3px]">
          {accounts.map(account => (
            <div key={account.id} className="flex justify-between text-[11px] leading-tight">
              <span className="text-ledger-text-faint truncate pr-2">{account.name}</span>
              <span className="text-ledger-text-secondary tabular-nums flex-shrink-0">${fmt(account.balance)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Overview({ onNavigate }: OverviewProps) {
  const [timeRange, setTimeRange] = useState<'6M' | '1Y'>('6M')
  const monthOptions = getMonthOptions(6)
  const [selectedMonth, setSelectedMonth] = useState<string>(() =>
    resolveSelectedMonth(OVERVIEW_MONTH_KEY, getMonthOptions(6)),
  )
  const [hoveredSlice, setHoveredSlice] = useState<number | null>(null)
  const [selectedSlice, setSelectedSlice] = useState<number | null>(null)
  const [hoveredNetWorth, setHoveredNetWorth] = useState<{ date: string; value: number } | null>(null)
  const [expandedAssetGroups, setExpandedAssetGroups] = useState<Set<AssetGroup>>(() => new Set())
  const [syncRefresh, setSyncRefresh] = useState(0)
  useOnSyncComplete(useCallback(() => setSyncRefresh(n => n + 1), []))

  const selectMonth = (month: string) => {
    setSelectedMonth(month)
    storeMonth(OVERVIEW_MONTH_KEY, month)
    setMonthInUrl(month)
    setSelectedSlice(null)
    setHoveredSlice(null)
  }

  useEffect(() => {
    if (getMonthFromUrl() !== selectedMonth) {
      setMonthInUrl(selectedMonth)
      storeMonth(OVERVIEW_MONTH_KEY, selectedMonth)
    }
  }, [selectedMonth])
  const spendingChartRef = useRef<HTMLDivElement | null>(null)
  const spendAnimationFrameRef = useRef<number | null>(null)
  const spendAnimationInitializedRef = useRef(false)
  const { data, loading } = useAnalytics(selectedMonth)
  const { transactions: recentTxns, loading: recentLoading } = useRecentTransactions(selectedMonth, 5, syncRefresh)
  const { data: budgetData, loading: budgetLoading } = useBudgets(selectedMonth, syncRefresh)
  const { data: nwData, loading: nwLoading } = useNetWorth(timeRange === '6M' ? 6 : 12, syncRefresh)
  const [animatedSpendData, setAnimatedSpendData] = useState<CategorySpend[]>([])
  const [animatedSpendTotal, setAnimatedSpendTotal] = useState<number | null>(null)
  const activeSlice = selectedSlice ?? hoveredSlice

  useEffect(() => {
    function handleDocumentMouseDown(event: MouseEvent) {
      if (!spendingChartRef.current?.contains(event.target as Node)) {
        setSelectedSlice(null)
        setHoveredSlice(null)
      }
    }

    document.addEventListener('mousedown', handleDocumentMouseDown)
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown)
  }, [])

  useEffect(() => {
    return () => {
      if (spendAnimationFrameRef.current !== null) {
        cancelAnimationFrame(spendAnimationFrameRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!data) return

    const targetSpendData = data.spending_by_category
    const currentSpendData = animatedSpendData
    const currentSpendTotal = animatedSpendTotal ?? 0

    if (spendAnimationFrameRef.current !== null) {
      cancelAnimationFrame(spendAnimationFrameRef.current)
    }

    if (!spendAnimationInitializedRef.current) {
      setAnimatedSpendData(targetSpendData)
      setAnimatedSpendTotal(data.total_spending)
      spendAnimationInitializedRef.current = true
      return
    }

    const start = performance.now()
    const duration = 420

    const animate = (now: number) => {
      const rawProgress = Math.min((now - start) / duration, 1)
      const easedProgress = easeOutCubic(rawProgress)

      setAnimatedSpendData(buildAnimatedSpendFrame(currentSpendData, targetSpendData, easedProgress))
      setAnimatedSpendTotal(lerp(currentSpendTotal, data.total_spending, easedProgress))

      if (rawProgress < 1) {
        spendAnimationFrameRef.current = requestAnimationFrame(animate)
      } else {
        setAnimatedSpendData(targetSpendData)
        setAnimatedSpendTotal(data.total_spending)
        spendAnimationFrameRef.current = null
      }
    }

    spendAnimationFrameRef.current = requestAnimationFrame(animate)
  }, [data])

  const spendingChange = data && data.prev_month_spending > 0
    ? ((data.total_spending - data.prev_month_spending) / data.prev_month_spending * 100)
    : null

  const monthLabel = selectedMonth ? formatMonthLabel(selectedMonth) : '—'

  const totalSpendingLabel = data ? `$${fmt(data.total_spending)}` : '—'
  const totalIncomeLabel = data ? `$${fmt(data.total_income)}` : '—'
  const savingsRateLabel = data ? `${data.savings_rate.toFixed(0)}%` : '—'
  const spendingChartData = spendAnimationInitializedRef.current
    ? animatedSpendData
    : (data?.spending_by_category ?? [])
  const spendingChartTotal = spendAnimationInitializedRef.current
    ? (animatedSpendTotal ?? 0)
    : (data?.total_spending ?? 0)
  const activeCategory = activeSlice !== null ? spendingChartData[activeSlice] ?? null : null
  const activeCategoryShare = activeCategory && spendingChartTotal > 0
    ? (activeCategory.value / spendingChartTotal) * 100
    : null
  const monthRefreshing = loading || recentLoading || budgetLoading

  const budgetPct = budgetData && budgetData.total_limit > 0
    ? (budgetData.total_spent / budgetData.total_limit) * 100
    : null
  const budgetOver = budgetData ? budgetData.total_spent > budgetData.total_limit : false
  const sortedBudgetItems = budgetData
    ? [...budgetData.budgets].sort((a, b) => {
        const aPct = a.limit > 0 ? (a.spent / a.limit) * 100 : 0
        const bPct = b.limit > 0 ? (b.spent / b.limit) * 100 : 0

        if (bPct !== aPct) return bPct - aPct
        if (b.spent !== a.spent) return b.spent - a.spent
        return a.category.localeCompare(b.category)
      })
    : []
  const assetAccounts = nwData?.accounts.filter(account => !account.is_liability) ?? []
  const assetGroups = groupAssetAccounts(assetAccounts)

  const toggleAssetGroup = (group: AssetGroup) => {
    setExpandedAssetGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  return (
    <div className="min-h-full flex flex-col gap-3 min-w-0">
      <AlertsPanel />

      {/* Row 1: Net Worth + Spending by Category */}
      <div className="grid grid-cols-[2fr_1.4fr] gap-3 min-w-0 items-stretch shrink-0">
        {/* Net Worth Card */}
        <div className="glass-card p-3 short:p-3.5 tall:p-4 min-w-0 min-h-0 overflow-hidden flex flex-col">
          <div className="flex justify-between items-start">
            <div>
              <div className="text-[12px] text-ledger-text-faint font-medium">
                {hoveredNetWorth ? formatChartDate(hoveredNetWorth.date) : 'Net Worth'}
              </div>
              <div className="text-[26px] short:text-[24px] tall:text-[28px] font-bold letter-spacing-[-0.02em] mt-[2px] tabular-nums leading-tight">
                {nwLoading ? '—' : `$${fmt(hoveredNetWorth ? hoveredNetWorth.value : nwData?.current_net_worth ?? 0)}`}
              </div>
              {!nwLoading && nwData && nwData.snapshots.length >= 2 && nwData.change_amount !== 0 && (
                <div className={`flex items-center gap-[6px] mt-[4px] transition-opacity ${hoveredNetWorth ? 'opacity-0' : 'opacity-100'}`}>
                  {nwData.change_pct !== 0 && (
                    <span className={`inline-flex items-center gap-[3px] text-[11.5px] font-semibold px-[6px] py-[2px] rounded-[6px] ${
                      nwData.change_pct >= 0
                        ? 'bg-[rgba(78,195,138,0.13)] text-ledger-positive'
                        : 'bg-[rgba(231,112,95,0.13)] text-ledger-negative'
                    }`}>
                      {nwData.change_pct >= 0
                        ? <ArrowUp className="w-[11px] h-[11px]" strokeWidth={2.5} />
                        : <ArrowDown className="w-[11px] h-[11px]" strokeWidth={2.5} />}
                      {Math.abs(nwData.change_pct).toFixed(1)}%
                    </span>
                  )}
                  <span className={`text-[12px] tabular-nums font-semibold ${nwData.change_amount >= 0 ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
                    {nwData.change_amount >= 0 ? '+' : '−'}${fmt(Math.abs(nwData.change_amount))}
                  </span>
                  <span className="text-[12px] text-ledger-text-faint">this period</span>
                </div>
              )}
            </div>
            <div className="flex gap-[5px]">
              {(['6M', '1Y'] as const).map(r => (
                <button
                  key={r}
                  onClick={() => setTimeRange(r)}
                  className={`text-[11.5px] px-[8px] py-[3px] rounded-[6px] font-semibold transition-all ${
                    timeRange === r
                      ? 'bg-ledger-accent text-ledger-accent-on'
                      : 'glass-chip text-ledger-text-faint hover:text-ledger-text-primary'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-[8px] short:mt-[6px] h-[clamp(56px,9vh,100px)] shrink-0">
            {nwLoading ? (
              <div className="h-full flex items-center justify-center text-[12.5px] text-ledger-text-faintest">Loading…</div>
            ) : nwData && nwData.snapshots.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={nwData.snapshots.map(s => ({ date: s.date, value: s.total }))}
                  onMouseMove={(state: any) => {
                    const point = state?.activePayload?.[0]?.payload
                    if (state?.isTooltipActive && point) {
                      setHoveredNetWorth({ date: point.date, value: point.value })
                    }
                  }}
                  onMouseLeave={() => setHoveredNetWorth(null)}
                >
                  <defs>
                    <linearGradient id="colorNetWorth" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#5b8def" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#5b8def" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="0" stroke="#0d0f14" horizontal={false} vertical={false} />
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={['auto', 'auto']} />
                  <Tooltip
                    content={() => null}
                    cursor={{ stroke: '#5b8def', strokeWidth: 1, strokeDasharray: '3 3' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#5b8def"
                    strokeWidth={2.5}
                    fill="url(#colorNetWorth)"
                    dot={nwData.snapshots.length === 1}
                    activeDot={{ r: 4, fill: '#5b8def', stroke: '#0d0f14', strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-[12.5px] text-ledger-text-faintest">
                No accounts linked
              </div>
            )}
          </div>

          {/* Assets / Liabilities — totals + account names, no nested scroll */}
          {!nwLoading && nwData && nwData.accounts.length > 0 && (
            <div className="mt-2 short:mt-1.5 pt-2 short:pt-1.5 grid grid-cols-2 gap-x-3 short:gap-x-2 flex-1 min-h-0 overflow-y-auto soft-scrollbar">
              {/* Assets column */}
              <div>
                <div className="text-[10px] text-ledger-text-faintest uppercase font-semibold tracking-wide mb-[4px]">Assets</div>
                <div className="flex flex-col gap-[5px]">
                  {assetGroups.map(entry => (
                    <AssetGroupDropdown
                      key={entry.group}
                      group={entry.group}
                      label={entry.label}
                      accounts={entry.accounts}
                      total={entry.total}
                      expanded={expandedAssetGroups.has(entry.group)}
                      onToggle={toggleAssetGroup}
                    />
                  ))}
                </div>
                <div className="flex justify-between text-[11px] mt-[4px] pt-[4px] border-t border-ledger-border-subtle/50">
                  <span className="text-ledger-text-faint">Total</span>
                  <span className="text-ledger-positive tabular-nums font-semibold">${fmt(nwData.total_assets)}</span>
                </div>
              </div>

              {/* Liabilities column */}
              <div>
                <div className="text-[10px] text-ledger-text-faintest uppercase font-semibold tracking-wide mb-[4px]">Liabilities</div>
                {nwData.accounts.filter(a => a.is_liability).length === 0 ? (
                  <div className="text-[11px] text-ledger-text-faintest italic">None</div>
                ) : (
                  <div className="flex flex-col gap-[3px]">
                    {nwData.accounts.filter(a => a.is_liability).map(a => (
                      <div key={a.id} className="flex justify-between text-[11.5px] leading-tight">
                        <span className="text-ledger-text-secondary truncate pr-2">{a.name}</span>
                        <span className="text-ledger-negative tabular-nums font-medium flex-shrink-0">−${fmt(a.balance)}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex justify-between text-[11px] mt-[4px] pt-[4px] border-t border-ledger-border-subtle/50">
                  <span className="text-ledger-text-faint">Total</span>
                  <span className="text-ledger-negative tabular-nums font-semibold">−${fmt(nwData.total_liabilities)}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Spending by Category Donut */}
        <div
          ref={spendingChartRef}
          className="glass-card p-4 min-w-0 h-full grid grid-cols-[200px_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 overflow-hidden"
        >
          <div className="col-span-2 flex items-center justify-between gap-3">
            <div className="text-[13px] text-ledger-text-faint font-medium">Spending by Category</div>
            <div className="flex items-center gap-2 shrink-0">
              {monthRefreshing && data && (
                <span className="text-[10px] uppercase tracking-[0.14em] text-ledger-text-faintest">
                  Updating
                </span>
              )}
              <select
                value={selectedMonth}
                onChange={e => selectMonth(e.target.value)}
                className="text-[11.5px] glass-chip px-[7px] py-[3px] text-ledger-text-primary cursor-pointer outline-none"
              >
                {monthOptions.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          {loading && !data ? (
            <div className="col-span-2 flex items-center justify-center text-ledger-text-faint text-[13px] min-h-[210px]">Loading…</div>
          ) : !data || (spendingChartData.length === 0 && data.spending_by_category.length === 0) ? (
            <div className="col-span-2 flex items-center justify-center text-ledger-text-faint text-[12px] min-h-[210px]">No expense data</div>
          ) : (
            <>
            <div
              className={`relative h-[200px] w-[200px] self-center transition-opacity duration-200 ${loading ? 'opacity-80' : 'opacity-100'}`}
              onClick={event => {
                const target = event.target as Element | null
                if (target?.closest('[data-spending-legend-item="true"]') || target?.closest('.recharts-pie-sector')) {
                  return
                }
                setSelectedSlice(null)
                setHoveredSlice(null)
              }}
            >
                <div
                  className="absolute left-1/2 top-1/2 h-[196px] w-[196px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[28px] pointer-events-none"
                  style={{
                    background: `radial-gradient(circle, ${alphaColor(activeCategory?.color ?? '#8ea5ff', activeCategory ? 0.28 : 0.16)} 0%, ${alphaColor(activeCategory?.color ?? '#8ea5ff', activeCategory ? 0.18 : 0.10)} 28%, ${alphaColor(activeCategory?.color ?? '#8ea5ff', 0.08)} 54%, transparent 82%)`,
                  }}
                />
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <defs>
                      {spendingChartData.map((entry, i) => (
                        <radialGradient
                          id={`overview-spending-slice-${i}`}
                          key={entry.name}
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
                      data={spendingChartData}
                      cx="50%" cy="50%"
                      innerRadius={64} outerRadius={92}
                      paddingAngle={1}
                      dataKey="value"
                      activeIndex={activeSlice ?? undefined}
                      activeShape={renderActiveSpendingShape}
                      isAnimationActive={false}
                      onMouseEnter={(_, i) => {
                        if (selectedSlice === null) setHoveredSlice(i)
                      }}
                      onMouseLeave={() => setHoveredSlice(null)}
                      onClick={(_, i) => {
                        setSelectedSlice(i)
                        setHoveredSlice(i)
                      }}
                      style={{ outline: 'none' }}
                    >
                      {spendingChartData.map((entry, i) => (
                        <Cell
                          key={entry.name}
                          fill={`url(#overview-spending-slice-${i})`}
                          stroke={activeSlice === i ? alphaColor(entry.color, 0.34) : 'rgba(255,255,255,0.06)'}
                          strokeWidth={activeSlice === i ? 0.9 : 0.4}
                          style={{
                            outline: 'none',
                            cursor: 'pointer',
                            filter: activeSlice === i ? `drop-shadow(0 0 12px ${alphaColor(entry.color, 0.22)})` : undefined,
                          }}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                {/* Center label — updates on hover */}
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <div
                    className="absolute left-1/2 top-1/2 h-[168px] w-[168px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[18px]"
                    style={{
                      background: `radial-gradient(circle, ${alphaColor(activeCategory?.color ?? '#8ea5ff', activeCategory ? 0.42 : 0.28)} 0%, ${alphaColor(activeCategory?.color ?? '#8ea5ff', activeCategory ? 0.30 : 0.18)} 18%, rgba(54,60,92,0.24) 34%, rgba(26,30,44,0.10) 56%, rgba(18,21,30,0.04) 72%, rgba(18,21,30,0) 100%)`,
                    }}
                  />
                  <div
                    className="absolute left-1/2 top-1/2 h-[112px] w-[112px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[10px]"
                    style={{
                      background: `radial-gradient(circle, ${alphaColor(activeCategory?.color ?? '#8ea5ff', activeCategory ? 0.30 : 0.20)} 0%, ${alphaColor(activeCategory?.color ?? '#8ea5ff', activeCategory ? 0.14 : 0.10)} 42%, rgba(20,24,34,0) 78%)`,
                    }}
                  />
                  <div className="relative flex h-[88px] w-[88px] flex-col items-center justify-center">
                    {activeCategory ? (
                      <>
                        <span className="relative z-10 w-[72px] text-center text-[9.5px] font-medium leading-snug text-ledger-text-faint break-words">
                          {formatCategory(activeCategory.name)}
                        </span>
                        <span className="relative z-10 mt-[3px] text-[15px] font-bold tabular-nums tracking-tight">
                          ${fmt(activeCategory.value)}
                        </span>
                        {activeCategoryShare !== null && (
                          <span className="relative z-10 mt-[2px] text-[8.5px] font-semibold uppercase tracking-[0.1em] text-ledger-text-faintest">
                            {activeCategoryShare.toFixed(0)}% of spend
                          </span>
                        )}
                      </>
                    ) : (
                      <>
                        <span className="relative z-10 text-[8.5px] font-semibold uppercase tracking-[0.12em] text-ledger-text-faintest">
                          {monthLabel}
                        </span>
                        <span className="relative z-10 mt-[3px] text-[15px] font-bold tabular-nums tracking-tight">
                          ${fmt(spendingChartTotal)}
                        </span>
                        <span className="relative z-10 mt-[2px] text-[8.5px] font-medium text-ledger-text-faint">
                          Total spent
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Legend — own grid column, below header row */}
              <div className="flex flex-col gap-[6px] min-w-0 min-h-0 self-stretch overflow-y-auto soft-scrollbar">
                {spendingChartData.map((cat, i) => (
                  <div
                    key={cat.name}
                    data-spending-legend-item="true"
                    className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[10px] px-2.5 py-[6px] min-h-[32px] cursor-pointer transition-all hover:opacity-100 ${
                      activeSlice === i ? 'border' : 'border border-transparent'
                    }`}
                    style={{
                      opacity: activeSlice === null || activeSlice === i ? 1 : 0.62,
                      borderColor: activeSlice === i ? alphaColor(cat.color, 0.36) : 'transparent',
                      background: activeSlice === i
                        ? `linear-gradient(135deg, ${alphaColor(cat.color, 0.24)} 0%, ${alphaColor(cat.color, 0.12)} 52%, rgba(255,255,255,0.04) 100%)`
                        : 'transparent',
                      boxShadow: activeSlice === i
                        ? `inset 0 1px 0 rgba(255,255,255,0.12), 0 0 20px ${alphaColor(cat.color, 0.12)}`
                        : 'none',
                    }}
                    onMouseEnter={() => {
                      if (selectedSlice === null) setHoveredSlice(i)
                    }}
                    onMouseLeave={() => setHoveredSlice(null)}
                    onClick={() => {
                      setSelectedSlice(i)
                      setHoveredSlice(i)
                    }}
                  >
                    <div className="min-w-0">
                      <div
                        className={`min-w-0 truncate text-[12px] leading-tight transition-colors ${activeSlice === i ? 'font-semibold' : 'font-medium text-ledger-text-secondary'}`}
                        style={activeSlice === i ? { color: cat.color } : undefined}
                      >
                        {formatCategory(cat.name)}
                      </div>
                    </div>
                    <span
                      className={`text-[11px] tabular-nums font-semibold ${activeSlice === i ? '' : 'text-ledger-text-faint'}`}
                      style={activeSlice === i ? { color: cat.color } : undefined}
                    >
                      ${fmt(cat.value)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Row 2: Monthly overview + transactions (left) | Budget progress (right) */}
      <div className="grid grid-cols-[2fr_1fr] gap-3 items-stretch min-w-0 flex-1 min-h-0">
        {/* Left: KPIs + recent transactions */}
        <div className="glass-card overflow-hidden flex flex-col min-h-0 min-w-0 h-full">
          <div className={`px-4 pt-3.5 pb-3 border-b border-white/10 transition-opacity duration-200 shrink-0 ${loading ? 'opacity-80' : 'opacity-100'}`}>
            <div className="flex items-center justify-between mb-2.5">
              <div className="text-[13px] font-semibold">
                Monthly overview
                <span className="text-ledger-text-faint font-normal ml-2">{monthLabel}</span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2.5">
              <div className="glass-chip px-3 py-2">
                <div className="text-[10px] text-ledger-text-faintest uppercase tracking-wide font-semibold">Spending</div>
                <div className="text-[17px] font-bold mt-[2px] tabular-nums tracking-tight leading-tight">
                  {data ? totalSpendingLabel : '—'}
                </div>
                {spendingChange !== null && (
                  <div className={`text-[10px] mt-[2px] flex items-center gap-[2px] ${spendingChange <= 0 ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
                    {spendingChange <= 0
                      ? <><ArrowDown className="w-[9px] h-[9px]" strokeWidth={2.5} />{Math.abs(spendingChange).toFixed(0)}% vs prior</>
                      : <><ArrowUp className="w-[9px] h-[9px]" strokeWidth={2.5} />{spendingChange.toFixed(0)}% vs prior</>
                    }
                  </div>
                )}
              </div>
              <div className="glass-chip px-3 py-2">
                <div className="text-[10px] text-ledger-text-faintest uppercase tracking-wide font-semibold">Income</div>
                <div className="text-[17px] font-bold mt-[2px] tabular-nums tracking-tight leading-tight">
                  {data ? totalIncomeLabel : '—'}
                </div>
                <div className="text-[10px] text-ledger-text-faint mt-[2px]">
                  {data && data.total_income > 0 ? 'This month' : 'No deposits'}
                </div>
              </div>
              <div className="glass-chip px-3 py-2">
                <div className="text-[10px] text-ledger-text-faintest uppercase tracking-wide font-semibold">Savings rate</div>
                <div className="text-[17px] font-bold mt-[2px] tabular-nums tracking-tight leading-tight">
                  {data ? savingsRateLabel : '—'}
                </div>
                <div className="text-[10px] text-ledger-text-faint mt-[2px] truncate">
                  {data ? (data.savings_rate >= 0 ? 'Income exceeds spending' : 'Over budget') : ''}
                </div>
              </div>
            </div>
          </div>

          <div className="flex justify-between items-center px-4 py-2 shrink-0">
            <span className="text-[13px] font-semibold">Recent transactions</span>
            <button
              onClick={() => onNavigate('transactions')}
              className="text-[12px] text-ledger-accent font-semibold cursor-pointer hover:opacity-80"
            >
              View all
            </button>
          </div>

          <div className="flex flex-col flex-1 min-h-0">
            {recentLoading && recentTxns.length === 0 ? (
              <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">Loading…</div>
            ) : recentTxns.length === 0 ? (
              <div className="px-4 py-4 text-center text-ledger-text-faint text-[12px]">
                No transactions this month. Import a CSV or sync an account.
              </div>
            ) : (
              <div className={`flex flex-col flex-1 transition-opacity duration-200 ${recentLoading ? 'opacity-80' : 'opacity-100'}`}>
                {recentTxns.map(txn => (
                <div key={txn.id} className="flex items-center gap-2.5 px-4 py-[7px] border-t border-white/10 flex-1 min-h-[44px]">
                  {transactionDisplayIcon(txn) ? (
                    <img
                      src={transactionDisplayIcon(txn)!}
                      alt=""
                      className="w-[26px] h-[26px] rounded-[7px] shrink-0 bg-ledger-inset object-contain"
                    />
                  ) : (
                    <div
                      className="w-[26px] h-[26px] rounded-[7px] flex items-center justify-center text-[10.5px] font-bold flex-shrink-0"
                      style={{
                        backgroundColor: txn.amount < 0 ? '#0f2a52' : '#1a1e27',
                        color: txn.amount < 0 ? '#7fb0ff' : '#aeb4bf',
                      }}
                    >
                      {txnInitials(txn.merchant, txn.amount)}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] font-semibold truncate leading-tight">{txn.merchant}</div>
                    <div className="text-[10.5px] text-ledger-text-faint leading-tight">
                      {txn.account_name ?? 'Unknown'} · {formatTxnDate(txn.date)}
                    </div>
                  </div>
                  <span
                    className="text-[10px] px-[6px] py-[1px] rounded-[5px] whitespace-nowrap"
                    style={{
                      backgroundColor: txn.amount < 0 ? 'rgba(78,195,138,0.1)' : '#161a21',
                      color: txn.amount < 0 ? '#4ec38a' : '#9aa0ad',
                      border: txn.amount < 0 ? '1px solid rgba(78,195,138,0.25)' : '1px solid #232834',
                    }}
                  >
                    {formatTransactionCategory(txn)}
                  </span>
                  <span
                    className="text-[12.5px] font-semibold w-[70px] text-right tabular-nums flex-shrink-0"
                    style={{ color: txn.amount < 0 ? '#4ec38a' : undefined }}
                  >
                    {txn.amount < 0 ? '+' : '−'}${Math.abs(txn.amount).toFixed(2)}
                  </span>
                </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: budget progress */}
        <div className="glass-card px-4 py-3.5 flex flex-col min-h-0 min-w-0 h-full">
          <div className="flex justify-between items-center mb-2.5 shrink-0">
            <span className="text-[13px] font-semibold">Budget progress</span>
            <button
              onClick={() => onNavigate('budgets')}
              className="text-[12px] text-ledger-accent font-semibold hover:opacity-80"
            >
              Manage
            </button>
          </div>

          {budgetLoading && !budgetData ? (
            <div className="text-center py-4 text-ledger-text-faint text-[12px]">Loading…</div>
          ) : !budgetData || budgetData.budgets.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-2 py-4 rounded-[8px] border border-dashed border-ledger-border-input">
              <div className="text-[12px] text-ledger-text-secondary mb-1.5">No budgets for {monthLabel}</div>
              <button
                onClick={() => onNavigate('budgets')}
                className="text-[11.5px] text-ledger-accent font-semibold hover:opacity-80"
              >
                Set up budgets →
              </button>
            </div>
          ) : (
            <div className={`flex flex-col flex-1 min-h-0 transition-opacity duration-200 ${budgetLoading ? 'opacity-80' : 'opacity-100'}`}>
              <div className="mb-2.5 pb-2.5 border-b border-white/10 shrink-0">
                <div className="flex justify-between text-[12px] mb-1">
                  <span className="text-ledger-text-secondary">Total</span>
                  <span className="tabular-nums font-semibold">
                    ${fmt(budgetData.total_spent)}
                    <span className="text-ledger-text-faint font-normal"> / ${fmt(budgetData.total_limit)}</span>
                  </span>
                </div>
                <div className="h-[6px] rounded-[3px] bg-ledger-track overflow-hidden">
                  <div
                    className="h-full rounded-[3px] transition-all"
                    style={{
                      width: `${Math.min(budgetPct ?? 0, 100)}%`,
                      backgroundColor: budgetOver ? '#e7705f' : '#5b8def',
                    }}
                  />
                </div>
                <div className={`text-[10px] mt-1 ${budgetOver ? 'text-ledger-negative' : 'text-ledger-text-faint'}`}>
                  {budgetOver
                    ? `$${fmt(budgetData.total_spent - budgetData.total_limit)} over`
                    : `$${fmt(budgetData.total_limit - budgetData.total_spent)} remaining`}
                </div>
              </div>

              <div className="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto justify-evenly">
                {sortedBudgetItems.map(b => {
                  const isVirtual = Boolean(b.virtual)
                  const pct = b.limit > 0 ? (b.spent / b.limit) * 100 : (isVirtual ? 100 : 0)
                  const over = !isVirtual && b.spent > b.limit
                  return (
                    <div key={b.id}>
                      <div className="flex justify-between text-[11.5px] mb-1 leading-tight">
                        <span className="truncate pr-2">{formatCategory(b.category)}</span>
                        <span className="tabular-nums text-ledger-text-muted flex-shrink-0 text-[11px]">
                          {isVirtual ? `$${fmt(b.spent)}` : `$${fmt(b.spent)} / $${fmt(b.limit)}`}
                        </span>
                      </div>
                      <div className="h-[5px] rounded-[3px] bg-ledger-track overflow-hidden">
                        <div
                          className="h-full rounded-[3px]"
                          style={{
                            width: `${Math.min(pct, 100)}%`,
                            backgroundColor: over ? '#e7705f' : b.color,
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
