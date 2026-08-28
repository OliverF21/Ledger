import { useState, useEffect, useRef } from 'react'
import {
  X, Pencil, Trash2, Sparkles, ChevronRight, TrendingUp, Check,
  Repeat, UtensilsCrossed, ShoppingBasket, ShoppingBag, Home, Car,
  Plane, Heart, Film, Gift, Wallet, Zap, Wifi, Phone, Coffee, Music,
  Gamepad2, Shirt, Fuel, Stethoscope, Building2, GraduationCap, PawPrint,
  Briefcase, Circle, type LucideIcon,
} from 'lucide-react'
import { apiFetch } from '../api/client'
import { formatCategory } from '../utils/categories'
import { getMonthOptions, currentMonthValue } from '../utils/months'
import { alphaColor } from '../utils/color'
import { useSubscriptions, type SubscriptionItem } from '../hooks/useSubscriptions'
import { Eyebrow, GlassCard, ProgressBar, InitialsChip } from '../components/ui/primitives'

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

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtWhole(n: number) {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

const TRACK_OK = '#63cfcc'
const TRACK_OVER = '#f4907f'

function daysLeftInMonth(month: string): number | null {
  if (month !== currentMonthValue()) return null
  const now = new Date()
  const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
  return lastDay - now.getDate()
}

function formatDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatCadence(cadence: string) {
  if (cadence === 'weekly') return 'Weekly'
  if (cadence === 'monthly') return 'Monthly'
  if (cadence === 'annual') return 'Annual'
  return cadence
}

function monthlyCost(sub: SubscriptionItem): number {
  if (sub.cadence === 'monthly') return sub.average_amount
  if (sub.cadence === 'weekly') return sub.average_amount * 4.33
  if (sub.cadence === 'annual') return sub.average_amount / 12
  return sub.average_amount
}

function categoryIcon(category: string): LucideIcon {
  const c = category.toLowerCase()
  if (/dining|restaurant|food.?and.?drink|fast.?food|alcohol|bar/.test(c)) return UtensilsCrossed
  if (/coffee/.test(c)) return Coffee
  if (/grocer/.test(c)) return ShoppingBasket
  if (/shop|merchandise|clothing|electronics|sporting/.test(c)) return ShoppingBag
  if (/rent|hous|home|utilit|mortgage/.test(c)) return Home
  if (/gas|fuel/.test(c) && !/electric/.test(c)) return Fuel
  if (/car|transport|rideshare|transit|parking/.test(c)) return Car
  if (/travel|flight|lodging|hotel/.test(c)) return Plane
  if (/medical|health|doctor|pharm/.test(c)) return Stethoscope
  if (/gym|fitness|personal.?care|beauty/.test(c)) return Heart
  if (/stream|entertainment|video.?game/.test(c)) return Gamepad2
  if (/music/.test(c)) return Music
  if (/film|movie/.test(c)) return Film
  if (/gift|donat/.test(c)) return Gift
  if (/pet/.test(c)) return PawPrint
  if (/educat|tuition/.test(c)) return GraduationCap
  if (/internet|cable|wifi/.test(c)) return Wifi
  if (/phone|telephone/.test(c)) return Phone
  if (/loan|credit.?card|bank.?fee|transfer/.test(c)) return Building2
  if (/income|wage/.test(c)) return Wallet
  if (/business/.test(c)) return Briefcase
  if (/shirt/.test(c)) return Shirt
  if (/electric|power/.test(c)) return Zap
  return Circle
}

const MONTH_OPTIONS = getMonthOptions(6)

const PALETTE = [
  '#82a9f2', '#63cfcc', '#a196fa', '#74d8a8', '#e6bd79',
  '#f4907f', '#f4a97f', '#95c8ff', '#a3dfc0', '#b9a8ff',
]

interface ModalProps {
  month: string
  editing: BudgetItem | null
  onClose: () => void
  onSaved: () => void
}

function BudgetModal({ month, editing, onClose, onSaved }: ModalProps) {
  const [category, setCategory] = useState(editing?.category ?? '')
  const [limit, setLimit] = useState(editing ? String(editing.limit) : '')
  const [color, setColor] = useState(editing?.color ?? PALETTE[0])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    const limitNum = parseFloat(limit)
    if (!category.trim()) return setError('Category name is required')
    if (isNaN(limitNum) || limitNum <= 0) return setError('Enter a valid limit amount')
    setSaving(true)
    setError(null)
    try {
      let res: Response
      if (editing) {
        res = await apiFetch(`/api/budgets/${editing.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ limit: limitNum }),
        })
      } else {
        res = await apiFetch('/api/budgets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category_name: category.trim(), limit: limitNum, month, color }),
        })
      }
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Save failed')
      }
      onSaved()
      onClose()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="glass-overlay fixed inset-0 z-50 flex items-center justify-center">
      <div className="glass-modal p-[26px] w-[380px]">
        <div className="flex items-center justify-between mb-[20px]">
          <h3 className="text-[15px] font-semibold">{editing ? 'Edit budget' : 'New budget'}</h3>
          <button onClick={onClose} className="text-ledger-text-faint hover:text-ledger-text-primary transition-colors">
            <X className="w-[16px] h-[16px]" />
          </button>
        </div>

        <div className="flex flex-col gap-[14px]">
          {!editing && (
            <div>
              <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Category</label>
              <input
                type="text"
                value={category}
                onChange={e => setCategory(e.target.value)}
                placeholder="e.g. Groceries, Dining Out…"
                className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-white/60"
              />
            </div>
          )}

          <div>
            <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Monthly limit</label>
            <div className="relative">
              <span className="absolute left-[12px] top-1/2 -translate-y-1/2 text-[13px] text-ledger-text-faint">$</span>
              <input
                type="number"
                min="0"
                step="10"
                value={limit}
                onChange={e => setLimit(e.target.value)}
                placeholder="0.00"
                className="w-full glass-chip pl-[24px] pr-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-white/60"
              />
            </div>
          </div>

          {!editing && (
            <div>
              <label className="text-[12px] text-ledger-text-faint block mb-[8px]">Color</label>
              <div className="flex gap-[8px] flex-wrap">
                {PALETTE.map(c => (
                  <button
                    key={c}
                    onClick={() => setColor(c)}
                    className="w-[22px] h-[22px] rounded-[6px] transition-transform hover:scale-110"
                    style={{
                      backgroundColor: c,
                      outline: color === c ? `2px solid ${c}` : undefined,
                      outlineOffset: color === c ? '2px' : undefined,
                    }}
                  />
                ))}
              </div>
            </div>
          )}

          {error && <p className="text-[12px] text-ledger-negative">{error}</p>}

          <button
            onClick={handleSave}
            disabled={saving}
            className="mt-[4px] w-full solid-cta rounded-[9px] py-[9px] font-semibold text-[13px] disabled:opacity-50"
          >
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Add budget'}
          </button>
        </div>
      </div>
    </div>
  )
}

const ONBOARDING_KEY = 'ledger_budgets_onboarded'

function OnboardingPrompt({ onAskAdvisor, onDismiss }: { onAskAdvisor: () => void; onDismiss: () => void }) {
  return (
    <div className="glass-overlay fixed inset-0 z-50 flex items-center justify-center">
      <div className="glass-modal w-[420px] p-[32px] flex flex-col items-center text-center">
        <div className="icon-well w-[48px] h-[48px] rounded-[14px] flex items-center justify-center mb-[18px]">
          <Sparkles className="w-[22px] h-[22px]" strokeWidth={1.6} />
        </div>
        <h3 className="text-[17px] font-bold mb-[8px]">Set up your budgets</h3>
        <p className="text-[13px] text-ledger-text-faint leading-relaxed mb-[24px]">
          Add monthly limits by category, or ask the AI Advisor to propose them from your spending.
        </p>
        <div className="flex flex-col gap-[10px] w-full">
          <button
            onClick={onAskAdvisor}
            className="w-full solid-cta rounded-[10px] py-[11px] font-semibold text-[13px]"
          >
            Open AI Advisor
          </button>
          <button
            onClick={onDismiss}
            className="w-full glass-chip text-ledger-text-primary rounded-[10px] py-[11px] font-semibold text-[13px] hover:opacity-80 transition-opacity"
          >
            I'll set it up manually
          </button>
        </div>
      </div>
    </div>
  )
}

type Insight = {
  id: string
  kind: 'over' | 'ok' | 'remaining'
  title: string
  detail: string
  budgetId?: number
}

export default function Budgets() {
  // Default to the current month so budgets set for "this month" (incl. ones
  // applied from the AI Advisor) are visible immediately.
  const [selectedMonth, setSelectedMonth] = useState(MONTH_OPTIONS[0].value)
  const [data, setData] = useState<BudgetsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [editing, setEditing] = useState<BudgetItem | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [focusId, setFocusId] = useState<number | null>(null)
  const focusTimer = useRef<number | null>(null)
  const { subscriptions, loading: subsLoading } = useSubscriptions()

  const fetchBudgets = (checkOnboarding = false) => {
    setLoading(true)
    apiFetch(`/api/budgets?month=${selectedMonth}`)
      .then(r => r.json())
      .then(d => {
        setData(d)
        if (checkOnboarding && (!d.budgets || d.budgets.length === 0) && !localStorage.getItem(ONBOARDING_KEY)) {
          setShowOnboarding(true)
        }
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchBudgets(true) }, [selectedMonth])

  useEffect(() => {
    return () => {
      if (focusTimer.current) window.clearTimeout(focusTimer.current)
    }
  }, [])

  const handleDelete = async (id: number) => {
    setDeletingId(id)
    setDeleteError(null)
    try {
      const res = await apiFetch(`/api/budgets/${id}`, { method: 'DELETE' })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Failed to remove budget')
      }
      setConfirmingDeleteId(null)
      setData(prev => {
        if (!prev) return prev
        const remainingBudgets = prev.budgets.filter(b => b.id !== id)
        return {
          ...prev,
          budgets: remainingBudgets,
          total_limit: remainingBudgets.reduce((sum, b) => sum + b.limit, 0),
          total_spent: remainingBudgets.reduce((sum, b) => sum + b.spent, 0),
        }
      })
    } catch (e: any) {
      setDeleteError(e.message || 'Failed to remove budget')
      fetchBudgets()
    } finally {
      setDeletingId(null)
    }
  }

  const focusBudget = (id: number) => {
    setFocusId(id)
    requestAnimationFrame(() => {
      document.getElementById(`budget-row-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    if (focusTimer.current) window.clearTimeout(focusTimer.current)
    focusTimer.current = window.setTimeout(() => setFocusId(null), 1600)
  }

  const budgets = data?.budgets ?? []
  const totalBudget = data?.total_limit ?? 0
  const totalSpent = data?.total_spent ?? 0
  const remaining = totalBudget - totalSpent
  const totalOver = remaining < 0
  const totalPct = totalBudget > 0 ? (totalSpent / totalBudget) * 100 : 0
  const daysLeft = daysLeftInMonth(selectedMonth)

  const sortedBudgets = [...budgets].sort((a, b) => {
    const aVirtual = Boolean(a.virtual)
    const bVirtual = Boolean(b.virtual)
    if (aVirtual !== bVirtual) return aVirtual ? 1 : -1
    const aOver = !aVirtual && a.spent > a.limit
    const bOver = !bVirtual && b.spent > b.limit
    if (aOver !== bOver) return aOver ? -1 : 1
    const aPct = a.limit > 0 ? a.spent / a.limit : 0
    const bPct = b.limit > 0 ? b.spent / b.limit : 0
    if (bPct !== aPct) return bPct - aPct
    return a.category.localeCompare(b.category)
  })

  const overBudgets = budgets.filter(b => !b.virtual && b.spent > b.limit)
  const insights: Insight[] = overBudgets.map(b => ({
    id: `over-${b.id}`,
    kind: 'over' as const,
    title: `${formatCategory(b.category)} is over budget`,
    detail: `You've spent $${fmt(b.spent - b.limit)} more than planned`,
    budgetId: b.id,
  }))

  if (overBudgets.length === 0) {
    const best = budgets
      .filter(b => !b.virtual && b.limit > 0 && b.spent / b.limit <= 0.85)
      .sort((a, b) => (a.spent / a.limit) - (b.spent / b.limit))[0]
    if (best) {
      insights.push({
        id: `ok-${best.id}`,
        kind: 'ok',
        title: `${formatCategory(best.category)}: You're doing great`,
        detail: `$${fmt(best.limit - best.spent)} remaining in this category`,
        budgetId: best.id,
      })
    }
  }

  if (remaining > 0 && totalBudget > 0) {
    insights.push({
      id: 'remaining',
      kind: 'remaining',
      title: `$${fmtWhole(remaining)} left to budget`,
      detail: 'You can still reach your goals',
    })
  }

  const recurring = [...subscriptions].sort((a, b) => a.next_expected_date.localeCompare(b.next_expected_date))
  const recurringMonthly = subscriptions.reduce((sum, s) => sum + monthlyCost(s), 0)

  let remainingCopy = ''
  if (!loading && totalBudget > 0) {
    const money = totalOver
      ? `$${fmtWhole(Math.abs(remaining))} over`
      : `$${fmtWhole(remaining)} left`
    if (daysLeft === null) remainingCopy = money
    else if (daysLeft === 0) remainingCopy = `${money} · last day`
    else remainingCopy = `${money} · ${daysLeft} day${daysLeft === 1 ? '' : 's'} to go`
  }

  return (
    <div className="flex flex-col gap-[14px]">
      {showOnboarding && (
        <OnboardingPrompt
          onAskAdvisor={() => {
            localStorage.setItem(ONBOARDING_KEY, '1')
            setShowOnboarding(false)
            window.location.hash = 'advisor'
          }}
          onDismiss={() => {
            localStorage.setItem(ONBOARDING_KEY, '1')
            setShowOnboarding(false)
          }}
        />
      )}
      {(showModal || editing) && (
        <BudgetModal
          month={selectedMonth}
          editing={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSaved={fetchBudgets}
        />
      )}

      {deleteError && (
        <GlassCard className="px-[16px] py-[12px] text-[13px] text-ledger-negative" rise={false}>
          {deleteError}
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(300px,0.92fr)_minmax(0,1.28fr)] gap-[14px] items-stretch">
        <div className="flex flex-col gap-[14px] min-w-0">
          <GlassCard className="p-[22px]">
            <div className="flex items-center justify-between gap-[12px] mb-[14px]">
              <Eyebrow>Monthly progress</Eyebrow>
              <select
                value={selectedMonth}
                onChange={e => setSelectedMonth(e.target.value)}
                aria-label="Budget month"
                className="glass-chip px-[10px] py-[6px] text-[12px] text-ledger-text-primary cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
              >
                {MONTH_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="flex items-baseline gap-[8px] flex-wrap">
              <span className="text-[32px] leading-none font-bold tabular-nums tracking-tight">
                {loading ? '—' : `$${fmtWhole(totalSpent)}`}
              </span>
              <span className="text-[15px] text-ledger-text-faint tabular-nums">
                of {loading ? '—' : `$${fmtWhole(totalBudget)}`}
              </span>
            </div>
            <div className="flex items-center gap-[12px] mt-[16px]">
              <div className="flex-1">
                <ProgressBar
                  pct={totalPct}
                  height={11}
                  glow
                  color={totalOver ? TRACK_OVER : TRACK_OK}
                />
              </div>
              <span className={`text-[13px] tabular-nums w-[42px] text-right shrink-0 ${totalOver ? 'text-ledger-negative' : 'text-ledger-text-secondary'}`}>
                {loading || totalBudget <= 0 ? '—' : `${Math.round(totalPct)}%`}
              </span>
            </div>
            {remainingCopy && (
              <p className={`text-[12px] mt-[10px] ${totalOver ? 'text-ledger-negative-soft' : 'text-ledger-text-faint'}`}>
                {remainingCopy}
              </p>
            )}
          </GlassCard>

          {insights.length > 0 && (
            <GlassCard className="p-[22px]">
              <Eyebrow className="mb-[14px]">Budget insights</Eyebrow>
              <div className="flex flex-col gap-[4px]">
                {insights.map(insight => {
                  const clickable = insight.budgetId != null
                  const Icon = insight.kind === 'over' ? TrendingUp : insight.kind === 'ok' ? Check : Wallet
                  const iconWrap = insight.kind === 'over'
                    ? 'bg-[rgba(244,144,127,0.16)] text-ledger-negative'
                    : 'bg-[rgba(99,207,204,0.16)] text-ledger-cat-teal'
                  return (
                    <button
                      key={insight.id}
                      type="button"
                      onClick={() => insight.budgetId != null && focusBudget(insight.budgetId)}
                      disabled={!clickable}
                      className={`flex items-center gap-[12px] w-full text-left rounded-[12px] px-[8px] py-[10px] -mx-[8px] transition-colors ${
                        clickable ? 'hover:bg-white/[0.04] cursor-pointer' : 'cursor-default'
                      } focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50`}
                    >
                      <span className={`w-[36px] h-[36px] rounded-full flex items-center justify-center shrink-0 ${iconWrap}`}>
                        <Icon className="w-[15px] h-[15px]" strokeWidth={2.1} />
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="block text-[13px] font-semibold leading-tight">{insight.title}</span>
                        <span className="block text-[12px] text-ledger-text-faint mt-[3px] leading-snug">{insight.detail}</span>
                      </span>
                      {clickable && (
                        <ChevronRight className="w-[15px] h-[15px] text-ledger-text-faintest shrink-0" strokeWidth={2} />
                      )}
                    </button>
                  )
                })}
              </div>
            </GlassCard>
          )}

          <GlassCard className="p-[22px] flex-1">
            <div className="flex items-center justify-between gap-[12px] mb-[14px]">
              <Eyebrow>Recurring</Eyebrow>
              {!subsLoading && subscriptions.length > 0 && (
                <span className="text-[12px] text-ledger-text-faint tabular-nums">
                  ${fmt(recurringMonthly)} / mo
                </span>
              )}
            </div>
            {subsLoading ? (
              <div className="text-[13px] text-ledger-text-faint py-[8px]">Loading recurring charges…</div>
            ) : recurring.length === 0 ? (
              <div className="py-[6px]">
                <Repeat className="w-[16px] h-[16px] text-ledger-text-faint mb-[8px]" strokeWidth={1.8} />
                <p className="text-[13px] font-medium">No recurring charges detected</p>
                <p className="text-[12px] text-ledger-text-faint mt-[4px] leading-relaxed">
                  Merchants billed on a regular schedule for a consistent amount, at least 3 times, show up here.
                </p>
              </div>
            ) : (
              <ul className="flex flex-col">
                {recurring.map((sub, i) => (
                  <li
                    key={`${sub.merchant}-${i}`}
                    className="flex items-center gap-[12px] py-[11px] border-b border-white/[0.06] last:border-b-0"
                  >
                    <InitialsChip initials={sub.merchant.slice(0, 1).toUpperCase()} size={36} radius={18} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-semibold truncate">{sub.merchant}</div>
                      <div className="text-[11.5px] text-ledger-text-faint mt-[2px] truncate">
                        {formatCadence(sub.cadence)} · {formatCategory(sub.category)}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-[13px] font-semibold tabular-nums">${fmt(sub.average_amount)}</div>
                      <div className="text-[11px] text-ledger-text-faint mt-[2px]">
                        {formatDate(sub.next_expected_date)}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </GlassCard>
        </div>

        <GlassCard className="p-[22px] min-w-0 flex flex-col">
          <div className="flex items-center justify-between gap-[12px] mb-[18px]">
            <Eyebrow>Budgets</Eyebrow>
            <button
              type="button"
              onClick={() => setShowModal(true)}
              className="solid-cta rounded-[8px] px-[12px] py-[6px] font-semibold text-[12.5px] active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
            >
              Add
            </button>
          </div>

          {loading && !data ? (
            <div className="text-[13px] text-ledger-text-faint py-[24px] text-center">Loading…</div>
          ) : budgets.length === 0 ? (
            <div className="py-[28px] text-center">
              <div className="text-[14px] font-semibold mb-[6px]">No budgets for this month</div>
              <div className="text-[13px] text-ledger-text-faint mb-[14px]">
                Set monthly spending limits by category.
              </div>
              <button
                type="button"
                onClick={() => setShowModal(true)}
                className="solid-cta rounded-[8px] px-[14px] py-[8px] font-semibold text-[13px]"
              >
                Add budget
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-[18px] flex-1 min-h-0">
              {sortedBudgets.map(budget => {
                const isVirtual = Boolean(budget.virtual)
                const pct = budget.limit > 0 ? (budget.spent / budget.limit) * 100 : (isVirtual ? 100 : 0)
                const isOver = !isVirtual && budget.spent > budget.limit
                const Icon = categoryIcon(budget.category)
                const iconColor = isOver ? TRACK_OVER : (isVirtual ? '#8a909c' : budget.color || TRACK_OK)
                return (
                  <div
                    key={budget.id}
                    id={`budget-row-${budget.id}`}
                    className={`rounded-[14px] -mx-[8px] px-[8px] py-[6px] transition-colors ${
                      focusId === budget.id ? 'bg-white/[0.05]' : ''
                    }`}
                  >
                    <div className="flex items-center gap-[12px]">
                      <span
                        className="w-[36px] h-[36px] rounded-full flex items-center justify-center shrink-0"
                        style={{ backgroundColor: alphaColor(iconColor, 0.16), color: iconColor }}
                      >
                        <Icon className="w-[15px] h-[15px]" strokeWidth={2} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-[10px]">
                          <span className="flex items-center gap-[6px] min-w-0">
                            <span className="text-[13.5px] font-semibold truncate">{formatCategory(budget.category)}</span>
                            {!isVirtual && (
                              <span className="flex items-center shrink-0">
                                <button
                                  type="button"
                                  title="Edit budget"
                                  onClick={() => { setConfirmingDeleteId(null); setEditing(budget) }}
                                  className="p-[3px] text-ledger-text-faintest hover:text-ledger-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 rounded"
                                >
                                  <Pencil className="w-[12px] h-[12px]" strokeWidth={2} />
                                </button>
                                <button
                                  type="button"
                                  title="Remove budget"
                                  onClick={() => {
                                    setDeleteError(null)
                                    setConfirmingDeleteId(prev => prev === budget.id ? null : budget.id)
                                  }}
                                  disabled={deletingId === budget.id}
                                  className="p-[3px] text-ledger-text-faintest hover:text-ledger-negative transition-colors disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 rounded"
                                >
                                  <Trash2 className="w-[12px] h-[12px]" strokeWidth={2} />
                                </button>
                              </span>
                            )}
                          </span>
                          <span className={`text-[13px] tabular-nums shrink-0 ${isOver ? 'text-ledger-negative' : 'text-ledger-text-secondary'}`}>
                            {isVirtual ? (
                              `$${fmt(budget.spent)}`
                            ) : (
                              <>
                                ${fmt(budget.spent)}
                                <span className="text-ledger-text-faint"> / ${fmt(budget.limit)}</span>
                              </>
                            )}
                          </span>
                        </div>
                      </div>
                    </div>

                    {!isVirtual && confirmingDeleteId === budget.id && (
                      <div className="flex items-center justify-between gap-[10px] mt-[10px] ml-[48px] px-[10px] py-[8px] rounded-[8px] border border-ledger-border-subtle bg-ledger-inset/60">
                        <span className="text-[12px] text-ledger-text-secondary">Remove this budget?</span>
                        <div className="flex items-center gap-[8px] shrink-0">
                          <button
                            type="button"
                            onClick={() => setConfirmingDeleteId(null)}
                            className="text-[12px] text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(budget.id)}
                            disabled={deletingId === budget.id}
                            className="text-[12px] font-semibold text-ledger-negative hover:opacity-80 transition-opacity disabled:opacity-40"
                          >
                            {deletingId === budget.id ? 'Removing…' : 'Remove'}
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center gap-[12px] mt-[10px] ml-[48px]">
                      <div className="flex-1">
                        <ProgressBar
                          pct={pct}
                          height={8}
                          color={isOver ? TRACK_OVER : isVirtual ? '#adb8cb' : TRACK_OK}
                        />
                      </div>
                      <span className={`text-[12px] tabular-nums w-[40px] text-right shrink-0 ${isOver ? 'text-ledger-negative' : 'text-ledger-text-faint'}`}>
                        {`${Math.round(pct)}%`}
                      </span>
                    </div>
                    {isOver && (
                      <p className="text-[12px] text-ledger-negative mt-[6px] ml-[48px]">
                        Over budget by ${fmt(budget.spent - budget.limit)}
                      </p>
                    )}
                    {isVirtual && (
                      <p className="text-[11.5px] text-ledger-text-faint mt-[6px] ml-[48px]">
                        Outside tracked categories
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  )
}
