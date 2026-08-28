import { useMemo, useState } from 'react'
import {
  useOptimizerRun,
  type Bound,
  type OptimizationSuggestion,
  type RiskReturnPoint,
} from '../../hooks/useInvestments'
import { GlassCard, Chip, Slider, EmptyState, LoadingRow } from './primitives'

/* ── Efficient frontier ─────────────────────────────────────────────────── */

const CHART = { width: 760, height: 420, left: 56, right: 20, top: 20, bottom: 42 }

/**
 * Risk on x, return on y. Three layers, back to front: the faint cloud of
 * random portfolios (scale only — it ignores the user's constraints), the
 * constrained frontier with its fill, and the two suggested portfolios.
 */
function FrontierChart({ result }: { result: OptimizationSuggestion }) {
  const { width, height, left, right, top, bottom } = CHART
  const plotW = width - left - right
  const plotH = height - top - bottom

  const all: RiskReturnPoint[] = [
    ...result.scatter,
    ...result.frontier,
    ...(result.current_point ? [result.current_point] : []),
    ...(result.max_sharpe_point ? [result.max_sharpe_point] : []),
    ...(result.max_utility_point ? [result.max_utility_point] : []),
  ]
  if (all.length === 0) return null

  const volMax = Math.max(...all.map(p => p.volatility_pct)) * 1.08 || 1
  const retLo = Math.min(0, ...all.map(p => p.return_pct))
  const retHi = Math.max(...all.map(p => p.return_pct)) * 1.08 || 1

  const x = (vol: number) => left + (vol / volMax) * plotW
  const y = (ret: number) => top + (1 - (ret - retLo) / (retHi - retLo)) * plotH

  const line = result.frontier.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.volatility_pct).toFixed(1)} ${y(p.return_pct).toFixed(1)}`).join(' ')
  const area = result.frontier.length > 1
    ? `${line} L${x(result.frontier[result.frontier.length - 1].volatility_pct).toFixed(1)} ${height - bottom} L${x(result.frontier[0].volatility_pct).toFixed(1)} ${height - bottom} Z`
    : ''

  const yTicks = Array.from({ length: 5 }, (_, i) => retLo + ((retHi - retLo) * i) / 4)
  const xTicks = Array.from({ length: 5 }, (_, i) => (volMax * i) / 4)

  const markers = [
    { key: 'utility', point: result.max_utility_point, color: '#e6bd79', label: 'Max quadratic utility' },
    { key: 'current', point: result.current_point, color: '#adb8cb', label: 'Current' },
    { key: 'sharpe', point: result.max_sharpe_point, color: '#f4907f', label: 'Max Sharpe' },
  ].filter((m): m is typeof m & { point: RiskReturnPoint } => m.point !== null)

  return (
    // Held at the viewBox's own size so the axis type renders 1:1 rather than
    // scaling up with the card.
    <div className="relative h-[420px] w-full max-w-[760px] mt-2">
      <div
        className="absolute left-[15%] top-[30%] w-[320px] h-[260px] pointer-events-none rounded-full"
        style={{ filter: 'blur(60px)', background: 'radial-gradient(circle, rgba(130,169,242,0.28), transparent 70%)' }}
      />
      <div
        className="absolute right-[10%] top-[5%] w-[220px] h-[200px] pointer-events-none rounded-full"
        style={{ filter: 'blur(50px)', background: 'radial-gradient(circle, rgba(244,145,127,0.14), transparent 70%)' }}
      />
      <svg viewBox={`0 0 ${width} ${height}`} className="absolute inset-0 w-full h-full" style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="frontierFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#82a9f2" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#82a9f2" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="frontierLine" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#82a9f2" stopOpacity="0.35" />
            <stop offset="55%" stopColor="#82a9f2" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#82a9f2" stopOpacity="1" />
          </linearGradient>
        </defs>

        {yTicks.map(tick => (
          <g key={`y${tick}`}>
            <line x1={left} y1={y(tick)} x2={width - right} y2={y(tick)} stroke="rgba(255,255,255,0.06)" />
            <text x={left - 10} y={y(tick) + 4} textAnchor="end" fontSize="10" fill="rgba(255,255,255,0.36)">
              {tick.toFixed(0)}%
            </text>
          </g>
        ))}
        {xTicks.map(tick => (
          <text key={`x${tick}`} x={x(tick)} y={height - bottom + 20} textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.36)">
            {tick.toFixed(0)}%
          </text>
        ))}
        <text x={left - 10} y={top - 8} textAnchor="end" fontSize="9.5" fill="rgba(255,255,255,0.3)" letterSpacing="0.12em">RETURN</text>
        <text x={width - right} y={height - bottom + 36} textAnchor="end" fontSize="9.5" fill="rgba(255,255,255,0.3)" letterSpacing="0.12em">VOLATILITY</text>

        {result.scatter.map((p, i) => (
          <circle key={i} cx={x(p.volatility_pct)} cy={y(p.return_pct)} r="1.5" fill="#ffffff" opacity="0.14" />
        ))}

        {area && <path d={area} fill="url(#frontierFill)" />}
        {line && (
          <path d={line} fill="none" stroke="url(#frontierLine)" strokeWidth="2" strokeLinecap="round" className="ledger-draw-short" />
        )}

        {markers.map(marker => (
          <g key={marker.key}>
            <circle cx={x(marker.point.volatility_pct)} cy={y(marker.point.return_pct)} r="13" fill={marker.color} opacity="0.28" style={{ filter: 'blur(3px)' }} />
            <circle cx={x(marker.point.volatility_pct)} cy={y(marker.point.return_pct)} r="5.5" fill={marker.color} stroke="rgba(255,255,255,0.7)" strokeWidth="1.5">
              <title>{`${marker.label} — ${marker.point.return_pct.toFixed(1)}% return at ${marker.point.volatility_pct.toFixed(1)}% volatility`}</title>
            </circle>
          </g>
        ))}
      </svg>
    </div>
  )
}

function LegendDot({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-[7px] text-[12px] font-semibold text-white/60">
      <span className="w-[9px] h-[9px] rounded-full inline-block border-[1.5px] border-white/70" style={{ background: color }} />
      {children}
    </div>
  )
}

/* ── Panel ──────────────────────────────────────────────────────────────── */

const DEFAULT_POSITION_CAP = 35
const DEFAULT_DIVERSIFICATION = 20

export interface OptimizerPanelProps {
  /** Sectors present in the book, from the last optimizer run or the summary. */
  sectors: { name: string; sp_reference_pct: number | null }[]
  /** Tickers available to constrain individually. */
  tickers: string[]
}

/**
 * The Advanced optimization panel: constraint form on the left, efficient
 * frontier on the right. Nothing recomputes while sliders move — the sweep is
 * ~40 solves server-side, so it runs on "Run optimization" and the chart shows
 * the last result until then.
 */
export default function OptimizerPanel({ sectors, tickers }: OptimizerPanelProps) {
  const [positionCap, setPositionCap] = useState(DEFAULT_POSITION_CAP)
  const [diversification, setDiversification] = useState(DEFAULT_DIVERSIFICATION)
  const [sectorBounds, setSectorBounds] = useState<Record<string, Bound>>({})
  const [tickerBounds, setTickerBounds] = useState<Record<string, Bound>>({})
  const { data: result, running, error, run } = useOptimizerRun()

  const availableTickers = useMemo(
    () => tickers.filter(t => !(t in tickerBounds)),
    [tickers, tickerBounds],
  )

  const boundOf = (map: Record<string, Bound>, key: string): Bound =>
    map[key] ?? { floor_pct: 0, cap_pct: 100 }

  const setBound = (
    setter: React.Dispatch<React.SetStateAction<Record<string, Bound>>>,
    key: string,
    patch: Partial<Bound>,
  ) => setter(prev => ({ ...prev, [key]: { ...boundOf(prev, key), ...patch } }))

  const handleRun = () => run({
    position_cap_pct: positionCap,
    diversification_pct: diversification,
    sector_bounds: sectorBounds,
    ticker_bounds: tickerBounds,
  })

  return (
    <div className="flex gap-4 items-stretch">
      {/* Constraints */}
      <GlassCard className="w-[520px] shrink-0 flex flex-col px-[22px] pt-5 pb-[18px] max-h-[760px]">
        <div className="text-[15px] font-bold tracking-[-0.02em] shrink-0">Advanced optimization</div>

        <div className="flex-1 min-h-0 overflow-y-auto soft-scrollbar mt-4 pr-1">
          <div className="grid grid-cols-2 gap-5 mb-[18px]">
            <Slider label="Position cap" value={positionCap} onChange={setPositionCap} min={1} max={100} />
            <Slider label="Diversification" value={diversification} onChange={setDiversification} />
          </div>

          <div className="text-[12px] font-bold mb-2.5">
            Sector constraints{' '}
            <span className="text-white/40 font-medium">— S&amp;P 500 weight marked for reference</span>
          </div>
          {sectors.length === 0 ? (
            <Chip className="px-3 py-2.5 mb-2.5 text-[11.5px] text-white/50">
              Sectors are classified on the first optimizer run — hit Run optimization to load them.
            </Chip>
          ) : sectors.map(sector => {
            const bound = boundOf(sectorBounds, sector.name)
            return (
              <Chip key={sector.name} className="px-3 py-2.5 mb-2.5">
                <div className="flex items-center justify-between mb-2.5">
                  <span className="text-[13px] font-bold">{sector.name}</span>
                  <div className="flex items-center gap-2.5">
                    {sector.sp_reference_pct !== null && (
                      <span className="text-[11px] text-white/40">~{sector.sp_reference_pct}%</span>
                    )}
                    <button
                      type="button"
                      onClick={() => setSectorBounds(prev => {
                        const next = { ...prev }
                        delete next[sector.name]
                        return next
                      })}
                      className="text-[11px] font-semibold text-white/60 hover:text-white"
                    >
                      Reset
                    </button>
                  </div>
                </div>
                <div className="mb-2">
                  <Slider size="sm" label="Floor" value={bound.floor_pct}
                    onChange={v => setBound(setSectorBounds, sector.name, { floor_pct: v })} />
                </div>
                <Slider size="sm" label="Cap" value={bound.cap_pct}
                  onChange={v => setBound(setSectorBounds, sector.name, { cap_pct: v })} />
              </Chip>
            )
          })}

          <div className="text-[12px] font-bold mt-3.5 mb-2.5">
            Ticker constraints{' '}
            <span className="text-white/40 font-medium">— overrides the position cap for that ticker</span>
          </div>
          {Object.keys(tickerBounds).map(ticker => {
            const bound = boundOf(tickerBounds, ticker)
            return (
              <Chip key={ticker} className="px-3 py-2.5 mb-2.5">
                <div className="flex items-center justify-between mb-3">
                  <span className="inline-flex items-center px-3 py-[5px] rounded-[8px] bg-white/[0.09] border border-white/[0.16] text-[12px] font-bold">
                    {ticker}
                  </span>
                  <button
                    type="button"
                    onClick={() => setTickerBounds(prev => {
                      const next = { ...prev }
                      delete next[ticker]
                      return next
                    })}
                    className="text-[11px] font-semibold text-white/60 hover:text-white"
                  >
                    Remove
                  </button>
                </div>
                <div className="mb-2">
                  <Slider size="sm" label="Floor" value={bound.floor_pct}
                    onChange={v => setBound(setTickerBounds, ticker, { floor_pct: v })} />
                </div>
                <Slider size="sm" label="Cap" value={bound.cap_pct}
                  onChange={v => setBound(setTickerBounds, ticker, { cap_pct: v })} />
              </Chip>
            )
          })}

          {availableTickers.length > 0 && (
            <label className="ghost-add flex items-center justify-center gap-[7px] h-10 text-[12.5px] font-semibold cursor-pointer">
              <span>+ Add ticker constraint</span>
              <select
                value=""
                aria-label="Add ticker constraint"
                onChange={e => {
                  if (!e.target.value) return
                  setBound(setTickerBounds, e.target.value, {})
                }}
                className="bg-transparent border-none outline-none text-white/70 cursor-pointer"
              >
                <option value="">Pick…</option>
                {availableTickers.map(ticker => (
                  <option key={ticker} value={ticker}>{ticker}</option>
                ))}
              </select>
            </label>
          )}
        </div>

        <button
          type="button"
          onClick={handleRun}
          disabled={running}
          className="solid-cta rounded-[13px] flex items-center justify-center gap-2 h-11 mt-3.5 text-[13.5px] font-bold shrink-0"
        >
          {running ? 'Optimizing…' : 'Run optimization'}
        </button>

        {error && <div className="mt-2.5 text-[11.5px] text-ledger-negative-soft">{error}</div>}
        {result?.infeasible && (
          <div className="mt-2.5 text-[11.5px] text-ledger-warning">
            No portfolio satisfies these constraints — the closest feasible mix is shown instead.
          </div>
        )}
      </GlassCard>

      {/* Frontier */}
      <GlassCard className="flex-1 min-w-0 flex flex-col px-6 py-5 max-h-[760px]">
        <div className="shrink-0">
          <div className="text-[15px] font-bold tracking-[-0.02em]">Efficient frontier</div>
          <div className="text-[12px] text-white/50 mt-2 max-w-[640px] leading-relaxed">
            The line is the best return available at each level of risk given your position cap ({positionCap}%)
            and sector limits. The markers are the suggested portfolios. The faint dots are random portfolios
            shown only for scale — they ignore your limits.
          </div>
        </div>

        <div className="flex items-center gap-[22px] mt-4 shrink-0 flex-wrap">
          <div className="flex items-center gap-[7px] text-[12px] font-semibold text-white/60">
            <svg width="16" height="10" viewBox="0 0 16 10"><path d="M1 8 L15 2" stroke="#82a9f2" strokeWidth="2" strokeLinecap="round" /></svg>
            Efficient frontier
          </div>
          <LegendDot color="#f4907f">Max Sharpe</LegendDot>
          <LegendDot color="#e6bd79">Max quadratic utility</LegendDot>
          <LegendDot color="#adb8cb">Current</LegendDot>
        </div>

        {running && !result ? (
          <LoadingRow className="h-[420px]" label="Sweeping the frontier…" />
        ) : !result ? (
          <EmptyState
            className="h-[420px]"
            title="Set your constraints, then run"
            body="The frontier is ~40 constrained solves, so it runs on demand rather than on every slider move."
          />
        ) : result.insufficient_data ? (
          <EmptyState
            className="h-[420px]"
            title="Not enough price history"
            body="The optimizer needs at least 30 days of daily closes across two or more priced holdings."
          />
        ) : (
          <>
            <FrontierChart result={result} />
            <div className="grid grid-cols-3 gap-2.5 mt-3 shrink-0">
              {[
                { label: 'Current', point: result.current_point },
                { label: 'Max Sharpe', point: result.max_sharpe_point },
                { label: 'Max utility', point: result.max_utility_point },
              ].map(({ label, point }) => (
                <Chip key={label} className="px-3 py-2">
                  <div className="text-[9.5px] uppercase tracking-[0.14em] font-semibold text-white/40">{label}</div>
                  <div className="mt-1 text-[13px] font-bold tabular-nums">
                    {point ? `${point.return_pct.toFixed(1)}% / ${point.volatility_pct.toFixed(1)}%` : '—'}
                  </div>
                  <div className="mt-0.5 text-[10px] text-white/44">
                    return / vol{point?.sharpe != null ? ` · Sharpe ${point.sharpe.toFixed(2)}` : ''}
                  </div>
                </Chip>
              ))}
            </div>
          </>
        )}
      </GlassCard>
    </div>
  )
}
