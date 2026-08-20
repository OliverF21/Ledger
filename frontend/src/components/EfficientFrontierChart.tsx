import { ComposedChart, Scatter, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, TooltipProps } from 'recharts'

interface FrontierPoint { volatility_pct: number; return_pct: number }
interface ObjectiveMarker { name: string; volatility_pct: number; return_pct: number; color: string }

interface Props {
  frontierPoints: FrontierPoint[]
  markers: ObjectiveMarker[]
}

const OBJECTIVE_LABELS: Record<string, string> = {
  max_sharpe: 'Max Sharpe',
  max_quadratic_utility: 'Max Quadratic Utility',
}

export default function EfficientFrontierChart({ frontierPoints, markers }: Props) {
  // Recharts computes one "nearest point across all combined series" and stamps that single
  // value onto every tooltip row (Line + every Scatter), rather than each series showing its
  // own true value. Overriding `content` to recompute each row ourselves from the component's
  // own props — ignoring Recharts' broken per-row `payload` values — is the verified fix.
  const renderTooltip = ({ active, label }: TooltipProps<number, string>) => {
    if (!active || label == null) return null
    let nearest = frontierPoints[0]
    let best = Infinity
    for (const p of frontierPoints) {
      const d = Math.abs(p.volatility_pct - label)
      if (d < best) { best = d; nearest = p }
    }
    return (
      <div style={{ backgroundColor: '#11141a', border: '1px solid #1c2029', borderRadius: '8px', padding: 8, fontSize: 12 }}>
        <div style={{ color: '#999', marginBottom: 4 }}>{label}</div>
        <div style={{ color: '#5b8def' }}>Efficient Frontier : {nearest.return_pct.toFixed(2)}%</div>
        {markers.map(m => (
          <div key={m.name} style={{ color: m.color }}>{OBJECTIVE_LABELS[m.name] ?? m.name} : {m.return_pct.toFixed(2)}%</div>
        ))}
      </div>
    )
  }

  return (
    <div className="h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart>
          <CartesianGrid strokeDasharray="0" stroke="rgba(255,255,255,0.06)" horizontal vertical={false} />
          <XAxis
            type="number" dataKey="volatility_pct" name="Volatility"
            stroke="#5c626f" axisLine={false} tickLine={false} style={{ fontSize: '12px' }}
            unit="%" domain={['auto', 'auto']}
          />
          <YAxis
            type="number" dataKey="return_pct" name="Return"
            stroke="#5c626f" axisLine={false} tickLine={false} style={{ fontSize: '12px' }}
            unit="%" domain={['auto', 'auto']}
          />
          <Tooltip content={renderTooltip} />
          <Legend />
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
