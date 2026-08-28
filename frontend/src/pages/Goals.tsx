import { useState, useEffect } from 'react'
import { Pencil, Trash2, Target } from 'lucide-react'
import { apiFetch } from '../api/client'

interface GoalItem {
  id: number
  name: string
  kind: string
  kind_label: string
  target_amount: number
  opening_amount: number
  labeled_in: number
  labeled_out: number
  progress: number
  remaining: number
  monthly_contribution: number | null
  annual_return: number
  target_date: string | null
  status: string
  color: string
  months_remaining: number | null
  projected_end_month: string | null
  percent_funded: number
}

const KIND_OPTIONS = [
  { value: 'emergency_fund', label: 'Emergency fund' },
  { value: 'sinking_fund', label: 'Sinking fund' },
  { value: 'debt_payoff', label: 'Debt payoff' },
  { value: 'invest', label: 'Invest' },
  { value: 'custom', label: 'Custom' },
]

const PALETTE = [
  '#82a9f2', '#63cfcc', '#a196fa', '#74d8a8', '#e6bd79',
  '#f4907f', '#95c8ff', '#adb8cb', '#b6ebcd', '#c4b5fd',
]

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function money0(n: number | null | undefined) {
  if (n === null || n === undefined) return '—'
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

interface GoalModalProps {
  editing: GoalItem | null
  onClose: () => void
  onSaved: () => void
}

function GoalModal({ editing, onClose, onSaved }: GoalModalProps) {
  const [name, setName] = useState(editing?.name ?? '')
  const [kind, setKind] = useState(editing?.kind ?? 'sinking_fund')
  const [target, setTarget] = useState(editing ? String(Math.round(editing.target_amount)) : '')
  const [opening, setOpening] = useState(editing ? String(Math.round(editing.opening_amount)) : '0')
  const [pmt, setPmt] = useState(
    editing?.monthly_contribution != null ? String(Math.round(editing.monthly_contribution)) : '',
  )
  const [targetDate, setTargetDate] = useState(editing?.target_date ?? '')
  const [annualReturn, setAnnualReturn] = useState(
    editing && editing.annual_return > 0 ? String(Math.round(editing.annual_return * 1000) / 10) : '0',
  )
  const [color, setColor] = useState(editing?.color ?? PALETTE[0])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    const trimmed = name.trim()
    const targetAmt = parseFloat(target)
    if (!trimmed || !Number.isFinite(targetAmt) || targetAmt <= 0) {
      setError('Name and a target greater than $0 are required.')
      return
    }
    const openingAmt = parseFloat(opening) || 0
    const pmtAmt = pmt.trim() === '' ? null : parseFloat(pmt)
    const rPct = parseFloat(annualReturn) || 0
    setSaving(true)
    setError(null)
    try {
      const body = {
        name: trimmed,
        kind,
        target_amount: targetAmt,
        current_amount: Math.max(0, openingAmt),
        monthly_contribution: pmtAmt != null && Number.isFinite(pmtAmt) ? pmtAmt : null,
        target_date: targetDate.trim() || null,
        annual_return_assumption: Math.min(0.12, Math.max(0, rPct / 100)),
        status: editing?.status ?? 'active',
        color,
      }
      const res = await apiFetch(editing ? `/api/goals/${editing.id}` : '/api/goals', {
        method: editing ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const json = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(json.detail || 'Failed to save goal')
      onSaved()
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save goal')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="glass-overlay fixed inset-0 z-50 flex items-center justify-center">
      <div className="glass-modal w-[420px] max-h-[88vh] overflow-auto p-[26px] flex flex-col gap-[14px]">
        <div className="flex items-center justify-between">
          <h3 className="text-[15px] font-semibold">{editing ? 'Edit goal' : 'New goal'}</h3>
          <button onClick={onClose} className="text-[12px] text-ledger-text-faint hover:text-ledger-text-primary">
            Close
          </button>
        </div>
        <div>
          <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Emergency fund, Vacation…"
            className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-white/60"
          />
        </div>
        <div>
          <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Kind</label>
          <select
            value={kind}
            onChange={e => setKind(e.target.value)}
            className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary focus:outline-none"
          >
            {KIND_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-[12px]">
          <div>
            <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Target</label>
            <div className="relative">
              <span className="absolute left-[12px] top-1/2 -translate-y-1/2 text-[13px] text-ledger-text-faint">$</span>
              <input
                type="number"
                min="0"
                step="100"
                value={target}
                onChange={e => setTarget(e.target.value)}
                className="w-full glass-chip pl-[24px] pr-[12px] py-[8px] text-[13px] text-ledger-text-primary focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Opening amount</label>
            <div className="relative">
              <span className="absolute left-[12px] top-1/2 -translate-y-1/2 text-[13px] text-ledger-text-faint">$</span>
              <input
                type="number"
                min="0"
                step="50"
                value={opening}
                onChange={e => setOpening(e.target.value)}
                className="w-full glass-chip pl-[24px] pr-[12px] py-[8px] text-[13px] text-ledger-text-primary focus:outline-none"
              />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-[12px]">
          <div>
            <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Planned $/mo</label>
            <div className="relative">
              <span className="absolute left-[12px] top-1/2 -translate-y-1/2 text-[13px] text-ledger-text-faint">$</span>
              <input
                type="number"
                min="0"
                step="10"
                value={pmt}
                onChange={e => setPmt(e.target.value)}
                placeholder="optional"
                className="w-full glass-chip pl-[24px] pr-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Assumed return %</label>
            <input
              type="number"
              min="0"
              max="12"
              step="0.1"
              value={annualReturn}
              onChange={e => setAnnualReturn(e.target.value)}
              className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary focus:outline-none"
            />
          </div>
        </div>
        <div>
          <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Target date</label>
          <input
            type="date"
            value={targetDate}
            onChange={e => setTargetDate(e.target.value)}
            className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary focus:outline-none"
          />
        </div>
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
        {error && <p className="text-[12px] text-ledger-negative">{error}</p>}
        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-[4px] w-full bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] font-semibold text-[13px] hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {saving ? 'Saving…' : editing ? 'Save changes' : 'Add goal'}
        </button>
      </div>
    </div>
  )
}

export default function Goals() {
  const [goals, setGoals] = useState<GoalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<GoalItem | null>(null)
  const [confirmingId, setConfirmingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchGoals = () => {
    setLoading(true)
    apiFetch('/api/goals')
      .then(r => r.json())
      .then(d => setGoals(d.goals ?? []))
      .catch(() => setGoals([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchGoals() }, [])

  const dismiss = async (id: number) => {
    setError(null)
    try {
      const res = await apiFetch(`/api/goals/${id}`, { method: 'DELETE' })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Failed to dismiss goal')
      }
      setConfirmingId(null)
      setGoals(prev => prev.filter(g => g.id !== id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to dismiss goal')
    }
  }

  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0)
  const totalProgress = goals.reduce((sum, g) => sum + g.progress, 0)

  return (
    <div className="flex flex-col gap-[18px]">
      {(showModal || editing) && (
        <GoalModal
          editing={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSaved={fetchGoals}
        />
      )}

      <div className="glass-card p-[22px]">
        <div className="grid grid-cols-[1fr_1fr_auto] gap-[24px] items-center">
          <div>
            <div className="text-[12.5px] text-ledger-text-faint">Labeled progress</div>
            <div className="text-[25px] font-bold mt-[6px] tabular-nums">
              {loading ? '—' : `$${fmt(totalProgress)}`}
            </div>
          </div>
          <div>
            <div className="text-[12.5px] text-ledger-text-faint">Combined targets</div>
            <div className="text-[25px] font-bold mt-[6px] tabular-nums">
              {loading ? '—' : `$${fmt(totalTarget)}`}
            </div>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="bg-ledger-accent text-ledger-accent-on rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] hover:opacity-90 transition-opacity whitespace-nowrap"
          >
            + Add goal
          </button>
        </div>
        <p className="text-[12px] text-ledger-text-faint mt-[12px] leading-[1.5]">
          Progress is opening balance plus transfers you label — not leftover income, and not a spend budget.
          Label transfers on the Transactions page; labeled amounts also show as named Cash Flow sinks.
        </p>
      </div>

      {error && (
        <div className="glass-card p-[14px] text-[12.5px] text-ledger-negative">{error}</div>
      )}

      {loading ? (
        <div className="text-center py-10 text-ledger-text-faint text-[13px]">Loading…</div>
      ) : goals.length === 0 ? (
        <div className="glass-card p-[36px] text-center">
          <Target className="w-[24px] h-[24px] text-ledger-text-faint mx-auto mb-[10px]" strokeWidth={1.8} />
          <div className="text-[14px] font-semibold mb-[8px]">No goals yet</div>
          <div className="text-[13px] text-ledger-text-faint leading-[1.5]">
            Add an emergency fund or sinking fund, or ask Claude to propose one from your surplus.
            Applied Advisor goals land here.
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-[12px]">
          {goals.map(g => {
            const pct = Math.min(100, Math.max(0, g.percent_funded))
            return (
              <div key={g.id} className="glass-card p-[18px]">
                <div className="flex items-start gap-[14px]">
                  <div
                    className="w-[10px] h-[10px] rounded-full mt-[6px] flex-shrink-0"
                    style={{ backgroundColor: g.color }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-[8px] mb-[6px] flex-wrap">
                      <span className="text-[15px] font-semibold">{g.name}</span>
                      <span className="text-[10px] uppercase tracking-widest glass-chip px-[8px] py-[2px] rounded-[6px] text-ledger-text-muted">
                        {g.kind_label}
                      </span>
                    </div>
                    <div className="h-[8px] rounded-full bg-ledger-inset overflow-hidden mb-[10px]">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${pct}%`, backgroundColor: g.color }}
                      />
                    </div>
                    <div className="flex flex-wrap gap-x-[18px] gap-y-[6px] text-[12.5px] text-ledger-text-faint">
                      <span>
                        <span className="text-ledger-text-secondary tabular-nums">{money0(g.progress)}</span>
                        {' '}of {money0(g.target_amount)}
                        <span className="text-ledger-text-faintest"> · {pct}%</span>
                      </span>
                      {g.monthly_contribution != null && (
                        <span>{money0(g.monthly_contribution)}/mo planned</span>
                      )}
                      {g.months_remaining != null && g.remaining > 0 && (
                        <span>
                          {g.months_remaining} mo remaining
                          {g.projected_end_month ? ` · ${g.projected_end_month}` : ''}
                        </span>
                      )}
                      {g.remaining <= 0 && (
                        <span className="text-ledger-positive">Funded</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-[6px] flex-shrink-0">
                    <button
                      title="Edit"
                      onClick={() => setEditing(g)}
                      className="p-[7px] rounded-[7px] glass-chip text-ledger-text-muted hover:text-ledger-text-heading"
                    >
                      <Pencil className="w-[13px] h-[13px]" strokeWidth={2} />
                    </button>
                    {confirmingId === g.id ? (
                      <button
                        onClick={() => dismiss(g.id)}
                        className="px-[10px] py-[7px] rounded-[7px] text-[12px] font-semibold bg-ledger-negative/20 text-ledger-negative"
                      >
                        Dismiss?
                      </button>
                    ) : (
                      <button
                        title="Dismiss"
                        onClick={() => setConfirmingId(g.id)}
                        className="p-[7px] rounded-[7px] glass-chip text-ledger-text-muted hover:text-ledger-negative"
                      >
                        <Trash2 className="w-[13px] h-[13px]" strokeWidth={2} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
