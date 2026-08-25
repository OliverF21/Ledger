import { useMemo } from 'react'
import { ComposedChart, Scatter, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, TooltipProps } from 'recharts'

interface FrontierPoint { volatility_pct: number; return_pct: number }
interface RandomPortfolioPoint { volatility_pct: number; return_pct: number; sharpe: number }
export interface ObjectiveMarker { name: string; volatility_pct: number; return_pct: number; color: string }

interface Props {
  frontierPoints: FrontierPoint[]
  markers: ObjectiveMarker[]
  randomPortfolios?: RandomPortfolioPoint[]
}

const OBJECTIVE_LABELS: Record<string, string> = {
  max_sharpe: 'Max Sharpe',
  max_quadratic_utility: 'Max Quadratic Utility',
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0
  const idx = (p / 100) * (sorted.length - 1)
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
}

// Rounds a domain out to a "nice" step (1/2/5/10/20/25/50/100 ...) and returns
// the explicit tick array alongside it -- we render with this array via the
// `ticks` prop rather than letting Recharts auto-generate ticks from the
// domain. Recharts' own tick generator picks its "nice" step independently of
// the domain it's handed (e.g. domain=[0,150] -> Recharts may pick step=40,
// not our step=50), and 40 doesn't evenly divide 150 -- it renders 0/40/80
// then tacks the raw domain boundary (150) on as an extra, unevenly-spaced
// tick. Owning the tick array ourselves is the only way to guarantee even
// spacing regardless of what Recharts' internal algorithm would have chosen.
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

// Same "zoom to where the data actually is" percentile approach as
// framework_portfolio_optimization.py's ZOOM_PCTL/AXIS_PAD -- the random-
// portfolio cloud is unconstrained (no position cap / sector limits, see the
// comment below), so its corner solutions can sit far outside where the
// frontier and markers actually live. A domain of ['auto', 'auto'] lets one
// such outlier stretch both axes until the real content is a thumbnail in
// the corner. keyValues (the frontier line + objective markers) are never
// clipped by the percentile -- only the padding is computed from them too,
// so a chosen objective can't end up flush against the edge of the plot.
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
  const { domain: xDomain, ticks: xTicks } = useMemo(
    () =>
      zoomedDomain(
        [...frontierPoints.map(p => p.volatility_pct), ...randomPortfolios.map(p => p.volatility_pct)],
        markers.map(m => m.volatility_pct),
        { pctlLow: 1, pctlHigh: 99, padFrac: 0.06, anchorZero: true },
      ),
    [frontierPoints, randomPortfolios, markers],
  )
  const { domain: yDomain, ticks: yTicks } = useMemo(
    () =>
      zoomedDomain(
        [...frontierPoints.map(p => p.return_pct), ...randomPortfolios.map(p => p.return_pct)],
        markers.map(m => m.return_pct),
        { pctlLow: 1, pctlHigh: 99, padFrac: 0.15, anchorZero: false },
      ),
    [frontierPoints, randomPortfolios, markers],
  )

  // Recharts computes one "nearest point across all combined series" and stamps that single
  // value onto every tooltip row (Line + every Scatter), rather than each series showing its
  // own true value. Overriding `content` to recompute each row ourselves from the component's
  // own props — ignoring Recharts' broken per-row `payload` values — is the verified fix.
  const renderTooltip = ({ active, label }: TooltipProps<number, string>) => {
    if (!active || label == null) return null
    // frontierPoints can be [] while markers is still populated -- advanced mode
    // always produces both objective markers, but the separate frontier-sweep
    // step can independently come back empty if every swept target volatility
    // failed to converge. Guard nearest as possibly-null (rather than seeding
    // it from frontierPoints[0]) so hovering a marker in that scenario still
    // renders the marker rows instead of throwing on nearest.return_pct.
    let nearest: FrontierPoint | null = null
    let best = Infinity
    for (const p of frontierPoints) {
      const d = Math.abs(p.volatility_pct - label)
      if (d < best) { best = d; nearest = p }
    }
    return (
      <div style={{ backgroundColor: '#11141a', border: '1px solid #1c2029', borderRadius: '8px', padding: 8, fontSize: 12 }}>
        <div style={{ color: '#999', marginBottom: 4 }}>{label}</div>
        {nearest && (
          <div style={{ color: '#5b8def' }}>Efficient Frontier : {nearest.return_pct.toFixed(2)}%</div>
        )}
        {markers.map(m => (
          <div key={m.name} style={{ color: m.color }}>{OBJECTIVE_LABELS[m.name] ?? m.name} : {m.return_pct.toFixed(2)}%</div>
        ))}
      </div>
    )
  }

  return (
    <div className="h-full min-h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart margin={{ top: 10, right: 16, bottom: 44, left: 28 }}>
          <CartesianGrid strokeDasharray="0" stroke="rgba(255,255,255,0.06)" horizontal vertical={false} />
          <XAxis
            type="number" dataKey="volatility_pct" name="Volatility"
            stroke="#5c626f" axisLine={false} tickLine={false} style={{ fontSize: '13px' }}
            unit="%" domain={xDomain} ticks={xTicks} tickFormatter={v => Math.round(v).toString()}
            label={{ value: 'Annualized Volatility', position: 'bottom', offset: 10, fill: '#8b90a0', fontSize: 12 }}
          />
          <YAxis
            type="number" dataKey="return_pct" name="Return"
            stroke="#5c626f" axisLine={false} tickLine={false} style={{ fontSize: '13px' }}
            unit="%" domain={yDomain} ticks={yTicks} tickFormatter={v => Math.round(v).toString()}
            label={{ value: 'Annualized Return', angle: -90, position: 'insideLeft', offset: -4, fill: '#8b90a0', fontSize: 12 }}
          />
          <Tooltip content={renderTooltip} />
          <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: '12px' }} />
          {/* Random-portfolio backdrop cloud (ported from example_portfolio_optimization.py's
              Dirichlet-sampled visualization) -- every point is a random, unconstrained
              (no position cap / sector limits) combination of the same held tickers, shown
              purely to illustrate how much of the mathematically-reachable universe those
              constraints cut away. Rendered FIRST (before the Line/markers) so it sits behind
              them; legendType="none" keeps ~1500 dots from adding a legend entry of their own. */}
          {randomPortfolios.length > 0 && (
            <Scatter
              data={randomPortfolios} dataKey="return_pct" name="Random portfolios"
              legendType="none" isAnimationActive={false}
              // Recharts sizes Scatter shapes via an implicit ZAxis (default area
              // range [64, 400]px^2) when no z dataKey is given, which renders far
              // too large for a ~1500-point cloud. A custom shape function bypasses
              // that entirely -- fixed 1.5px radius, matching the "s=1, alpha=0.35"
              // dense-cloud look from example_portfolio_optimization.py's matplotlib
              // scatter this was ported from.
              shape={(props: unknown) => {
                const { cx, cy } = props as { cx: number; cy: number }
                return <circle cx={cx} cy={cy} r={1.5} fill="#5b8def" fillOpacity={0.12} />
              }}
            />
          )}
          <Line
            data={frontierPoints} dataKey="return_pct" name="Efficient Frontier"
            stroke="#5b8def" strokeWidth={2} dot={false} type="monotone"
          />
          {markers.map(m => (
            <Scatter
              key={m.name}
              data={[m]} dataKey="return_pct" name={OBJECTIVE_LABELS[m.name] ?? m.name}
              fill={m.color} shape="triangle"
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
