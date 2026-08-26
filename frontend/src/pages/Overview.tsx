import { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowUp, ArrowDown, ChevronDown } from 'lucide-react'
import { AreaChart, Area, PieChart, Pie, Cell, Sector, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../api/client'
import { useAnalytics, type CategorySpend } from '../hooks/useAnalytics'
import { useOnSyncComplete } from '../hooks/useSync'
import AlertsPanel from '../components/AlertsPanel'
import { formatCategory, formatTransactionCategory, transactionDisplayIcon } from '../utils/categories'
import { getMonthOptions, resolveSelectedMonth, storeMonth, setMonthInUrl, getMonthFromUrl, formatMonthLabel } from '../utils/months'
import {
  CHART_ACCENT,
  CHART_NEGATIVE,
  tooltipItemStyle,
  tooltipLabelStyle,
  tooltipStyle,
} from '../utils/chartTheme'
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
    <div className="min-h-full flex flex-col gap-4 min-w-0">
      <AlertsPanel />

      <section className="glass-card px-5 pt-5 pb-4 min-w-0 overflow-hidden">
        <div className="flex justify-between items-start gap-4">
          <div>
            <div className="text-[13px] text-ledger-text-muted font-medium">Net worth</div>
            <div className="text-[40px] short:text-[34px] tall:text-[48px] font-semibold tracking-tightest mt-1 leading-none tabular-nums text-ledger-text-heading">
              {nwLoading ? '—' : `$${fmt(nwData?.current_net_worth ?? 0)}`}
            </div>
            {!nwLoading && nwData && nwData.snapshots.length >= 2 && nwData.change_amount !== 0 && (
              <div className="flex items-center gap-[6px] mt-2">
                {nwData.change_pct !== 0 && (
                  <span className={`inline-flex items-center gap-[3px] text-[12px] font-semibold ${
                    nwData.change_pct >= 0 ? 'text-ledger-positive' : 'text-ledger-negative'
                  }`}>
                    {nwData.change_pct >= 0
                      ? <ArrowUp className="w-[12px] h-[12px]" strokeWidth={2.5} />
                      : <ArrowDown className="w-[12px] h-[12px]" strokeWidth={2.5} />}
                    {Math.abs(nwData.change_pct).toFixed(1)}%
                  </span>
                )}
                <span className={`text-[13px] font-semibold tabular-nums ${nwData.change_amount >= 0 ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
                  {nwData.change_amount >= 0 ? '+' : '−'}${fmt(Math.abs(nwData.change_amount))}
                </span>
                <span className="text-[13px] text-ledger-text-faint">this period</span>
              </div>
            )}
          </div>
          <div className="flex gap-[5px]">
            {(['6M', '1Y'] as const).map(r => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`text-[12px] px-[9px] py-[4px] rounded-[7px] font-medium ${
                  timeRange === r
                    ? 'bg-ledger-accent text-ledger-accent-on'
                    : 'text-ledger-text-faint hover:text-ledger-text-primary hover:bg-ledger-hover'
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 h-[clamp(120px,18vh,176px)]">
          {nwLoading ? (
            <div className="h-full flex items-center justify-center text-[13px] text-ledger-text-faintest">Loading…</div>
          ) : nwData && nwData.snapshots.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={nwData.snapshots.map(s => ({ date: s.date, value: s.total }))}>
                <defs>
                  <linearGradient id="colorNetWorth" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART_ACCENT} stopOpacity={0.18} />
                    <stop offset="100%" stopColor={CHART_ACCENT} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" hide />
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  formatter={(val: number) => [`$${fmt(val)}`, 'Net worth']}
                  cursor={false}
                />
                <Area type="monotone" dataKey="value" stroke={CHART_ACCENT} strokeWidth={2} fill="url(#colorNetWorth)" dot={nwData.snapshots.length === 1} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-[13px] text-ledger-text-faintest">
              No accounts linked
            </div>
          )}
        </div>

        {!nwLoading && nwData && nwData.accounts.length > 0 && (
          <div className="mt-4 pt-4 border-t border-ledger-border-subtle grid grid-cols-2 gap-x-8">
            <div>
              <div className="metric-label mb-2">Assets</div>
              <div className="flex flex-col gap-[6px]">
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
              <div className="flex justify-between text-[12px] mt-2 pt-2 border-t border-ledger-border-subtle">
                <span className="text-ledger-text-faint">Total</span>
                <span className="text-ledger-positive tabular-nums font-semibold">${fmt(nwData.total_assets)}</span>
              </div>
            </div>

            <div>
              <div className="metric-label mb-2">Liabilities</div>
              {nwData.accounts.filter(a => a.is_liability).length === 0 ? (
                <div className="text-[12px] text-ledger-text-faintest">None</div>
              ) : (
                <div className="flex flex-col gap-[6px]">
                  {nwData.accounts.filter(a => a.is_liability).map(a => (
                    <div key={a.id} className="flex justify-between text-[12px] leading-tight">
                      <span className="text-ledger-text-secondary truncate pr-2">{a.name}</span>
                      <span className="text-ledger-negative tabular-nums flex-shrink-0">−${fmt(a.balance)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex justify-between text-[12px] mt-2 pt-2 border-t border-ledger-border-subtle">
                <span className="text-ledger-text-faint">Total</span>
                <span className="text-ledger-negative tabular-nums font-semibold">−${fmt(nwData.total_liabilities)}</span>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className={`glass-card px-5 py-4 grid grid-cols-3 divide-x divide-ledger-border-subtle ${loading ? 'opacity-80' : ''}`}>
        <div className="pr-5">
          <div className="text-[13px] text-ledger-text-muted">Spending</div>
          <div className="text-[22px] font-semibold mt-1 tabular-nums tracking-tight leading-none">
            {data ? totalSpendingLabel : '—'}
          </div>
          {spendingChange !== null && (
            <div className={`text-[12px] mt-1.5 flex items-center gap-1 ${spendingChange <= 0 ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
              {spendingChange <= 0
                ? <><ArrowDown className="w-[11px] h-[11px]" strokeWidth={2.5} />{Math.abs(spendingChange).toFixed(0)}% vs prior</>
                : <><ArrowUp className="w-[11px] h-[11px]" strokeWidth={2.5} />{spendingChange.toFixed(0)}% vs prior</>
              }
            </div>
          )}
        </div>
        <div className="px-5">
          <div className="text-[13px] text-ledger-text-muted">Income</div>
          <div className="text-[22px] font-semibold mt-1 tabular-nums tracking-tight leading-none text-ledger-positive">
            {data ? totalIncomeLabel : '—'}
          </div>
          <div className="text-[12px] text-ledger-text-faint mt-1.5">
            {data && data.total_income > 0 ? monthLabel : 'No deposits'}
          </div>
        </div>
        <div className="pl-5">
          <div className="text-[13px] text-ledger-text-muted">Savings rate</div>
          <div className="text-[22px] font-semibold mt-1 tabular-nums tracking-tight leading-none">
            {data ? savingsRateLabel : '—'}
          </div>
          <div className="text-[12px] text-ledger-text-faint mt-1.5 truncate">
            {data ? (data.savings_rate >= 0 ? 'Income exceeds spending' : 'Spending exceeds income') : ''}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-[1.15fr_1fr] gap-4 items-stretch min-w-0">
        <div
          ref={spendingChartRef}
          className="glass-card p-5 min-w-0 grid grid-cols-[180px_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] gap-x-5 gap-y-3 overflow-hidden"
        >
          <div className="col-span-2 flex items-center justify-between gap-3">
            <div className="text-[14px] font-semibold">Spending by category</div>
            <div className="flex items-center gap-2 shrink-0">
              {monthRefreshing && data && (
                <span className="text-[11px] text-ledger-text-faintest">Updating</span>
              )}
              <select
                value={selectedMonth}
                onChange={e => selectMonth(e.target.value)}
                className="text-[12px] glass-chip px-[8px] py-[4px] text-ledger-text-primary cursor-pointer outline-none"
              >
                {monthOptions.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          {loading && !data ? (
            <div className="col-span-2 flex items-center justify-center text-ledger-text-faint text-[13px] min-h-[180px]">Loading…</div>
          ) : !data || (spendingChartData.length === 0 && data.spending_by_category.length === 0) ? (
            <div className="col-span-2 flex items-center justify-center text-ledger-text-faint text-[13px] min-h-[180px]">No expense data</div>
          ) : (
            <>
              <div
                className={`relative h-[180px] w-[180px] self-center ${loading ? 'opacity-80' : 'opacity-100'}`}
                onClick={event => {
                  const target = event.target as Element | null
                  if (target?.closest('[data-spending-legend-item="true"]') || target?.closest('.recharts-pie-sector')) {
                    return
                  }
                  setSelectedSlice(null)
                  setHoveredSlice(null)
                }}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={spendingChartData}
                      cx="50%" cy="50%"
                      innerRadius={58} outerRadius={82}
                      paddingAngle={1.5}
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
                      {spendingChartData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={entry.color}
                          stroke="#070b12"
                          strokeWidth={2}
                          style={{ outline: 'none', cursor: 'pointer' }}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  {activeCategory ? (
                    <>
                      <span className="w-[88px] text-center text-[11px] font-medium leading-snug text-ledger-text-faint break-words">
                        {formatCategory(activeCategory.name)}
                      </span>
                      <span className="mt-1 text-[16px] font-semibold tabular-nums tracking-tight">
                        ${fmt(activeCategory.value)}
                      </span>
                      {activeCategoryShare !== null && (
                        <span className="mt-0.5 text-[11px] text-ledger-text-faintest">
                          {activeCategoryShare.toFixed(0)}% of spend
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <span className="text-[11px] text-ledger-text-faint">{monthLabel}</span>
                      <span className="mt-1 text-[16px] font-semibold tabular-nums tracking-tight">
                        ${fmt(spendingChartTotal)}
                      </span>
                      <span className="mt-0.5 text-[11px] text-ledger-text-faintest">Total spent</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-[2px] min-w-0 min-h-0 self-stretch overflow-y-auto soft-scrollbar">
                {spendingChartData.map((cat, i) => (
                  <div
                    key={cat.name}
                    data-spending-legend-item="true"
                    className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[8px] px-2 py-[6px] cursor-pointer ${
                      activeSlice === i ? 'bg-ledger-hover' : 'hover:bg-ledger-hover/60'
                    }`}
                    style={{ opacity: activeSlice === null || activeSlice === i ? 1 : 0.45 }}
                    onMouseEnter={() => {
                      if (selectedSlice === null) setHoveredSlice(i)
                    }}
                    onMouseLeave={() => setHoveredSlice(null)}
                    onClick={() => {
                      setSelectedSlice(i)
                      setHoveredSlice(i)
                    }}
                  >
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: cat.color }} />
                      <span className="min-w-0 truncate text-[13px] text-ledger-text-secondary">
                        {formatCategory(cat.name)}
                      </span>
                    </div>
                    <span className="text-[13px] tabular-nums text-ledger-text-primary">
                      ${fmt(cat.value)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="glass-card px-5 py-4 flex flex-col min-h-0 min-w-0">
          <div className="flex justify-between items-center mb-3 shrink-0">
            <span className="text-[14px] font-semibold">Budget progress</span>
            <button
              onClick={() => onNavigate('budgets')}
              className="text-[13px] text-ledger-accent font-medium hover:opacity-80"
            >
              Manage
            </button>
          </div>

          {budgetLoading && !budgetData ? (
            <div className="text-center py-4 text-ledger-text-faint text-[13px]">Loading…</div>
          ) : !budgetData || budgetData.budgets.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-2 py-4 rounded-[8px] border border-dashed border-ledger-border-input">
              <div className="text-[13px] text-ledger-text-secondary mb-1.5">No budgets for {monthLabel}</div>
              <button
                onClick={() => onNavigate('budgets')}
                className="text-[13px] text-ledger-accent font-medium hover:opacity-80"
              >
                Set up budgets
              </button>
            </div>
          ) : (
            <div className={`flex flex-col flex-1 min-h-0 ${budgetLoading ? 'opacity-80' : ''}`}>
              <div className="mb-3 pb-3 border-b border-ledger-border-subtle shrink-0">
                <div className="flex justify-between text-[13px] mb-1.5">
                  <span className="text-ledger-text-secondary">Total</span>
                  <span className="tabular-nums font-semibold">
                    ${fmt(budgetData.total_spent)}
                    <span className="text-ledger-text-faint font-normal"> / ${fmt(budgetData.total_limit)}</span>
                  </span>
                </div>
                <div className="h-[5px] rounded-full bg-ledger-track overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(budgetPct ?? 0, 100)}%`,
                      backgroundColor: budgetOver ? CHART_NEGATIVE : CHART_ACCENT,
                    }}
                  />
                </div>
                <div className={`text-[12px] mt-1.5 ${budgetOver ? 'text-ledger-negative' : 'text-ledger-text-faint'}`}>
                  {budgetOver
                    ? `$${fmt(budgetData.total_spent - budgetData.total_limit)} over`
                    : `$${fmt(budgetData.total_limit - budgetData.total_spent)} remaining`}
                </div>
              </div>

              <div className="flex flex-col gap-2.5 flex-1 min-h-0 overflow-y-auto">
                {sortedBudgetItems.map(b => {
                  const isVirtual = Boolean(b.virtual)
                  const pct = b.limit > 0 ? (b.spent / b.limit) * 100 : (isVirtual ? 100 : 0)
                  const over = !isVirtual && b.spent > b.limit
                  return (
                    <div key={b.id}>
                      <div className="flex justify-between text-[13px] mb-1 leading-tight">
                        <span className="truncate pr-2 text-ledger-text-secondary">{formatCategory(b.category)}</span>
                        <span className="tabular-nums text-ledger-text-muted flex-shrink-0 text-[12px]">
                          {isVirtual ? `$${fmt(b.spent)}` : `$${fmt(b.spent)} / $${fmt(b.limit)}`}
                        </span>
                      </div>
                      <div className="h-[4px] rounded-full bg-ledger-track overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.min(pct, 100)}%`,
                            backgroundColor: over ? CHART_NEGATIVE : CHART_ACCENT,
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

      <section className="glass-card overflow-hidden min-w-0">
        <div className="flex justify-between items-center px-5 py-3">
          <span className="text-[14px] font-semibold">Recent transactions</span>
          <button
            onClick={() => onNavigate('transactions')}
            className="text-[13px] text-ledger-accent font-medium cursor-pointer hover:opacity-80"
          >
            View all
          </button>
        </div>

        <div className="flex flex-col">
          {recentLoading && recentTxns.length === 0 ? (
            <div className="px-5 py-6 text-center text-ledger-text-faint text-[13px]">Loading…</div>
          ) : recentTxns.length === 0 ? (
            <div className="px-5 py-6 text-center text-ledger-text-faint text-[13px]">
              No transactions this month. Import a CSV or sync an account.
            </div>
          ) : (
            <div className={recentLoading ? 'opacity-80' : ''}>
              {recentTxns.map(txn => (
                <div key={txn.id} className="flex items-center gap-3 px-5 py-2 border-t border-ledger-border-subtle min-h-[40px]">
                  {transactionDisplayIcon(txn) ? (
                    <img
                      src={transactionDisplayIcon(txn)!}
                      alt=""
                      className="w-6 h-6 rounded-[6px] shrink-0 bg-ledger-inset object-contain"
                    />
                  ) : (
                    <div
                      className={`w-6 h-6 rounded-[6px] flex items-center justify-center text-[10px] font-semibold flex-shrink-0 ${
                        txn.amount < 0
                          ? 'bg-ledger-positive-soft text-ledger-positive'
                          : 'bg-ledger-inset text-ledger-text-muted'
                      }`}
                    >
                      {txnInitials(txn.merchant, txn.amount)}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate leading-tight">{txn.merchant}</div>
                    <div className="text-[11.5px] text-ledger-text-faint leading-tight">
                      {txn.account_name ?? 'Unknown'} · {formatTxnDate(txn.date)}
                    </div>
                  </div>
                  <span className="text-[12px] text-ledger-text-faint whitespace-nowrap hidden sm:block">
                    {formatTransactionCategory(txn)}
                  </span>
                  <span
                    className={`text-[13px] font-medium w-[76px] text-right tabular-nums flex-shrink-0 ${
                      txn.amount < 0 ? 'text-ledger-positive' : 'text-ledger-text-primary'
                    }`}
                  >
                    {txn.amount < 0 ? '+' : '−'}${Math.abs(txn.amount).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
