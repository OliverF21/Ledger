import { ComposedChart, Scatter, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

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
          <Tooltip
            contentStyle={{ backgroundColor: '#11141a', border: '1px solid #1c2029', borderRadius: '8px' }}
            formatter={(value: number) => `${value.toFixed(2)}%`}
          />
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
