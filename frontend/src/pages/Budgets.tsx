import { useState, useEffect } from 'react'
import { X, Pencil, Trash2, Sparkles } from 'lucide-react'
import { PieChart, Pie, Cell, Sector, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../api/client'
import { formatCategory } from '../utils/categories'
import { getMonthOptions } from '../utils/months'
import { CATEGORY_PALETTE, CHART_ACCENT, CHART_NEGATIVE, CHART_SURFACE, CHART_TEXT } from '../utils/chartTheme'

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

const MONTH_OPTIONS = getMonthOptions(6)

interface Suggestion {
  category: string
  label: string
  suggested: number
  actual_avg: number
  color: string
}

interface SuggestData {
  avg_monthly_income: number
  months_sampled: number
  suggestions: Suggestion[]
}

const PALETTE = CATEGORY_PALETTE

interface SuggestPanelProps {
  month: string
  onClose: () => void
  onApplied: () => void
}

const UNALLOCATED_COLOR = CHART_SURFACE.borderStrong

function SuggestPanel({ month, onClose, onApplied }: SuggestPanelProps) {
  const [data, setData] = useState<SuggestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [amounts, setAmounts] = useState<Record<string, string>>({})
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch('/api/budgets/suggest')
      .then(r => r.json())
      .then(d => {
        setData(d)
        setSelected(new Set(d.suggestions.map((s: Suggestion) => s.category)))
        const init: Record<string, string> = {}
        d.suggestions.forEach((s: Suggestion) => { init[s.category] = String(Math.round(s.suggested)) })
        setAmounts(init)
      })
      .catch(() => setError('Failed to load suggestions'))
      .finally(() => setLoading(false))
  }, [])

  const toggle = (cat: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(cat) ? next.delete(cat) : next.add(cat)
      return next
    })
  }

  const setAmount = (cat: string, val: string) => {
    setAmounts(prev => ({ ...prev, [cat]: val }))
  }

  const handleApply = async () => {
    if (!data) return
    setApplying(true)
    setError(null)
    const toApply = data.suggestions.filter(s => selected.has(s.category))
    let failed = 0
    for (const s of toApply) {
      const limit = parseFloat(amounts[s.category] ?? String(s.suggested))
      if (isNaN(limit) || limit <= 0) { failed++; continue }
      try {
        const res = await apiFetch('/api/budgets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category_name: s.label, category_key: s.category, limit, month, color: s.color }),
        })
        const json = await res.json()
        if (!res.ok && !json.detail?.includes('already exists')) failed++
      } catch { failed++ }
    }
    setApplying(false)
    if (failed > 0) setError(`${failed} budget(s) failed to save`)
    else { onApplied(); onClose() }
  }

  // Build pie data from selected suggestions + unallocated remainder
  const pieData = data ? (() => {
    const slices = data.suggestions
      .filter(s => selected.has(s.category))
      .map(s => {
        const value = Math.max(0, parseFloat(amounts[s.category] ?? String(s.suggested)) || 0)
        return {
          name: s.label,
          value,
          pct: data.avg_monthly_income > 0 ? (value / data.avg_monthly_income) * 100 : 0,
          color: s.color,
          category: s.category,
        }
      })
    const allocated = slices.reduce((sum, s) => sum + s.value, 0)
    const unallocated = Math.max(0, data.avg_monthly_income - allocated)
    if (unallocated > 0) {
      slices.push({ name: 'Unallocated', value: unallocated, pct: (unallocated / data.avg_monthly_income) * 100, color: UNALLOCATED_COLOR, category: '__unallocated__' })
    }
    return slices
  })() : []

  const hoveredSlice = activeSlice !== null ? pieData[activeSlice] : null

  return (
    <div className="glass-overlay fixed inset-0 z-50 flex items-center justify-center">
      <div className="glass-modal w-[820px] max-h-[88vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-[26px] py-[20px] border-b border-white/8">
          <div>
            <h3 className="text-[15px] font-semibold">Suggested budget breakdown</h3>
            {data && (
              <p className="text-[12px] text-ledger-text-faint mt-[2px]">
                ${fmt(data.avg_monthly_income)}/mo avg income · {data.months_sampled}-month history
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-ledger-text-faint hover:text-ledger-text-primary">
            <X className="w-[16px] h-[16px]" />
          </button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-ledger-text-faint text-[13px]">
            Analysing your income and spending…
          </div>
        ) : error && !data ? (
          <div className="flex-1 flex items-center justify-center text-ledger-negative text-[13px]">{error}</div>
        ) : data ? (
          <div className="flex flex-1 overflow-hidden">
            {/* Pie chart */}
            <div className="flex flex-col items-center justify-center w-[320px] flex-shrink-0 py-[24px] border-r border-white/8">
              <div className="relative w-[230px] h-[230px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%" cy="50%"
                      innerRadius={68} outerRadius={102}
                      paddingAngle={2} dataKey="value"
                      activeIndex={activeSlice ?? undefined}
                      activeShape={(props: any) => <Sector {...props} outerRadius={props.outerRadius + 5} style={{ outline: 'none' }} />}
                      onMouseEnter={(_, i) => setActiveSlice(i)}
                      onMouseLeave={() => setActiveSlice(null)}
                      style={{ outline: 'none' }}
                    >
                      {pieData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} style={{ outline: 'none', cursor: 'default' }} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                {/* Center label */}
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  {hoveredSlice ? (
                    <>
                      <span className="text-[11px] text-ledger-text-faint w-[90px] text-center leading-tight break-words">{hoveredSlice.name}</span>
                      <span className="text-[18px] font-bold tabular-nums mt-[2px]">{hoveredSlice.pct.toFixed(0)}%</span>
                      <span className="text-[11px] text-ledger-text-faint tabular-nums">${fmt(hoveredSlice.value)}</span>
                    </>
                  ) : (
                    <>
                      <span className="text-[10px] text-ledger-text-faintest">allocated</span>
                      <span className="text-[17px] font-bold tabular-nums">
                        {data.avg_monthly_income > 0
                          ? `${Math.round((pieData.filter(s => s.category !== '__unallocated__').reduce((a, s) => a + s.value, 0) / data.avg_monthly_income) * 100)}%`
                          : '—'}
                      </span>
                      <span className="text-[10px] text-ledger-text-faintest">of income</span>
                    </>
                  )}
                </div>
              </div>
              <div className="mt-[14px] text-center">
                <div className="text-[11px] text-ledger-text-faintest">Savings target</div>
                <div className="text-[14px] font-bold tabular-nums text-ledger-positive mt-[1px]">
                  {data.avg_monthly_income > 0
                    ? `$${fmt(Math.max(0, data.avg_monthly_income - pieData.filter(s => s.category !== '__unallocated__').reduce((a, s) => a + s.value, 0)))}`
                    : '—'}
                </div>
              </div>
            </div>

            {/* Category list */}
            <div className="soft-scrollbar flex-1 overflow-y-auto py-[16px] px-[20px]">
              <div className="flex flex-col gap-[6px]">
                {data.suggestions.map((s) => {
                  const isSelected = selected.has(s.category)
                  const currentAmt = Math.max(0, parseFloat(amounts[s.category] ?? String(s.suggested)) || 0)
                  const pct = data.avg_monthly_income > 0 ? (currentAmt / data.avg_monthly_income) * 100 : 0
                  const sliderMax = Math.max(Math.ceil(s.suggested * 2 / 50) * 50, Math.ceil(s.actual_avg * 2 / 50) * 50, 200)
                  const sliderPct = Math.min((currentAmt / sliderMax) * 100, 100)
                  const avgPct = s.actual_avg > 0 ? Math.min((s.actual_avg / sliderMax) * 100, 100) : 0
                  const pieIdx = pieData.findIndex(p => p.category === s.category)
                  const isHovered = activeSlice === pieIdx && pieIdx !== -1
                  return (
                    <div
                      key={s.category}
                      onMouseEnter={() => pieIdx !== -1 && setActiveSlice(pieIdx)}
                      onMouseLeave={() => setActiveSlice(null)}
                      className={`w-full rounded-[9px] border px-[12px] py-[10px] transition-all ${
                        isHovered ? 'border-ledger-accent/60 bg-ledger-inset' :
                        isSelected ? 'border-ledger-border-subtle bg-ledger-inset/60' :
                        'border-transparent bg-transparent opacity-40'
                      }`}
                    >
                      <div className="flex items-center gap-[9px]">
                        {/* Checkbox — only toggle target */}
                        <button
                          onClick={() => toggle(s.category)}
                          className="w-[15px] h-[15px] rounded-[4px] border flex-shrink-0 flex items-center justify-center transition-colors"
                          style={{
                            backgroundColor: isSelected ? s.color : 'transparent',
                            borderColor: isSelected ? s.color : CHART_SURFACE.borderStrong,
                          }}
                        >
                          {isSelected && (
                            <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                              <path d="M1.5 4L3.2 5.8L6.5 2.2" stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          )}
                        </button>
                        <span className="text-[13px] font-medium flex-1">{s.label}</span>
                        <span className="text-[12px] text-ledger-text-faint tabular-nums w-[32px] text-right">{pct.toFixed(0)}%</span>
                        <div className="flex items-center gap-[2px] flex-shrink-0">
                          <span className="text-[12px] text-ledger-text-faint">$</span>
                          <input
                            type="text"
                            inputMode="numeric"
                            value={amounts[s.category] ?? ''}
                            onChange={e => setAmount(s.category, e.target.value.replace(/[^0-9.]/g, ''))}
                            disabled={!isSelected}
                            className="w-[52px] bg-transparent border-b border-transparent hover:border-ledger-border-input focus:border-ledger-accent/60 text-[13px] font-semibold tabular-nums text-right focus:outline-none transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          />
                        </div>
                      </div>
                      {/* Interactive slider */}
                      <div className="mt-[6px] ml-[24px] flex items-center gap-[8px]">
                        <div className="flex-1 relative h-[16px] group/slider">
                          {/* Native range — invisible, handles all interaction */}
                          <input
                            type="range"
                            min={0}
                            max={sliderMax}
                            step={10}
                            value={currentAmt}
                            onChange={e => setAmount(s.category, e.target.value)}
                            disabled={!isSelected}
                            className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize disabled:cursor-not-allowed"
                          />
                          {/* Track */}
                          <div className="absolute inset-y-0 flex items-center w-full pointer-events-none">
                            <div className="w-full h-[3px] rounded-full bg-ledger-track">
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${sliderPct}%`, backgroundColor: isSelected ? s.color : CHART_SURFACE.borderStrong }}
                              />
                            </div>
                          </div>
                          {/* Avg marker tick */}
                          {avgPct > 0 && (
                            <div
                              className="absolute top-[3px] bottom-[3px] w-[1.5px] rounded-full pointer-events-none"
                              style={{ left: `${avgPct}%`, backgroundColor: CHART_TEXT.faintest }}
                            />
                          )}
                          {/* Thumb — only visible on hover */}
                          <div
                            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-[10px] h-[10px] rounded-full pointer-events-none opacity-0 group-hover/slider:opacity-100 transition-opacity duration-100"
                            style={{ left: `${sliderPct}%`, backgroundColor: isSelected ? s.color : CHART_SURFACE.borderStrong }}
                          />
                        </div>
                        {s.actual_avg > 0 && (
                          <span className="text-[10.5px] text-ledger-text-faintest tabular-nums whitespace-nowrap flex-shrink-0">
                            avg ${fmt(s.actual_avg)}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        ) : null}

        {/* Footer */}
        <div className="px-[26px] py-[14px] border-t border-white/8 flex items-center justify-between gap-[12px]">
          {error ? <p className="text-[12px] text-ledger-negative">{error}</p> : <span className="text-[12px] text-ledger-text-faint">{selected.size} of {data?.suggestions.length ?? 0} categories selected</span>}
          <button
            onClick={handleApply}
            disabled={applying || selected.size === 0}
            className="bg-ledger-accent text-ledger-accent-on rounded-[9px] px-[18px] py-[9px] font-semibold text-[13px] hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {applying ? 'Applying…' : `Apply ${selected.size} budget${selected.size !== 1 ? 's' : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}

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
                className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
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
                className="w-full glass-chip pl-[24px] pr-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
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
            className="mt-[4px] w-full bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] font-semibold text-[13px] hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Add budget'}
          </button>
        </div>
      </div>
    </div>
  )
}

const ONBOARDING_KEY = 'ledger_budgets_onboarded'

function OnboardingPrompt({ onSuggest, onDismiss }: { onSuggest: () => void; onDismiss: () => void }) {
  return (
    <div className="glass-overlay fixed inset-0 z-50 flex items-center justify-center">
      <div className="glass-modal w-[420px] p-[32px] flex flex-col items-center text-center">
        <div className="w-[48px] h-[48px] rounded-[14px] bg-ledger-accent/15 border border-ledger-accent/30 flex items-center justify-center mb-[18px]">
          <Sparkles className="w-[22px] h-[22px] text-ledger-accent" strokeWidth={1.6} />
        </div>
        <h3 className="text-[17px] font-bold mb-[8px]">Set up your budgets</h3>
        <p className="text-[13px] text-ledger-text-faint leading-relaxed mb-[24px]">
          Ledger can analyse your income and spending history to suggest a personalised monthly budget, or you can set one up manually.
        </p>
        <div className="flex flex-col gap-[10px] w-full">
          <button
            onClick={onSuggest}
            className="w-full bg-ledger-accent text-ledger-accent-on rounded-[10px] py-[11px] font-semibold text-[13px] hover:opacity-90 transition-opacity"
          >
            Suggest budgets from my income
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

export default function Budgets() {
  // Default to the current month so budgets set for "this month" (incl. ones
  // applied from the AI Advisor) are visible immediately.
  const [selectedMonth, setSelectedMonth] = useState(MONTH_OPTIONS[0].value)
  const [data, setData] = useState<BudgetsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showSuggest, setShowSuggest] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [editing, setEditing] = useState<BudgetItem | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

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
        const remaining = prev.budgets.filter(b => b.id !== id)
        return {
          ...prev,
          budgets: remaining,
          total_limit: remaining.reduce((sum, b) => sum + b.limit, 0),
          total_spent: remaining.reduce((sum, b) => sum + b.spent, 0),
        }
      })
    } catch (e: any) {
      setDeleteError(e.message || 'Failed to remove budget')
      fetchBudgets()
    } finally {
      setDeletingId(null)
    }
  }

  const budgets = data?.budgets ?? []
  const totalBudget = data?.total_limit ?? 0
  const totalSpent = data?.total_spent ?? 0
  const remaining = totalBudget - totalSpent

  return (
    <div className="flex flex-col gap-[18px]">
      {showOnboarding && (
        <OnboardingPrompt
          onSuggest={() => {
            localStorage.setItem(ONBOARDING_KEY, '1')
            setShowOnboarding(false)
            setShowSuggest(true)
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
      {showSuggest && (
        <SuggestPanel
          month={selectedMonth}
          onClose={() => setShowSuggest(false)}
          onApplied={fetchBudgets}
        />
      )}

      {/* Summary bar */}
      <div className="glass-card p-[22px]">
        <div className="grid grid-cols-[1fr_1fr_1fr_auto_auto_auto] gap-[24px] items-center">
          <div>
            <div className="metric-label">Total budget</div>
            <div className="text-stat font-bold mt-[6px] font-mono text-ledger-text-heading">
              {loading ? '—' : `$${fmt(totalBudget)}`}
            </div>
          </div>
          <div>
            <div className="metric-label">Spent</div>
            <div className="text-stat font-bold mt-[6px] font-mono text-ledger-text-heading">
              {loading ? '—' : `$${fmt(totalSpent)}`}
            </div>
          </div>
          <div>
            <div className="metric-label">Remaining</div>
            <div className={`text-stat font-bold mt-[6px] font-mono ${remaining < 0 ? 'text-ledger-negative' : 'text-ledger-positive'}`}>
              {loading ? '—' : `$${fmt(Math.abs(remaining))}`}
            </div>
          </div>
          <select
            value={selectedMonth}
            onChange={e => setSelectedMonth(e.target.value)}
            className="glass-chip px-[10px] py-[8px] text-[13px] text-ledger-text-primary cursor-pointer focus:outline-none"
          >
            {MONTH_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            onClick={() => setShowSuggest(true)}
            className="flex items-center gap-[6px] glass-chip text-ledger-text-primary rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] hover:opacity-80 transition-opacity whitespace-nowrap"
          >
            <Sparkles className="w-[14px] h-[14px]" strokeWidth={1.8} />
            Suggest
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="bg-ledger-accent text-ledger-accent-on rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] hover:opacity-90 transition-opacity whitespace-nowrap"
          >
            + Add budget
          </button>
        </div>
      </div>

      {deleteError && (
        <div className="glass-card px-[16px] py-[12px] text-[13px] text-ledger-negative">
          {deleteError}
        </div>
      )}

      {/* Cards */}
      {loading ? (
        <div className="text-center py-16 text-ledger-text-faint text-[13px]">Loading…</div>
      ) : budgets.length === 0 ? (
        <div className="glass-card p-[40px] text-center">
          <div className="text-[14px] font-semibold mb-[8px]">No budgets for this month</div>
          <div className="text-[13px] text-ledger-text-faint mb-[16px]">
            Click "+ Add budget" to set monthly spending limits by category.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-[18px]">
          {budgets.map((budget) => {
            const isVirtual = Boolean(budget.virtual)
            const pct = budget.limit > 0 ? (budget.spent / budget.limit) * 100 : (isVirtual ? 100 : 0)
            const isOver = !isVirtual && budget.spent > budget.limit

            return (
              <div key={budget.id} className="glass-card p-[18px]">
                <div className="flex items-center gap-[10px] mb-[12px]">
                  <span className="w-[10px] h-[10px] rounded-[3px] flex-shrink-0" style={{ backgroundColor: budget.color }} />
                  <span className="text-title font-semibold flex-1 truncate">{formatCategory(budget.category)}</span>
                  {isVirtual
                    ? <span className="text-ledger-text-muted text-[11px] px-[6px] py-[2px] rounded-[4px] bg-ledger-inset border border-ledger-border shrink-0">Unbudgeted</span>
                    : isOver
                      ? <span className="text-ledger-negative text-[11px] px-[6px] py-[2px] rounded-[4px] bg-ledger-negative-soft border border-ledger-negative-border shrink-0">Over</span>
                      : <span className="text-ledger-positive text-[11px] px-[6px] py-[2px] rounded-[4px] bg-ledger-positive-soft border border-ledger-positive-border shrink-0">On track</span>
                  }
                  {!isVirtual && (
                    <div className="flex items-center gap-[6px] shrink-0">
                      <button
                        type="button"
                        title="Edit budget"
                        onClick={() => { setConfirmingDeleteId(null); setEditing(budget) }}
                        className="p-[4px] text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
                      >
                        <Pencil className="w-[13px] h-[13px]" strokeWidth={2} />
                      </button>
                      <button
                        type="button"
                        title="Remove budget"
                        onClick={() => {
                          setDeleteError(null)
                          setConfirmingDeleteId(prev => prev === budget.id ? null : budget.id)
                        }}
                        disabled={deletingId === budget.id}
                        className="p-[4px] text-ledger-text-faint hover:text-ledger-negative transition-colors disabled:opacity-40"
                      >
                        <Trash2 className="w-[13px] h-[13px]" strokeWidth={2} />
                      </button>
                    </div>
                  )}
                </div>

                {!isVirtual && confirmingDeleteId === budget.id && (
                  <div className="flex items-center justify-between gap-[10px] mb-[12px] px-[10px] py-[8px] rounded-[8px] border border-ledger-border-subtle bg-ledger-inset/60">
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

                <div className="text-[15px] font-bold mb-[9px] font-mono">
                  {isVirtual ? (
                    <>${fmt(budget.spent)}</>
                  ) : (
                    <>
                      ${fmt(budget.spent)} <span className="text-ledger-text-faint font-normal">/ ${fmt(budget.limit)}</span>
                    </>
                  )}
                </div>

                <div className="h-[7px] rounded-[4px] bg-ledger-track overflow-hidden mb-[10px]">
                  <div
                    className="h-full rounded-[4px] transition-all"
                    style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: isOver ? CHART_NEGATIVE : CHART_ACCENT }}
                  />
                </div>

                <div className="text-[11.5px] text-ledger-text-faint">
                  {isVirtual
                    ? 'Outside tracked categories'
                    : isOver
                      ? `$${fmt(budget.spent - budget.limit)} over budget`
                      : `$${fmt(budget.limit - budget.spent)} remaining`}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
