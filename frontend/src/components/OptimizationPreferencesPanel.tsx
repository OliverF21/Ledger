import { useState } from 'react'
import { X } from 'lucide-react'
import {
  useSectorConstraints, useTickerConstraints,
  type OptimizationSettings, type SectorConstraint,
} from '../hooks/useInvestments'

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

// `referenceValue` renders a small static tick on the track (e.g. an S&P 500
// sector weight) purely as a visual anchor -- it never affects `value` and
// nothing is persisted from it. Dragging still only writes `value`.
function RangeSlider({ label, value, min, max, step, onChange, referenceValue, referenceLabel }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void
  referenceValue?: number; referenceLabel?: string
}) {
  const pct = ((value - min) / (max - min)) * 100
  const refPct = referenceValue !== undefined ? ((referenceValue - min) / (max - min)) * 100 : null
  return (
    <div className="group/slider">
      <div className="flex justify-between text-[11px] text-ledger-text-secondary mb-[2px]">
        <span>{label}</span><span>{value}%</span>
      </div>
      <div className="relative h-[3px] rounded-full bg-ledger-track">
        <div className="absolute h-full rounded-full bg-ledger-accent" style={{ width: `${pct}%` }} />
        {refPct !== null && (
          <div
            title={referenceLabel ?? `Reference: ~${referenceValue}%`}
            className="absolute top-1/2 w-[2px] h-[9px] -translate-y-1/2 bg-ledger-text-faint/70 rounded-full pointer-events-none"
            style={{ left: `${refPct}%` }}
          />
        )}
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="absolute inset-0 w-full opacity-0 cursor-pointer"
        />
      </div>
    </div>
  )
}

// Real Yahoo/Morningstar equity sector taxonomy -- NOT generic GICS textbook
// names. TickerClassification.sector_weights_json keys come straight from
// yfinance's info["sector"] (app/sector_data_provider.py), normalized
// (lowercase, no spaces/underscores/hyphens). A grid using GICS-style labels
// ("Financials", "Consumer Discretionary", "Materials") would silently match
// no held ticker's classification -- the exact bug already fixed elsewhere
// in this codebase for free-typed sector names (see routes/optimization_settings.py's
// server-side sector normalization). `key` here must stay in that exact
// normalized form.
//
// sp500WeightPct values are a static, hand-set approximate snapshot for the
// on-slider reference marker only -- not live data, not persisted, and not
// refreshed automatically. They exist purely to give the user something
// concrete to drag away from, per the product ask.
const SECTORS: { key: string; label: string; sp500WeightPct: number }[] = [
  { key: 'technology', label: 'Technology', sp500WeightPct: 32 },
  { key: 'financialservices', label: 'Financial Services', sp500WeightPct: 14 },
  { key: 'healthcare', label: 'Healthcare', sp500WeightPct: 10 },
  { key: 'consumercyclical', label: 'Consumer Cyclical', sp500WeightPct: 10 },
  { key: 'communicationservices', label: 'Communication Services', sp500WeightPct: 9 },
  { key: 'industrials', label: 'Industrials', sp500WeightPct: 8 },
  { key: 'consumerdefensive', label: 'Consumer Defensive', sp500WeightPct: 6 },
  { key: 'energy', label: 'Energy', sp500WeightPct: 3 },
  { key: 'utilities', label: 'Utilities', sp500WeightPct: 2.5 },
  { key: 'realestate', label: 'Real Estate', sp500WeightPct: 2 },
  { key: 'basicmaterials', label: 'Basic Materials', sp500WeightPct: 2 },
]

// Tickers have no existing search/entry convention elsewhere in this app --
// they're only ever displayed (sourced from synced holdings), never manually
// typed. Backend ticker-constraint matching is an exact string match against
// synced ticker symbols (build_ticker_bounds in sector_constraint_service.py),
// which are uppercase (e.g. "VOO", "AAPL"). Uppercase-on-blur keeps
// user-typed input consistent with that without being intrusive while typing.
function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase()
}

// One existing ticker constraint: name chip + floor/cap slider pair + remove
// button. Sectors no longer use this -- they're a fixed, always-shown grid
// (see SectorConstraintsGrid below) -- but tickers aren't a fixed enumerable
// set the way sectors are, so they keep the add/remove list.
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
// exactly (same border/spacing/Save-Cancel button styling). Ticker-only now.
function AddTickerConstraintForm({ onCreate }: {
  onCreate: (ticker: string, floorPct: number, capPct: number) => Promise<unknown>
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
    const normalized = normalizeTicker(name)
    if (!normalized) {
      setError('Enter a ticker')
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
        + Add ticker constraint
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
        onBlur={() => setName(prev => normalizeTicker(prev))}
        placeholder="e.g. VOO"
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

// Always renders all 11 sectors (SECTORS above), regardless of whether a
// SectorConstraint row exists for them. A sector with no row is fully
// unconstrained (matches sector_constraint_service.py's "absent = 0-100"
// rule exactly -- nothing changes server-side just from being shown here)
// and its sliders rest at 0/100 with only the S&P reference tick for
// context. The FIRST drag on an unconstrained sector creates a real
// constraint; subsequent drags update it. A "Reset" link (shown only once a
// real constraint exists) deletes the row, returning to the unconstrained
// resting state.
function SectorConstraintsGrid({ constraints, resettingId, onFloorChange, onCapChange, onReset }: {
  constraints: SectorConstraint[]
  resettingId: number | null
  onFloorChange: (sectorKey: string, existing: SectorConstraint | undefined, v: number) => void
  onCapChange: (sectorKey: string, existing: SectorConstraint | undefined, v: number) => void
  onReset: (existing: SectorConstraint) => void
}) {
  const bySector = new Map(constraints.map(c => [c.sector, c]))
  return (
    <div className="space-y-[6px]">
      {SECTORS.map(s => {
        const existing = bySector.get(s.key)
        const floorPct = existing?.floor_pct ?? 0
        const capPct = existing?.cap_pct ?? 100
        const referenceLabel = `S&P 500: ~${s.sp500WeightPct}%`
        return (
          <div key={s.key} className="border border-ledger-border-subtle rounded-[8px] p-[8px]">
            <div className="flex items-center justify-between gap-[8px] mb-[5px]">
              <span className="text-[11.5px] font-medium text-ledger-text-primary">{s.label}</span>
              <div className="flex items-center gap-[8px] shrink-0">
                <span className="text-[10px] text-ledger-text-faintest">~{s.sp500WeightPct}%</span>
                {existing && (
                  <button
                    type="button"
                    disabled={resettingId === existing.id}
                    onClick={() => onReset(existing)}
                    className="text-[10px] font-semibold text-ledger-text-faint hover:text-ledger-negative transition-colors disabled:opacity-40"
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-[5px]">
              <RangeSlider
                label="Floor" value={floorPct} min={0} max={100} step={1}
                referenceValue={s.sp500WeightPct} referenceLabel={referenceLabel}
                onChange={v => onFloorChange(s.key, existing, v)}
              />
              <RangeSlider
                label="Cap" value={capPct} min={0} max={100} step={1}
                referenceValue={s.sp500WeightPct} referenceLabel={referenceLabel}
                onChange={v => onCapChange(s.key, existing, v)}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// The toggle and its settings (sliders, sector grid, ticker constraints) are
// owned here; the LIVE toggle value and its mutator come from the parent
// (Investments.tsx also needs `prefs.advanced_enabled` to decide whether to
// show the results section, so it owns the single useOptimizationPreferences
// instance rather than each side keeping its own copy that could drift).
//
// Settings/constraint edits persist immediately (PUT/POST/DELETE per drag or
// click) but do NOT trigger a re-optimization by themselves anymore -- only
// clicking "Run optimization" (onRun) does. Dragging a slider used to fire a
// full backend re-solve (two SLSQP objectives + a 20-point frontier sweep)
// on every tick of a native <input type="range">, which is many times per
// second while dragging; this also fixes that.
export default function OptimizationPreferencesPanel({ prefs, updatePrefs, onRun, running }: {
  prefs: OptimizationSettings | null
  updatePrefs: (patch: Partial<OptimizationSettings>) => Promise<OptimizationSettings>
  onRun: () => void
  running: boolean
}) {
  const { data: sectorConstraints, create: createSector, update: updateSector, remove: removeSector } = useSectorConstraints()
  const { data: tickerConstraints, create: createTicker, update: updateTicker, remove: removeTicker } = useTickerConstraints()
  const [resettingSectorId, setResettingSectorId] = useState<number | null>(null)
  const [removingTickerId, setRemovingTickerId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Every mutation in this panel routes through here so failures are always
  // visible (previously: console.error only, so e.g. dragging an existing
  // constraint's floor above its own cap -- which the backend correctly
  // rejects with 422 -- silently did nothing from the user's perspective).
  const runMutation = async <T,>(mutation: Promise<T>, fallbackMessage: string): Promise<T | undefined> => {
    try {
      const result = await mutation
      setError(null)
      return result
    } catch (err) {
      setError(err instanceof Error ? err.message : fallbackMessage)
      return undefined
    }
  }

  if (!prefs) return null

  const handleSectorFloorChange = (sectorKey: string, existing: SectorConstraint | undefined, v: number) =>
    runMutation(
      existing
        ? updateSector(existing.id, { sector: sectorKey, floor_pct: v, cap_pct: existing.cap_pct })
        : createSector({ sector: sectorKey, floor_pct: v, cap_pct: 100 }),
      'Failed to update sector constraint',
    )

  const handleSectorCapChange = (sectorKey: string, existing: SectorConstraint | undefined, v: number) =>
    runMutation(
      existing
        ? updateSector(existing.id, { sector: sectorKey, floor_pct: existing.floor_pct, cap_pct: v })
        : createSector({ sector: sectorKey, floor_pct: 0, cap_pct: v }),
      'Failed to update sector constraint',
    )

  const handleResetSector = async (existing: SectorConstraint) => {
    setResettingSectorId(existing.id)
    await runMutation(removeSector(existing.id), 'Failed to reset sector constraint')
    setResettingSectorId(null)
  }

  const handleRemoveTicker = async (id: number) => {
    setRemovingTickerId(id)
    await runMutation(removeTicker(id), 'Failed to remove ticker constraint')
    setRemovingTickerId(null)
  }

  return (
    <div className="glass-card p-[13px]">
      <div className="flex items-center justify-between mb-[3px]">
        <div className="text-[13px] text-ledger-text-primary font-medium">Advanced optimization</div>
        <Toggle enabled={prefs.advanced_enabled} onToggle={() => runMutation(
          updatePrefs({ advanced_enabled: !prefs.advanced_enabled }),
          'Failed to update optimization preferences',
        )} />
      </div>
      {prefs.advanced_enabled && (
        <div className="space-y-[10px] mt-[10px]">
          {error && (
            <div className="text-[11.5px] text-ledger-negative bg-[rgba(231,112,95,0.1)] border border-ledger-negative/30 rounded-[7px] px-[9px] py-[6px]">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-[10px]">
            <RangeSlider label="Position cap" value={prefs.position_cap_pct} min={2} max={50} step={1}
              onChange={v => runMutation(
                updatePrefs({ position_cap_pct: v }), 'Failed to update optimization preferences',
              )} />
            <RangeSlider label="Diversification" value={prefs.concentration_strength * 100} min={0} max={100} step={5}
              onChange={v => runMutation(
                updatePrefs({ concentration_strength: v / 100 }), 'Failed to update optimization preferences',
              )} />
          </div>

          <div>
            <div className="text-[11.5px] font-semibold text-ledger-text-primary mb-[6px]">
              Sector constraints <span className="font-normal text-ledger-text-faint">— S&P 500 weight marked for reference</span>
            </div>
            {/* Capped height + internal scroll rather than letting 11 sectors push
                this column's height far past the chart column beside it -- see
                Investments.tsx's two-column layout comment. */}
            <div className="max-h-[280px] overflow-y-auto pr-[4px] -mr-[4px]">
              <SectorConstraintsGrid
                constraints={sectorConstraints}
                resettingId={resettingSectorId}
                onFloorChange={handleSectorFloorChange}
                onCapChange={handleSectorCapChange}
                onReset={handleResetSector}
              />
            </div>
          </div>

          <div>
            <div className="text-[11.5px] font-semibold text-ledger-text-primary mb-[6px]">Ticker constraints</div>
            {tickerConstraints.length === 0 ? (
              <div className="text-center py-3 text-ledger-text-faint text-[11.5px] mb-[8px]">
                No ticker constraints yet.
              </div>
            ) : (
              <div className="space-y-[6px] mb-[8px] max-h-[160px] overflow-y-auto pr-[4px] -mr-[4px]">
                {tickerConstraints.map(c => (
                  <ConstraintRow
                    key={c.id}
                    name={c.ticker}
                    floorPct={c.floor_pct}
                    capPct={c.cap_pct}
                    removing={removingTickerId === c.id}
                    onFloorChange={v => runMutation(
                      updateTicker(c.id, { ticker: c.ticker, floor_pct: v, cap_pct: c.cap_pct }),
                      'Failed to update ticker constraint',
                    )}
                    onCapChange={v => runMutation(
                      updateTicker(c.id, { ticker: c.ticker, floor_pct: c.floor_pct, cap_pct: v }),
                      'Failed to update ticker constraint',
                    )}
                    onRemove={() => handleRemoveTicker(c.id)}
                  />
                ))}
              </div>
            )}
            <AddTickerConstraintForm
              onCreate={(ticker, floor_pct, cap_pct) => createTicker({ ticker, floor_pct, cap_pct })}
            />
          </div>

          <button
            type="button"
            onClick={onRun}
            disabled={running}
            className="w-full bg-ledger-accent text-ledger-accent-on rounded-[8px] py-[9px] text-[12.5px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {running ? 'Running optimization…' : 'Run optimization'}
          </button>
        </div>
      )}
    </div>
  )
}
