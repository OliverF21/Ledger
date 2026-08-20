import { useState } from 'react'
import { X } from 'lucide-react'
import { useOptimizationPreferences, useSectorConstraints, useTickerConstraints } from '../hooks/useInvestments'

function Toggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`w-[40px] h-[23px] rounded-full relative cursor-pointer transition-colors ${enabled ? 'bg-ledger-accent' : 'bg-[#23262f]'}`}
    >
      <div className={`w-[17px] h-[17px] rounded-full absolute top-[3px] transition-all ${enabled ? 'bg-ledger-accent-on right-[3px]' : 'bg-ledger-text-faint left-[3px]'}`} />
    </button>
  )
}

function RangeSlider({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="group/slider">
      <div className="flex justify-between text-[12px] text-ledger-text-secondary mb-[4px]">
        <span>{label}</span><span>{value}%</span>
      </div>
      <div className="relative h-[3px] rounded-full bg-ledger-track">
        <div className="absolute h-full rounded-full bg-ledger-accent" style={{ width: `${pct}%` }} />
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="absolute inset-0 w-full opacity-0 cursor-pointer"
        />
      </div>
    </div>
  )
}

// Mirrors backend `_norm_sector_name` (backend/app/sector_data_provider.py)
// EXACTLY: lowercase, then strip underscores, spaces, and hyphens. Real
// sector keys derived from held tickers' classification data are normalized
// this way before they're ever stored in TickerClassification.sector_weights_json.
// SectorConstraint.sector, by contrast, is stored completely as-is by the
// CRUD API (routes/optimization_settings.py) -- no server-side normalization
// is ever applied to it. So a constraint whose sector isn't already in this
// normalized form will silently never match any held ticker's sector (see
// sector_constraint_service.clip_sector_bounds, which looks constraints up
// by exact `sector` string equality) -- normalize client-side before
// create/update so any reasonable casing/spacing the user types actually
// works, instead of quietly doing nothing.
function normalizeSectorName(raw: string): string {
  return raw.toLowerCase().replace(/_/g, '').replace(/ /g, '').replace(/-/g, '')
}

// Tickers have no existing search/entry convention elsewhere in this app --
// they're only ever displayed (sourced from synced holdings), never manually
// typed. Backend ticker-constraint matching is an exact string match against
// synced ticker symbols (build_ticker_bounds in sector_constraint_service.py),
// which are uppercase (e.g. "VOO", "AAPL"). Uppercase-on-blur keeps
// user-typed input consistent with that without being intrusive while typing.
function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase()
}

// One existing constraint: name chip + floor/cap slider pair + remove button.
// Mirrors the glass-chip row styling and hover-revealed icon-button
// convention used by Settings.tsx's categorization-rules list.
function ConstraintRow({ name, floorPct, capPct, removing, onFloorChange, onCapChange, onRemove }: {
  name: string
  floorPct: number
  capPct: number
  removing: boolean
  onFloorChange: (v: number) => void
  onCapChange: (v: number) => void
  onRemove: () => void
}) {
  return (
    <div className="border border-ledger-border-subtle rounded-[9px] p-[12px] group">
      <div className="flex items-start justify-between gap-[10px] mb-[10px]">
        <span className="glass-chip px-[10px] py-[7px] text-[12px] text-ledger-text-primary font-medium truncate">
          {name}
        </span>
        <button
          type="button"
          title="Remove constraint"
          onClick={onRemove}
          disabled={removing}
          className="text-ledger-text-faint hover:text-ledger-negative transition-colors disabled:opacity-40 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
        >
          <X className="w-[14px] h-[14px]" strokeWidth={2} />
        </button>
      </div>
      <div className="space-y-[10px]">
        <RangeSlider label="Floor" value={floorPct} min={0} max={100} step={1} onChange={onFloorChange} />
        <RangeSlider label="Cap" value={capPct} min={0} max={100} step={1} onChange={onCapChange} />
      </div>
    </div>
  )
}

// Small add-row form, collapsed to a "+ Add ... constraint" glass-chip button
// until clicked -- mirrors Settings.tsx's "+ New rule" / rule-form pattern
// exactly (same border/spacing/Save-Cancel button styling).
function AddConstraintForm({ fieldLabel, placeholder, transform, onCreate }: {
  fieldLabel: string
  placeholder: string
  transform: (raw: string) => string
  onCreate: (name: string, floorPct: number, capPct: number) => Promise<unknown>
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [floor, setFloor] = useState(0)
  const [cap, setCap] = useState(100)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resetForm = () => {
    setName('')
    setFloor(0)
    setCap(100)
    setError(null)
  }

  const handleCancel = () => {
    setOpen(false)
    resetForm()
  }

  const handleCreate = async () => {
    const normalized = transform(name)
    if (!normalized) {
      setError(`Enter a ${fieldLabel.toLowerCase()}`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onCreate(normalized, floor, cap)
      setOpen(false)
      resetForm()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create constraint')
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full glass-chip px-[12px] py-[8px] text-[13px] font-semibold text-ledger-text-primary hover:bg-[#161a21] transition-colors"
      >
        + Add {fieldLabel.toLowerCase()} constraint
      </button>
    )
  }

  return (
    <div className="border border-ledger-border-subtle rounded-[9px] p-[12px] space-y-[10px]">
      <input
        autoFocus
        type="text"
        value={name}
        onChange={e => setName(e.target.value)}
        onBlur={() => setName(prev => transform(prev))}
        placeholder={placeholder}
        className="w-full glass-chip px-[10px] py-[6px] text-[12px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
      />
      <RangeSlider label="Floor" value={floor} min={0} max={100} step={1} onChange={setFloor} />
      <RangeSlider label="Cap" value={cap} min={0} max={100} step={1} onChange={setCap} />
      {error && <p className="text-[11.5px] text-ledger-negative">{error}</p>}
      <div className="flex gap-[8px]">
        <button
          onClick={handleCreate}
          disabled={saving}
          className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[7px] py-[7px] text-[12.5px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={handleCancel}
          className="px-[14px] rounded-[7px] border border-ledger-border-input text-[12.5px] text-ledger-text-secondary hover:bg-ledger-inset transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// `onChange` fires after every successful mutation this panel makes. The
// panel writes through /optimization-settings and the constraint endpoints,
// but the advanced-mode view around it (frontier chart, per-objective
// comparison, clip-log banner) is driven by a SEPARATE /optimize response --
// including its own `advanced_enabled` field, which is what actually gates
// that view. Investments.tsx wires this to useInvestmentsOptimization's
// refetch so those results follow the panel instead of staying on the
// pre-edit snapshot until a page reload.
export default function OptimizationPreferencesPanel({ onChange }: { onChange?: () => void } = {}) {
  const { data: prefs, update } = useOptimizationPreferences()
  const { data: sectorConstraints, create: createSector, update: updateSector, remove: removeSector } = useSectorConstraints()
  const { data: tickerConstraints, create: createTicker, update: updateTicker, remove: removeTicker } = useTickerConstraints()
  const [removingSectorId, setRemovingSectorId] = useState<number | null>(null)
  const [removingTickerId, setRemovingTickerId] = useState<number | null>(null)

  // Wraps a mutation so onChange runs only after it actually succeeded --
  // a rejected write leaves the backend unchanged, so re-running /optimize
  // would just re-fetch identical results. Failures keep the existing
  // console.error handling.
  const notifyOnSuccess = async <T,>(mutation: Promise<T>, failureMessage: string): Promise<T | undefined> => {
    try {
      const result = await mutation
      onChange?.()
      return result
    } catch (err) {
      console.error(failureMessage, err)
      return undefined
    }
  }

  if (!prefs) return null

  const handleRemoveSector = async (id: number) => {
    setRemovingSectorId(id)
    try {
      await removeSector(id)
      onChange?.()
    } catch (err) {
      console.error('Failed to remove sector constraint:', err)
    } finally {
      setRemovingSectorId(null)
    }
  }

  const handleRemoveTicker = async (id: number) => {
    setRemovingTickerId(id)
    try {
      await removeTicker(id)
      onChange?.()
    } catch (err) {
      console.error('Failed to remove ticker constraint:', err)
    } finally {
      setRemovingTickerId(null)
    }
  }

  return (
    <div className="glass-card p-[16px]">
      <div className="flex items-center justify-between mb-[16px]">
        <span className="text-[14px] text-ledger-text-primary">Advanced optimization</span>
        <Toggle enabled={prefs.advanced_enabled} onToggle={() => notifyOnSuccess(
          update({ advanced_enabled: !prefs.advanced_enabled }),
          'Failed to update optimization preferences:',
        )} />
      </div>
      {prefs.advanced_enabled && (
        <div className="space-y-[16px]">
          <RangeSlider label="Position cap" value={prefs.position_cap_pct} min={2} max={50} step={1}
            onChange={v => notifyOnSuccess(
              update({ position_cap_pct: v }), 'Failed to update optimization preferences:',
            )} />
          <RangeSlider label="Diversification strength" value={prefs.concentration_strength * 100} min={0} max={100} step={5}
            onChange={v => notifyOnSuccess(
              update({ concentration_strength: v / 100 }), 'Failed to update optimization preferences:',
            )} />

          <div>
            <div className="text-[13px] font-semibold text-ledger-text-primary mb-[10px]">Sector constraints</div>
            {sectorConstraints.length === 0 ? (
              <div className="text-center py-6 text-ledger-text-faint text-[13px] mb-[12px]">
                No sector constraints yet. Set a floor/cap for a sector's total portfolio weight.
              </div>
            ) : (
              <div className="space-y-[8px] mb-[12px]">
                {sectorConstraints.map(c => (
                  <ConstraintRow
                    key={c.id}
                    name={c.sector}
                    floorPct={c.floor_pct}
                    capPct={c.cap_pct}
                    removing={removingSectorId === c.id}
                    onFloorChange={v => notifyOnSuccess(
                      updateSector(c.id, { sector: c.sector, floor_pct: v, cap_pct: c.cap_pct }),
                      'Failed to update sector constraint:',
                    )}
                    onCapChange={v => notifyOnSuccess(
                      updateSector(c.id, { sector: c.sector, floor_pct: c.floor_pct, cap_pct: v }),
                      'Failed to update sector constraint:',
                    )}
                    onRemove={() => handleRemoveSector(c.id)}
                  />
                ))}
              </div>
            )}
            <AddConstraintForm
              fieldLabel="Sector"
              placeholder="e.g. Technology"
              transform={normalizeSectorName}
              // Not wrapped in notifyOnSuccess: AddConstraintForm awaits this
              // and renders a rejection as an inline error under the form, so
              // the error must keep propagating rather than being swallowed
              // into console.error.
              onCreate={async (sector, floor_pct, cap_pct) => {
                const created = await createSector({ sector, floor_pct, cap_pct })
                onChange?.()
                return created
              }}
            />
          </div>

          <div>
            <div className="text-[13px] font-semibold text-ledger-text-primary mb-[10px]">Ticker constraints</div>
            {tickerConstraints.length === 0 ? (
              <div className="text-center py-6 text-ledger-text-faint text-[13px] mb-[12px]">
                No ticker constraints yet. Set a floor/cap for a specific ticker's portfolio weight.
              </div>
            ) : (
              <div className="space-y-[8px] mb-[12px]">
                {tickerConstraints.map(c => (
                  <ConstraintRow
                    key={c.id}
                    name={c.ticker}
                    floorPct={c.floor_pct}
                    capPct={c.cap_pct}
                    removing={removingTickerId === c.id}
                    onFloorChange={v => notifyOnSuccess(
                      updateTicker(c.id, { ticker: c.ticker, floor_pct: v, cap_pct: c.cap_pct }),
                      'Failed to update ticker constraint:',
                    )}
                    onCapChange={v => notifyOnSuccess(
                      updateTicker(c.id, { ticker: c.ticker, floor_pct: c.floor_pct, cap_pct: v }),
                      'Failed to update ticker constraint:',
                    )}
                    onRemove={() => handleRemoveTicker(c.id)}
                  />
                ))}
              </div>
            )}
            <AddConstraintForm
              fieldLabel="Ticker"
              placeholder="e.g. VOO"
              transform={normalizeTicker}
              // Same as the sector form above -- errors must reach
              // AddConstraintForm's inline error state.
              onCreate={async (ticker, floor_pct, cap_pct) => {
                const created = await createTicker({ ticker, floor_pct, cap_pct })
                onChange?.()
                return created
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
