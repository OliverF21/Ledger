import { useMemo } from 'react'

interface FrontierPoint { volatility_pct: number; return_pct: number }
interface RandomPortfolioPoint { volatility_pct: number; return_pct: number; sharpe: number }
export interface ObjectiveMarker { name: string; volatility_pct: number; return_pct: number; color: string }

interface Props {
  frontierPoints: FrontierPoint[]
  markers: ObjectiveMarker[]
  randomPortfolios?: RandomPortfolioPoint[]
}

const CHART = { width: 760, height: 420, left: 56, right: 20, top: 20, bottom: 42 }

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
  const niceLo = Math.floor(lo / step) * step
  const niceHi = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let t = niceLo; t <= niceHi + step / 2; t += step) ticks.push(Math.round((t + Number.EPSILON) * 1e6) / 1e6)
  return { domain: [niceLo, niceHi], ticks }
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

export default function EfficientFrontierChart({ frontierPoints, markers, randomPortfolios = [] }: Props) {
  const { width, height, left, right, top, bottom } = CHART
  const plotW = width - left - right
  const plotH = height - top - bottom

  const { domain: xDomain, ticks: xTicks } = useMemo(
    () =>
      zoomedDomain(
        frontierPoints.map(p => p.volatility_pct),
        markers.map(m => m.volatility_pct),
        { pctlLow: 1, pctlHigh: 99, padFrac: 0.06, anchorZero: true },
      ),
    [frontierPoints, markers],
  )
  const { domain: yDomain, ticks: yTicks } = useMemo(
    () =>
      zoomedDomain(
        frontierPoints.map(p => p.return_pct),
        markers.map(m => m.return_pct),
        { pctlLow: 1, pctlHigh: 99, padFrac: 0.15, anchorZero: false },
      ),
    [frontierPoints, markers],
  )

  const xSpan = Math.max(xDomain[1] - xDomain[0], 1e-6)
  const ySpan = Math.max(yDomain[1] - yDomain[0], 1e-6)
  const x = (vol: number) => left + ((vol - xDomain[0]) / xSpan) * plotW
  const y = (ret: number) => top + (1 - (ret - yDomain[0]) / ySpan) * plotH

  const line = frontierPoints
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.volatility_pct).toFixed(1)} ${y(p.return_pct).toFixed(1)}`)
    .join(' ')
  const area = frontierPoints.length > 1
    ? `${line} L${x(frontierPoints[frontierPoints.length - 1].volatility_pct).toFixed(1)} ${height - bottom} L${x(frontierPoints[0].volatility_pct).toFixed(1)} ${height - bottom} Z`
    : ''

  return (
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
              {Math.round(tick)}%
            </text>
          </g>
        ))}
        {xTicks.map(tick => (
          <text key={`x${tick}`} x={x(tick)} y={height - bottom + 20} textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.36)">
            {Math.round(tick)}%
          </text>
        ))}
        <text x={left - 10} y={top - 8} textAnchor="end" fontSize="9.5" fill="rgba(255,255,255,0.3)" letterSpacing="0.12em">RETURN</text>
        <text x={width - right} y={height - bottom + 36} textAnchor="end" fontSize="9.5" fill="rgba(255,255,255,0.3)" letterSpacing="0.12em">VOLATILITY</text>

        {randomPortfolios.map((p, i) => (
          <circle key={i} cx={x(p.volatility_pct)} cy={y(p.return_pct)} r="1.5" fill="#ffffff" opacity="0.14" />
        ))}

        {area && <path d={area} fill="url(#frontierFill)" />}
        {line && (
          <path d={line} fill="none" stroke="url(#frontierLine)" strokeWidth="2" strokeLinecap="round" className="ledger-draw-short" />
        )}

        {markers.map(marker => (
          <g key={marker.name}>
            <circle cx={x(marker.volatility_pct)} cy={y(marker.return_pct)} r="13" fill={marker.color} opacity="0.28" style={{ filter: 'blur(3px)' }} />
            <circle cx={x(marker.volatility_pct)} cy={y(marker.return_pct)} r="5.5" fill={marker.color} stroke="rgba(255,255,255,0.7)" strokeWidth="1.5">
              <title>{`${OBJECTIVE_LABELS[marker.name] ?? marker.name} — ${marker.return_pct.toFixed(1)}% return at ${marker.volatility_pct.toFixed(1)}% volatility`}</title>
            </circle>
          </g>
        ))}
      </svg>
    </div>
  )
}
