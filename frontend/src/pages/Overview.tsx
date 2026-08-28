import { useState, useEffect, useCallback, useMemo } from 'react'
import { apiFetch } from '../api/client'
import { useAnalytics } from '../hooks/useAnalytics'
import { useOnSyncComplete } from '../hooks/useSync'
import AlertsPanel from '../components/AlertsPanel'
import {
  Eyebrow, GlassCard, ChangeBadge, Tag, ProgressBar, InitialsChip, EmptyState, LoadingRow,
} from '../components/ui/primitives'
import { AreaLineChart, Donut, DonutLegend, type DonutSlice } from '../components/ui/charts'
import { formatCategory, formatTransactionCategory, transactionDisplayIcon } from '../utils/categories'
import { formatMonthLabel } from '../utils/months'
import { groupAssetAccounts } from '../utils/accountGroups'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Whole dollars — used wherever a figure sits next to a label rather than in
 *  a column of aligned amounts, where cents are noise. */
function fmtWhole(n: number) {
  return `$${Math.round(n).toLocaleString('en-US')}`
}

/** Splits a dollar amount so the cents can be set smaller and dimmer than the
 *  dollars, which is what stops the 68px hero figure reading as a wall. */
function splitAmount(value: number): { dollars: string; cents: string } {
  const abs = Math.abs(value)
  const dollars = Math.floor(abs).toLocaleString('en-US')
  const cents = (abs % 1).toFixed(2).slice(1)
  return { dollars: `${value < 0 ? '−' : ''}$${dollars}`, cents }
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

interface OverviewProps {
  onNavigate: (screen: 'transactions' | 'budgets') => void
  /** Selected month (YYYY-MM). Owned by App so the picker can live in the
   *  header cluster; see App.tsx. */
  month: string
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

function useRecentTransactions(month: string, limit = 6, refresh = 0) {
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
  const words = (merchant || '').split(' ').filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return '??'
}

function formatTxnDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  if (d.getTime() === today.getTime()) return 'Today'
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: d.getFullYear() !== today.getFullYear() ? 'numeric' : undefined,
  })
}

/* ── Hero sub-sections ──────────────────────────────────────────────────── */

/** One column of the Assets / Liabilities / This month triple beneath the
 *  net-worth figure: a total, then the accounts that make it up. */
function BreakdownColumn({
  label,
  total,
  rows,
  labelWidth = 118,
}: {
  label: string
  total: React.ReactNode
  rows: { key: string | number; name: string; value: string }[]
  labelWidth?: number
}) {
  return (
    <div className="min-w-0">
      <Eyebrow size="sm">{label}</Eyebrow>
      <div className="mt-1.5 text-[15px] font-bold tracking-[-0.025em] tabular-nums">{total}</div>
      <div className="mt-2 flex flex-col gap-[3px]">
        {rows.length === 0 ? (
          <span className="text-[11px] text-ledger-text-faintest italic">None</span>
        ) : (
          rows.map(row => (
            <div key={row.key} className="flex gap-2.5 text-[11px]">
              <span className="text-ledger-text-faint truncate" style={{ width: labelWidth }}>{row.name}</span>
              <span className="text-white/80 font-medium tabular-nums whitespace-nowrap">{row.value}</span>
            </div>
          ))
        )}
      </div>
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

/* ── Screen ─────────────────────────────────────────────────────────────── */

export default function Overview({ onNavigate, month: selectedMonth }: OverviewProps) {
  const [timeRange, setTimeRange] = useState<'6M' | '1Y'>('6M')
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const [syncRefresh, setSyncRefresh] = useState(0)
  useOnSyncComplete(useCallback(() => setSyncRefresh(n => n + 1), []))

  // Clear any pinned donut slice when the month changes — the categories
  // behind it are different data.
  useEffect(() => { setActiveSlice(null) }, [selectedMonth])

  const { data } = useAnalytics(selectedMonth)
  const { transactions: recentTxns, loading: recentLoading } = useRecentTransactions(selectedMonth, 6, syncRefresh)
  const { data: budgetData, loading: budgetLoading } = useBudgets(selectedMonth, syncRefresh)
  const { data: nwData, loading: nwLoading } = useNetWorth(timeRange === '6M' ? 6 : 12, syncRefresh)

  const monthLabel = selectedMonth ? formatMonthLabel(selectedMonth) : '—'
  const netWorth = nwData?.current_net_worth ?? 0
  const { dollars, cents } = splitAmount(netWorth)
  const growthUp = (nwData?.change_amount ?? 0) >= 0
  const chartColor = growthUp ? '#74d8a8' : '#f4907f'
  const hasHistory = Boolean(nwData && nwData.snapshots.length >= 2)

  const spendSlices: DonutSlice[] = useMemo(
    () => (data?.spending_by_category ?? []).map(cat => ({
      key: cat.name,
      label: formatCategory(cat.name),
      value: cat.value,
      color: cat.color,
    })),
    [data],
  )

  const spendingChange = data && data.prev_month_spending > 0
    ? ((data.total_spending - data.prev_month_spending) / data.prev_month_spending) * 100
    : null

  const assetAccounts = nwData?.accounts.filter(a => !a.is_liability) ?? []
  const liabilityAccounts = nwData?.accounts.filter(a => a.is_liability) ?? []
  const assetGroups = groupAssetAccounts(assetAccounts)

  const budgetPct = budgetData && budgetData.total_limit > 0
    ? (budgetData.total_spent / budgetData.total_limit) * 100
    : 0
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

  return (
    <div className="flex flex-col min-w-0">
      <AlertsPanel />

      {/* ── Hero: net worth over the drawn history curve ───────────────────
          The chart is the background of this section rather than a card of
          its own, and a radial scrim under the figures keeps them legible
          where the curve runs behind them. */}
      <section className="relative h-[410px] shrink-0 mt-1.5">
        {hasHistory && (
          <AreaLineChart
            values={nwData!.snapshots.map(s => s.total)}
            color={chartColor}
            width={1180}
            height={300}
            className="absolute top-[50px] h-[268px]"
            style={{ left: -18, right: -18, width: 'calc(100% + 36px)' }}
            maskImage="linear-gradient(90deg, #000 0%, #000 44%, rgba(0,0,0,0.25) 58%, transparent 66%)"
          />
        )}

        <div className="absolute left-[2px] top-0 z-20 ledger-rise-fast">
          <Eyebrow className="!tracking-[0.2em] !text-white/40">Net worth</Eyebrow>
          <div
            /* No tabular-nums: it pads the comma to a full digit cell and
               visibly breaks "$248,910" into three chunks. */
            className="mt-2 text-[68px] leading-[0.92] font-bold tracking-[-0.05em]"
            style={{ textShadow: '0 0 46px rgba(200,220,255,0.3)' }}
          >
            {nwLoading ? '—' : dollars}
            {!nwLoading && (
              <span className="text-[34px] font-semibold tracking-[-0.025em] text-white/[0.46]">{cents}</span>
            )}
          </div>

          <div className="mt-[13px] flex items-center gap-2.5 whitespace-nowrap">
            {hasHistory && nwData!.change_amount !== 0 && (
              <>
                <ChangeBadge positive={growthUp}>
                  {Math.abs(nwData!.change_pct).toFixed(1)}%
                </ChangeBadge>
                <span className="text-[12.5px] font-semibold" style={{ color: chartColor }}>
                  {growthUp ? '+' : '−'}${fmt(Math.abs(nwData!.change_amount))}
                </span>
              </>
            )}
            <span className="text-[12.5px] text-white/40">
              past {timeRange === '6M' ? '6 months' : '12 months'}
            </span>
            <span className="w-px h-[13px] bg-white/[0.14]" />
            <div className="flex gap-2.5 text-[11.5px] font-semibold">
              {(['6M', '1Y'] as const).map(range => (
                <button
                  key={range}
                  type="button"
                  onClick={() => setTimeRange(range)}
                  className={timeRange === range ? 'text-white' : 'text-white/[0.36] hover:text-white/85'}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Scrim: darkens the chart behind the bottom-left breakdown only. */}
        <div
          className="absolute left-0 bottom-0 w-[600px] h-[200px] z-10 pointer-events-none"
          style={{
            background:
              'radial-gradient(60% 65% at 20% 100%, rgba(8,11,15,0.92) 0%, rgba(8,11,15,0.6) 45%, rgba(8,11,15,0) 78%)',
          }}
        />

        <div className="absolute left-[2px] bottom-1 z-20 flex items-start gap-[34px] ledger-fade ledger-delay-1">
          <BreakdownColumn
            label="Assets"
            total={<span className="text-ledger-positive-soft">${fmt(nwData?.total_assets ?? 0)}</span>}
            rows={assetGroups.slice(0, 4).map(group => ({
              key: group.group,
              name: group.label,
              value: `$${fmt(group.total)}`,
            }))}
          />
          <Divider />
          <BreakdownColumn
            label="Liabilities"
            total={<span className="text-ledger-negative-soft">−${fmt(nwData?.total_liabilities ?? 0)}</span>}
            labelWidth={104}
            rows={liabilityAccounts.slice(0, 3).map(account => ({
              key: account.id,
              name: account.name,
              value: `−$${fmt(account.balance)}`,
            }))}
          />
          <Divider />
          <div>
            <Eyebrow size="sm">This month</Eyebrow>
            <div className="mt-1.5 flex items-baseline gap-2.5 text-[15px] font-bold tracking-[-0.025em] tabular-nums">
              <span className="text-ledger-positive-soft">+${fmt(data?.total_income ?? 0)}</span>
              <span className="text-ledger-negative-soft">−${fmt(data?.total_spending ?? 0)}</span>
            </div>
            <div className="mt-2 flex flex-col gap-[3px]">
              <div className="flex gap-2.5 text-[11px]">
                <span className="text-ledger-text-faint w-[60px]">Income</span>
                <span className="text-white/80 font-medium tabular-nums">${fmt(data?.total_income ?? 0)}</span>
              </div>
              <div className="flex gap-2.5 text-[11px]">
                <span className="text-ledger-text-faint w-[60px]">Spend</span>
                <span className="text-white/80 font-medium tabular-nums">${fmt(data?.total_spending ?? 0)}</span>
              </div>
              <div className="flex gap-2.5 text-[11px]">
                <span className="text-ledger-text-faint w-[60px]">Saved</span>
                <span className="text-white/80 font-medium tabular-nums">
                  {data ? `${data.savings_rate.toFixed(0)}%` : '—'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Spending list + donut, right-aligned against the faded chart. */}
        <div className="absolute right-0 top-5 z-20 flex items-center gap-5 ledger-rise">
          <div className="flex flex-col items-end gap-px">
            <Eyebrow size="sm" className="mb-1.5">{monthLabel} spending</Eyebrow>
            {spendSlices.length === 0 ? (
              <span className="text-[11.5px] text-ledger-text-faint">No expenses this month</span>
            ) : (
              <DonutLegend
                slices={spendSlices.slice(0, 8)}
                activeIndex={activeSlice}
                onHover={setActiveSlice}
                formatValue={fmtWhole}
              />
            )}
          </div>

          <Donut
            slices={spendSlices.slice(0, 8)}
            size={258}
            radius={84}
            strokeWidth={24}
            activeIndex={activeSlice}
            onHover={setActiveSlice}
          >
            {activeSlice !== null && spendSlices[activeSlice] ? (
              <>
                <div className="text-[9px] uppercase tracking-[0.18em] font-semibold text-white/[0.38] max-w-[110px] truncate">
                  {spendSlices[activeSlice].label}
                </div>
                <div className="mt-1 text-[30px] font-bold tracking-[-0.04em] tabular-nums">
                  {fmtWhole(spendSlices[activeSlice].value)}
                </div>
                <div className="mt-[3px] text-[10.5px] font-semibold text-white/50">
                  {data && data.total_spending > 0
                    ? `${((spendSlices[activeSlice].value / data.total_spending) * 100).toFixed(0)}% of spend`
                    : ''}
                </div>
              </>
            ) : (
              <>
                <div className="text-[9px] uppercase tracking-[0.18em] font-semibold text-white/[0.38]">Spent</div>
                <div className="mt-1 text-[30px] font-bold tracking-[-0.04em] tabular-nums">
                  {fmtWhole(data?.total_spending ?? 0)}
                </div>
                {spendingChange !== null && (
                  <div
                    className="mt-[3px] text-[10.5px] font-semibold"
                    style={{ color: spendingChange > 0 ? '#f5b3a4' : '#b6ebcd' }}
                  >
                    {spendingChange > 0 ? '+' : ''}{spendingChange.toFixed(0)}% vs prior
                  </div>
                )}
              </>
            )}
          </Donut>
        </div>
      </section>

      {/* ── Activity + Budgets ─────────────────────────────────────────── */}
      <section className="grid grid-cols-[1.46fr_1fr] gap-[22px] mt-2 min-h-[300px]">
        <GlassCard className="flex flex-col">
          <div className="flex items-center justify-between px-5 pt-[15px] pb-[11px]">
            <Eyebrow className="!text-white/[0.48]">Activity</Eyebrow>
            <button
              type="button"
              onClick={() => onNavigate('transactions')}
              className="text-[11.5px] font-semibold text-white/[0.74] hover:text-white"
            >
              View all →
            </button>
          </div>

          <div className="flex flex-col flex-1 px-2 pb-2">
            {recentLoading && recentTxns.length === 0 ? (
              <LoadingRow />
            ) : recentTxns.length === 0 ? (
              <EmptyState
                title="Nothing this month"
                body="Import a CSV or sync an account to see transactions here."
              />
            ) : (
              recentTxns.map((txn, i) => (
                <div
                  key={txn.id}
                  className="grid grid-cols-[28px_minmax(0,1fr)_110px_94px] items-center gap-[11px] px-3 py-2 rounded-[12px] flex-1 row-hover"
                  style={i > 0 ? { borderTop: '1px solid rgba(255,255,255,0.08)' } : undefined}
                >
                  {transactionDisplayIcon(txn) ? (
                    <img
                      src={transactionDisplayIcon(txn)!}
                      alt=""
                      className="w-7 h-7 rounded-[9px] object-contain bg-white/[0.06]"
                    />
                  ) : (
                    <InitialsChip
                      initials={txnInitials(txn.merchant, txn.amount)}
                      color={txn.amount < 0 ? '#74d8a8' : undefined}
                    />
                  )}
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-semibold tracking-[-0.01em] truncate">{txn.merchant}</div>
                    <div className="text-[10.5px] text-white/[0.44] mt-px truncate">
                      {txn.account_name ?? 'Unknown'} · {formatTxnDate(txn.date)}
                    </div>
                  </div>
                  <Tag
                    className="justify-self-start truncate max-w-full"
                    color={txn.amount < 0 ? '#74d8a8' : undefined}
                  >
                    {formatTransactionCategory(txn)}
                  </Tag>
                  <span
                    className="text-right text-[13px] font-bold tracking-[-0.02em] tabular-nums"
                    style={txn.amount < 0 ? { color: '#b6ebcd' } : undefined}
                  >
                    {txn.amount < 0 ? '+' : '−'}${fmt(Math.abs(txn.amount))}
                  </span>
                </div>
              ))
            )}
          </div>
        </GlassCard>

        {/* Budgets is deliberately not a card — it reads as a column of the
            page so the eye doesn't have to cross two glass edges to compare
            it against the activity list beside it. */}
        <div className="flex flex-col px-0.5 pt-1 pb-1.5 ledger-fade ledger-delay-2">
          <div className="flex items-center justify-between">
            <Eyebrow className="!text-white/40">Budgets</Eyebrow>
            <button
              type="button"
              onClick={() => onNavigate('budgets')}
              className="text-[11.5px] font-semibold text-white/60 hover:text-white"
            >
              Manage
            </button>
          </div>

          {budgetLoading && !budgetData ? (
            <LoadingRow />
          ) : !budgetData || budgetData.budgets.length === 0 ? (
            <EmptyState
              className="flex-1"
              title={`No budgets for ${monthLabel}`}
              action={
                <button
                  type="button"
                  onClick={() => onNavigate('budgets')}
                  className="text-[11.5px] font-semibold text-ledger-accent hover:brightness-110"
                >
                  Set up budgets →
                </button>
              }
            />
          ) : (
            <>
              <div className="mt-[11px] pb-[13px] border-b border-white/[0.12]">
                <div className="flex items-baseline justify-between">
                  <span className="text-[22px] font-bold tracking-[-0.035em] tabular-nums">
                    ${fmt(budgetData.total_spent)}
                  </span>
                  <span className="text-[11.5px] text-white/[0.44] tabular-nums">
                    of ${fmt(budgetData.total_limit)}
                  </span>
                </div>
                <div className="mt-2.5">
                  <ProgressBar
                    pct={budgetPct}
                    height={6}
                    glow
                    color={budgetOver ? '#f4907f' : '#ffffff'}
                  />
                </div>
                <div className={`mt-[7px] text-[11px] ${budgetOver ? 'text-ledger-negative-soft' : 'text-white/[0.48]'}`}>
                  {budgetOver
                    ? `$${fmt(budgetData.total_spent - budgetData.total_limit)} over`
                    : `$${fmt(budgetData.total_limit - budgetData.total_spent)} left`}
                </div>
              </div>

              <div className="flex flex-col gap-2.5 mt-[13px] flex-1 justify-between">
                {sortedBudgetItems.slice(0, 6).map(budget => {
                  const isVirtual = Boolean(budget.virtual)
                  const pct = budget.limit > 0 ? (budget.spent / budget.limit) * 100 : (isVirtual ? 100 : 0)
                  const over = !isVirtual && budget.spent > budget.limit
                  return (
                    <div key={budget.id}>
                      <div className="flex justify-between text-[11.5px] mb-[5px] gap-2">
                        <span className="text-white/[0.84] font-medium truncate">
                          {formatCategory(budget.category)}
                        </span>
                        <span
                          className={`tabular-nums whitespace-nowrap ${over ? 'text-ledger-negative-soft font-bold' : 'text-white/[0.56]'}`}
                        >
                          {isVirtual
                            ? `$${fmt(budget.spent)}`
                            : `$${fmt(budget.spent)} / $${Math.round(budget.limit).toLocaleString('en-US')}`}
                        </span>
                      </div>
                      <ProgressBar pct={pct} color={over ? '#f4907f' : budget.color} glow={over} />
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
