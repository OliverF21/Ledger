import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  pickFrontierHover,
  type FrontierHover,
  type HoverFrontierPoint,
  type HoverMarker,
} from './efficientFrontierHover'

interface FrontierPoint { volatility_pct: number; return_pct: number }
interface RandomPortfolioPoint { volatility_pct: number; return_pct: number; sharpe: number }
export interface ObjectiveMarker {
  name: string
  volatility_pct: number
  return_pct: number
  sharpe?: number | null
  color: string
}

interface Props {
  frontierPoints: FrontierPoint[]
  markers: ObjectiveMarker[]
  randomPortfolios?: RandomPortfolioPoint[]
}

const PLOT_INSET = { left: 44, right: 10, top: 14, bottom: 24 }

const OBJECTIVE_LABELS: Record<string, string> = {
  max_sharpe: 'Max Sharpe',
  max_quadratic_utility: 'Max Quadratic Utility',
  current: 'Current',
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0
  const idx = (p / 100) * (sorted.length - 1)
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
}

function niceTicksAndDomain([lo, hi]: [number, number]): { domain: [number, number]; ticks: number[] } {
  const range = hi - lo
  if (range <= 0) return { domain: [lo, hi], ticks: [lo] }
  const rawStep = range / 4
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const residual = rawStep / magnitude
  const step = (residual >= 5 ? 10 : residual >= 2 ? 5 : residual >= 1 ? 2 : 1) * magnitude
  const ticks: number[] = []
  const first = Math.ceil(lo / step) * step
  for (let t = first; t <= hi + 1e-9; t += step) {
    ticks.push(Math.round((t + Number.EPSILON) * 1e6) / 1e6)
  }
  if (ticks.length === 0) ticks.push(lo, hi)
  return { domain: [lo, hi], ticks }
}

// Domain from frontier + markers only — the random cloud is unseeded and
// must not drag the axis between runs. See the previous Recharts version.
function zoomedDomain(
  bulkValues: number[],
  keyValues: number[],
  { pctlLow, pctlHigh, padFrac, anchorZero }: { pctlLow: number; pctlHigh: number; padFrac: number; anchorZero: boolean },
): { domain: [number, number]; ticks: number[] } {
  if (bulkValues.length === 0 && keyValues.length === 0) return { domain: [0, 1], ticks: [0, 1] }

  const sorted = [...bulkValues].sort((a, b) => a - b)
  const keyMax = keyValues.length ? Math.max(...keyValues) : -Infinity
  const keyMin = keyValues.length ? Math.min(...keyValues) : Infinity
  const hi = Math.max(percentile(sorted, pctlHigh), keyMax)
  const lo = anchorZero ? 0 : Math.min(percentile(sorted, pctlLow), keyMin)

  const range = Math.max(hi - lo, 1e-6)
  return niceTicksAndDomain([anchorZero ? 0 : lo - range * padFrac, hi + range * padFrac])
}

function fmtPct1(n: number): string {
  return `${n < 0 ? '−' : ''}${Math.abs(n).toFixed(1)}%`
}

function clientToViewBox(
  event: ReactPointerEvent<HTMLDivElement>,
  width: number,
  height: number,
): { x: number; y: number } {
  const rect = event.currentTarget.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return { x: -1, y: -1 }
  return {
    x: ((event.clientX - rect.left) / rect.width) * width,
    y: ((event.clientY - rect.top) / rect.height) * height,
  }
}

export default function EfficientFrontierChart({ frontierPoints, markers, randomPortfolios = [] }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const { left, right, top, bottom } = PLOT_INSET
  const width = Math.max(size.width, 1)
  const height = Math.max(size.height, 1)
  const plotW = Math.max(width - left - right, 1)
  const plotH = Math.max(height - top - bottom, 1)
  const [hover, setHover] = useState<FrontierHover | null>(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const apply = () => {
      const rect = el.getBoundingClientRect()
      setSize({ width: Math.round(rect.width), height: Math.round(rect.height) })
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const { domain: xDomain, ticks: xTicks } = useMemo(
    () =>
      zoomedDomain(
        frontierPoints.map(p => p.volatility_pct),
        markers.map(m => m.volatility_pct),
        { pctlLow: 1, pctlHigh: 99, padFrac: 0.06, anchorZero: false },
      ),
    [frontierPoints, markers],
  )
  const { domain: yDomain, ticks: yTicks } = useMemo(
    () =>
      zoomedDomain(
        frontierPoints.map(p => p.return_pct),
        markers.map(m => m.return_pct),
        { pctlLow: 1, pctlHigh: 99, padFrac: 0.08, anchorZero: false },
      ),
    [frontierPoints, markers],
  )

  const xSpan = Math.max(xDomain[1] - xDomain[0], 1e-6)
  const ySpan = Math.max(yDomain[1] - yDomain[0], 1e-6)
  const x = (vol: number) => left + ((vol - xDomain[0]) / xSpan) * plotW
  const y = (ret: number) => top + (1 - (ret - yDomain[0]) / ySpan) * plotH

  const plot = useMemo(
    () => ({ left, top, right: width - right, bottom: height - bottom }),
    [left, top, right, width, height, bottom],
  )

  const projectedMarkers: HoverMarker[] = useMemo(() => {
    const toX = (vol: number) => left + ((vol - xDomain[0]) / xSpan) * plotW
    const toY = (ret: number) => top + (1 - (ret - yDomain[0]) / ySpan) * plotH
    return markers.map(m => ({
      name: m.name,
      label: OBJECTIVE_LABELS[m.name] ?? m.name,
      color: m.color,
      x: toX(m.volatility_pct),
      y: toY(m.return_pct),
      volatility_pct: m.volatility_pct,
      return_pct: m.return_pct,
      sharpe: m.sharpe ?? null,
    }))
  }, [markers, left, top, xDomain, yDomain, xSpan, ySpan, plotW, plotH])

  const projectedFrontier: HoverFrontierPoint[] = useMemo(() => {
    const toX = (vol: number) => left + ((vol - xDomain[0]) / xSpan) * plotW
    const toY = (ret: number) => top + (1 - (ret - yDomain[0]) / ySpan) * plotH
    return frontierPoints.map(p => ({
      x: toX(p.volatility_pct),
      y: toY(p.return_pct),
      volatility_pct: p.volatility_pct,
      return_pct: p.return_pct,
    }))
  }, [frontierPoints, left, top, xDomain, yDomain, xSpan, ySpan, plotW, plotH])

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const pointer = clientToViewBox(event, width, height)
    setHover(pickFrontierHover(pointer, plot, projectedMarkers, projectedFrontier))
  }, [width, height, plot, projectedMarkers, projectedFrontier])

  const handlePointerLeave = useCallback(() => setHover(null), [])

  const line = frontierPoints
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.volatility_pct).toFixed(1)} ${y(p.return_pct).toFixed(1)}`)
    .join(' ')
  const area = frontierPoints.length > 1
    ? `${line} L${x(frontierPoints[frontierPoints.length - 1].volatility_pct).toFixed(1)} ${height - bottom} L${x(frontierPoints[0].volatility_pct).toFixed(1)} ${height - bottom} Z`
    : ''

  const hoverXPct = hover ? (hover.x / width) * 100 : 0
  const hoverYPct = hover ? (hover.y / height) * 100 : 0
  const tooltipTransform = hover
    ? `translate(${hover.x > width * 0.62 ? 'calc(-100% - 14px)' : '14px'}, ${
        hover.y < 80 ? '14px' : hover.y > height - 80 ? 'calc(-100% - 14px)' : '-50%'
      })`
    : undefined

  return (
    <div
      ref={wrapRef}
      className="relative h-full w-full min-h-0 cursor-crosshair"
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      <div
        className="absolute left-[12%] top-[28%] w-[180px] h-[140px] pointer-events-none rounded-full"
        style={{ filter: 'blur(40px)', background: 'radial-gradient(circle, rgba(130,169,242,0.22), transparent 70%)' }}
      />
      <div
        className="absolute right-[8%] top-[6%] w-[120px] h-[100px] pointer-events-none rounded-full"
        style={{ filter: 'blur(36px)', background: 'radial-gradient(circle, rgba(244,145,127,0.12), transparent 70%)' }}
      />
      {size.width > 0 && size.height > 0 && (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="absolute inset-0 w-full h-full pointer-events-none"
        style={{ overflow: 'visible' }}
        aria-hidden="true"
      >
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
              {Math.round(tick)}%
            </text>
          </g>
        ))}
        {xTicks.map(tick => (
          <text key={`x${tick}`} x={x(tick)} y={height - 14} textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.36)">
            {Math.round(tick)}%
          </text>
        ))}
        <text x={left - 8} y={Math.max(10, top - 2)} textAnchor="end" fontSize="9" fill="rgba(255,255,255,0.3)" letterSpacing="0.12em">RETURN</text>
        <text x={(left + width - right) / 2} y={height - 3} textAnchor="middle" fontSize="9" fill="rgba(255,255,255,0.3)" letterSpacing="0.12em">VOLATILITY</text>

        {randomPortfolios.map((p, i) => (
          <circle key={i} cx={x(p.volatility_pct)} cy={y(p.return_pct)} r="1.5" fill="#ffffff" opacity="0.14" />
        ))}

        {area && <path d={area} fill="url(#frontierFill)" />}
        {line && (
          <path d={line} fill="none" stroke="url(#frontierLine)" strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" className="ledger-draw-short" />
        )}

        {markers.map(marker => {
          const active = hover?.kind === 'marker' && hover.name === marker.name
          return (
            <g key={marker.name}>
              <circle cx={x(marker.volatility_pct)} cy={y(marker.return_pct)} r="13" fill={marker.color} opacity="0.28" style={{ filter: 'blur(3px)' }} />
              <circle
                cx={x(marker.volatility_pct)}
                cy={y(marker.return_pct)}
                r={active ? 7 : 5.5}
                fill={marker.color}
                stroke="rgba(255,255,255,0.7)"
                strokeWidth={active ? 2 : 1.5}
              />
            </g>
          )
        })}
      </svg>
      )}

      {hover && (
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div
            className="absolute top-0 bottom-0 w-px"
            style={{
              left: `${hoverXPct}%`,
              background: `linear-gradient(180deg, transparent 0%, ${hover.color}99 10%, ${hover.color} 50%, ${hover.color}99 90%, transparent 100%)`,
              boxShadow: `0 0 12px ${hover.color}66`,
            }}
          />
          {hover.kind === 'frontier' && (
            <div
              className="absolute h-[9px] w-[9px] rounded-full"
              style={{
                left: `${hoverXPct}%`,
                top: `${hoverYPct}%`,
                transform: 'translate(-50%, -50%)',
                background: hover.color,
                boxShadow: `0 0 0 2px rgba(8,11,15,0.92), 0 0 0 3.5px ${hover.color}, 0 0 16px ${hover.color}cc`,
              }}
            />
          )}
        </div>
      )}

      {hover && (
        <div
          role="status"
          className="absolute z-10 pointer-events-none w-[168px] px-3 py-2.5 rounded-[12px] border border-white/14"
          style={{
            left: `${hoverXPct}%`,
            top: `${hoverYPct}%`,
            transform: tooltipTransform,
            background: 'rgba(12, 16, 22, 0.94)',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.10), 0 18px 40px -24px rgba(0,0,0,0.9)',
          }}
        >
          <div className="flex items-center gap-[7px] mb-1.5">
            <span className="w-[8px] h-[8px] rounded-full shrink-0" style={{ background: hover.color }} />
            <div className="text-[11px] font-semibold text-white/80 truncate">{hover.label}</div>
          </div>
          <HoverRow label="Return" value={fmtPct1(hover.return_pct)} />
          <HoverRow label="Volatility" value={fmtPct1(hover.volatility_pct)} />
          {hover.sharpe != null && (
            <HoverRow label="Sharpe" value={hover.sharpe.toFixed(2)} />
          )}
        </div>
      )}
    </div>
  )
}

function HoverRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[2px]">
      <span className="text-[10px] text-white/40">{label}</span>
      <span className="text-[12px] font-semibold tabular-nums">{value}</span>
    </div>
  )
}
