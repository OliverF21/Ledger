import { useState, useEffect } from 'react'
import {
  ComposedChart, Bar, Line, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, LineChart,
} from 'recharts'
import { TrendingUp, TrendingDown, X } from 'lucide-react'
import { apiFetch } from '../api/client'
import { formatCategory } from '../utils/categories'
import {
  AXIS_STROKE,
  CHART_ACCENT,
  CHART_POSITIVE,
  CHART_TEXT,
  GRID_STROKE,
  tooltipItemStyle,
  tooltipLabelStyle,
  tooltipStyle,
} from '../utils/chartTheme'

interface TrendMonth {
  month_key: string
  label: string
  full_label: string
  total_spending: number
  total_income: number
  net: number
  is_partial: boolean
}

interface TrendCategory {
  name: string
  color: string
  monthly: number[]
  total: number
  monthly_avg: number
  share_pct: number
  last_full: number
  prior_avg: number
  change_vs_prior_pct: number | null
}

interface TrendsData {
  months: TrendMonth[]
  categories: TrendCategory[]
  period_spending: number
  period_income: number
  monthly_avg_spending: number
  prev_monthly_avg_spending: number
  spending_change_pct: number | null
}

const RANGES = [3, 6, 12, 24] as const
type Range = (typeof RANGES)[number]

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

/** Spending direction badge — up is bad (red), down is good (green). */
function ChangeBadge({ pct, suffix }: { pct: number | null; suffix?: string }) {
  if (pct === null || !isFinite(pct)) {
    return <span className="text-[12px] text-ledger-text-faintest">—</span>
  }
  const up = pct > 0
  const flat = Math.abs(pct) < 1
  const color = flat ? 'text-ledger-text-faint' : up ? 'text-ledger-negative' : 'text-ledger-positive'
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-[4px] text-[12px] font-medium tabular-nums ${color}`}>
      {!flat && <Icon className="w-[12px] h-[12px]" strokeWidth={2.2} />}
      {up ? '+' : ''}{pct.toFixed(0)}%{suffix ? <span className="text-ledger-text-faintest font-normal">{suffix}</span> : null}
    </span>
  )
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const data = values.map((v, i) => ({ i, v }))
  if (data.length < 2) return <div className="w-[90px] h-[28px]" />
  return (
    <LineChart width={90} height={28} data={data} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
      <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.6} dot={false} isAnimationActive={false} />
    </LineChart>
  )
}

export default function Trends() {
  const [range, setRange] = useState<Range>(6)
  const [data, setData] = useState<TrendsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [focus, setFocus] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/analytics/trends?months=${range}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [range])

  const months = data?.months ?? []
  const categories = data?.categories ?? []
  const hasData = months.some(m => m.total_spending > 0 || m.total_income > 0)
  const completeCount = months.filter(m => !m.is_partial).length
  const partialMonth = months.find(m => m.is_partial)

  const focused = focus ? categories.find(c => c.name === focus) ?? null : null
  // Clear a stale focus if the category vanishes after a range change
  useEffect(() => {
    if (focus && data && !data.categories.some(c => c.name === focus)) setFocus(null)
  }, [data, focus])

  const chartData = months.map((m, i) => ({
    label: m.label,
    fullLabel: m.full_label,
    isPartial: m.is_partial,
    spending: focused ? focused.monthly[i] : m.total_spending,
    income: m.total_income,
  }))

  const periodLabel = months.length > 0
    ? `${months[0].full_label} – ${months[months.length - 1].full_label}`
    : ''

  // Insights: categories whose last complete month moved meaningfully vs. their
  // own typical month. Small bases are skipped — a $4 → $9 jump isn't a story.
  const movers = categories
    .filter(c => c.change_vs_prior_pct !== null && c.prior_avg >= 25 && Math.abs(c.change_vs_prior_pct) >= 15)
    .sort((a, b) => Math.abs(b.change_vs_prior_pct!) - Math.abs(a.change_vs_prior_pct!))
    .slice(0, 3)

  const spendingChange = data?.spending_change_pct ?? null

  return (
    <div className="flex flex-col gap-[18px]">
      {/* KPI row + range control */}
      <div className="flex gap-[18px] items-stretch flex-wrap">
        <div className="glass-card p-[18px] flex-1 min-w-[180px]">
          <div className="text-[12.5px] text-ledger-text-faint">Avg monthly spend</div>
          <div className="text-[25px] font-bold mt-[4px] tabular-nums">
            {loading ? '—' : `$${fmt(data?.monthly_avg_spending ?? 0)}`}
          </div>
          <div className="mt-[4px] flex items-center gap-[6px]">
            {!loading && <ChangeBadge pct={spendingChange} />}
            {!loading && spendingChange !== null && (
              <span className="text-[11px] text-ledger-text-faintest">vs prior {completeCount} mo</span>
            )}
          </div>
        </div>

        <div className="glass-card p-[18px] flex-1 min-w-[180px]">
          <div className="text-[12.5px] text-ledger-text-faint">Spent · {periodLabel || 'this period'}</div>
          <div className="text-[25px] font-bold mt-[4px] tabular-nums">
            {loading ? '—' : `$${fmt(data?.period_spending ?? 0)}`}
          </div>
          {partialMonth && !loading && (
            <div className="mt-[4px] text-[11px] text-ledger-text-faintest">
              includes {partialMonth.full_label} so far
            </div>
          )}
        </div>

        <div className="glass-card p-[18px] flex-1 min-w-[180px]">
          <div className="text-[12.5px] text-ledger-text-faint">Income · same period</div>
          <div className="text-[25px] font-bold mt-[4px] tabular-nums text-ledger-positive">
            {loading ? '—' : `$${fmt(data?.period_income ?? 0)}`}
          </div>
        </div>

        <div className="flex items-start">
          <div className="flex gap-[6px] glass-card p-[4px]">
            {RANGES.map(r => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-[12px] py-[6px] rounded-[6px] text-[13px] font-semibold transition-all ${
                  range === r
                    ? 'bg-ledger-accent text-ledger-accent-on'
                    : 'text-ledger-text-muted hover:text-ledger-text-primary'
                }`}
              >
                {r}M
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Insight chips */}
      {!loading && movers.length > 0 && (
        <div className="flex gap-[10px] flex-wrap">
          {movers.map(c => (
            <button
              key={c.name}
              onClick={() => setFocus(focus === c.name ? null : c.name)}
              className={`glass-chip flex items-center gap-[8px] px-[12px] py-[7px] text-[12px] transition-all hover:border-ledger-accent/40 ${
                focus === c.name ? 'border-ledger-accent/60' : ''
              }`}
            >
              <span className="w-[8px] h-[8px] rounded-[2px]" style={{ backgroundColor: c.color }} />
              <span className="text-ledger-text-secondary">{formatCategory(c.name)}</span>
              <ChangeBadge pct={c.change_vs_prior_pct} />
              <span className="text-ledger-text-faintest">vs typical month</span>
            </button>
          ))}
        </div>
      )}

      {/* Main chart */}
      <div className="glass-card p-[22px]">
        <div className="flex items-center gap-[10px] mb-[16px]">
          <div className="text-[14px] font-semibold">
            {focused ? `${formatCategory(focused.name)} by month` : 'Spending vs income by month'}
          </div>
          {focused && (
            <button
              onClick={() => setFocus(null)}
              className="flex items-center gap-[4px] glass-chip px-[8px] py-[3px] text-[11px] text-ledger-text-muted hover:text-ledger-text-primary transition-colors"
            >
              <X className="w-[11px] h-[11px]" strokeWidth={2.2} />
              All categories
            </button>
          )}
        </div>

        {loading ? (
          <div className="h-[300px] flex items-center justify-center text-ledger-text-faint text-[13px]">Loading…</div>
        ) : !hasData ? (
          <div className="h-[300px] flex flex-col items-center justify-center gap-[8px] text-[13px] text-ledger-text-faint">
            <span>No transaction history yet.</span>
            <span className="text-ledger-text-faintest text-[12px]">Link an account or import a CSV, then sync.</span>
          </div>
        ) : (
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} barCategoryGap="28%">
                <CartesianGrid strokeDasharray="0" stroke={GRID_STROKE} horizontal={true} vertical={false} />
                <XAxis dataKey="label" stroke={AXIS_STROKE} style={{ fontSize: '12px' }} tickLine={false} />
                <YAxis stroke={AXIS_STROKE} style={{ fontSize: '12px' }} tickFormatter={v => `$${fmt(v)}`} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  labelFormatter={(_, payload) => {
                    const p = payload?.[0]?.payload
                    return p ? `${p.fullLabel}${p.isPartial ? ' · in progress' : ''}` : ''
                  }}
                  formatter={(val: number, name: string) => [`$${fmt(val)}`, name === 'spending' ? 'Spending' : 'Income']}
                />
                {!focused && (
                  <Legend
                    formatter={(v: string) => (
                      <span style={{ color: CHART_TEXT.muted, fontSize: '12px' }}>
                        {v === 'spending' ? 'Spending' : 'Income'}
                      </span>
                    )}
                  />
                )}
                <Bar dataKey="spending" fill={focused ? focused.color : CHART_ACCENT} radius={[4, 4, 0, 0]} maxBarSize={44}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={focused ? focused.color : CHART_ACCENT}
                      fillOpacity={entry.isPartial ? 0.4 : 0.9}
                    />
                  ))}
                </Bar>
                {!focused && (
                  <Line type="monotone" dataKey="income" stroke={CHART_POSITIVE} strokeWidth={2} dot={false} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {partialMonth && hasData && !loading && (
          <div className="mt-[10px] text-[11px] text-ledger-text-faintest">
            {partialMonth.full_label} is in progress (lighter bar) and excluded from averages and comparisons.
          </div>
        )}
      </div>

      {/* Category breakdown table */}
      {!loading && categories.length > 0 && (
        <div className="glass-card overflow-hidden">
          <div className="px-[20px] pt-[18px] pb-[10px] text-[14px] font-semibold">
            Category breakdown
            <span className="ml-[8px] text-[11.5px] font-normal text-ledger-text-faintest">
              click a row to isolate it in the chart
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-ledger-border-subtle">
                  <th className="text-left px-[20px] py-[10px] text-[11.5px] text-ledger-text-faintest uppercase font-medium">Category</th>
                  <th className="text-left px-[20px] py-[10px] text-[11.5px] text-ledger-text-faintest uppercase font-medium">Trend</th>
                  <th className="text-right px-[20px] py-[10px] text-[11.5px] text-ledger-text-faintest uppercase font-medium">Total</th>
                  <th className="text-right px-[20px] py-[10px] text-[11.5px] text-ledger-text-faintest uppercase font-medium">Avg / mo</th>
                  <th className="text-right px-[20px] py-[10px] text-[11.5px] text-ledger-text-faintest uppercase font-medium">Vs typical</th>
                  <th className="text-left px-[20px] py-[10px] text-[11.5px] text-ledger-text-faintest uppercase font-medium w-[160px]">Share</th>
                </tr>
              </thead>
              <tbody>
                {categories.map(c => {
                  // Sparkline over complete months only — the in-progress month
                  // would make every category appear to crash at the end.
                  const sparkValues = partialMonth ? c.monthly.slice(0, -1) : c.monthly
                  const isFocused = focus === c.name
                  return (
                    <tr
                      key={c.name}
                      onClick={() => setFocus(isFocused ? null : c.name)}
                      className={`border-b border-ledger-border-subtle last:border-0 cursor-pointer transition-colors ${
                        isFocused ? 'bg-ledger-inset' : 'hover:bg-ledger-inset'
                      }`}
                    >
                      <td className="px-[20px] py-[11px]">
                        <div className="flex items-center gap-[8px]">
                          <span className="w-[9px] h-[9px] rounded-[2px] shrink-0" style={{ backgroundColor: c.color }} />
                          <span className="text-[13px] font-medium truncate">{formatCategory(c.name)}</span>
                        </div>
                      </td>
                      <td className="px-[20px] py-[11px]">
                        <Sparkline values={sparkValues} color={c.color} />
                      </td>
                      <td className="px-[20px] py-[11px] text-right text-[13px] font-semibold tabular-nums">
                        ${fmt(c.total)}
                      </td>
                      <td className="px-[20px] py-[11px] text-right text-[13px] text-ledger-text-secondary tabular-nums">
                        ${fmt(c.monthly_avg)}
                      </td>
                      <td className="px-[20px] py-[11px] text-right">
                        <ChangeBadge pct={c.change_vs_prior_pct} />
                      </td>
                      <td className="px-[20px] py-[11px]">
                        <div className="flex items-center gap-[8px]">
                          <div className="flex-1 h-[5px] rounded-full bg-ledger-track overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{ width: `${Math.min(100, c.share_pct)}%`, backgroundColor: c.color }}
                            />
                          </div>
                          <span className="text-[11px] text-ledger-text-faint tabular-nums w-[36px] text-right">
                            {c.share_pct.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
