/**
 * Hand-rolled SVG charts for the V2 design language.
 *
 * These replace Recharts for the two hero visuals (the drawn area line and
 * the stroke-arc donut). Recharts can't produce either without fighting it:
 * the line needs a mask-faded, stroke-dashoffset draw-in that spills outside
 * its box, and the donut needs uniform 22–24px ring segments with per-arc
 * hover glow. Both are a few dozen lines as raw SVG, and the result is
 * pixel-identical to the handoff. Recharts stays in use for the denser
 * analytical charts on Trends/Cash Flow, where its axes and tooltips earn
 * their weight.
 */
import { useId, type CSSProperties } from 'react'
import { mixHex } from '../../utils/color'

/* ── Area line chart ──────────────────────────────────────────────────── */

/** Catmull-Rom through the points, converted to cubic beziers. Gives the
 *  handoff's soft curve without the overshoot a naive bezier smoothing
 *  produces on a spiky series. */
function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return ''
  if (points.length === 1) return `M${points[0].x} ${points[0].y}`

  let d = `M${points[0].x} ${points[0].y}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2] ?? p2
    // Tension 1/6 is the standard uniform Catmull-Rom → Bezier conversion.
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = p1.y + (p2.y - p0.y) / 6
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`
  }
  return d
}

export interface AreaLineChartProps {
  values: number[]
  /** Line + fill colour. Callers pass positive/negative from the trend. */
  color: string
  width?: number
  height?: number
  /** Vertical inset so the curve's peaks aren't clipped by the viewBox. */
  padding?: number
  /** CSS mask that fades the right edge out, so the curve dissolves under
   *  overlaid figures rather than ending on a hard stop. */
  maskImage?: string
  className?: string
  style?: CSSProperties
  /** Suppress the entrance draw when the chart re-renders on a range switch. */
  animate?: boolean
}

export function AreaLineChart({
  values,
  color,
  width = 1180,
  height = 300,
  padding = 20,
  maskImage,
  className = '',
  style,
  animate = true,
}: AreaLineChartProps) {
  const gradientId = useId()
  if (values.length === 0) return null

  const min = Math.min(...values)
  const max = Math.max(...values)
  // A dead-flat series would divide by zero; centre it instead.
  const span = max - min || 1
  const usable = height - padding * 2
  const step = values.length > 1 ? width / (values.length - 1) : 0

  const points = values.map((value, i) => ({
    x: values.length > 1 ? i * step : width / 2,
    y: padding + (1 - (value - min) / span) * usable,
  }))

  const line = smoothPath(points)
  const area = `${line} L${width} ${height} L0 ${height} Z`

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      style={{ overflow: 'visible', pointerEvents: 'none', WebkitMaskImage: maskImage, maskImage, ...style }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`${gradientId}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${gradientId}-line`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" />
          <stop offset="55%" stopColor={color} stopOpacity="0.92" />
          <stop offset="100%" stopColor={color} stopOpacity="1" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId}-fill)`} />
      <path
        d={line}
        fill="none"
        stroke={`url(#${gradientId}-line)`}
        strokeWidth="2"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        className={animate ? 'ledger-draw' : undefined}
      />
    </svg>
  )
}

/* ── Donut ────────────────────────────────────────────────────────────── */

export interface DonutSlice {
  key: string
  label: string
  value: number
  color: string
}

/** Ring donut drawn as dash-offset arcs on concentric circles. Uniform stroke
 *  width means every segment reads at the same visual weight regardless of
 *  size — the thing a filled pie gets wrong when one slice dominates. */
export function Donut({
  slices,
  size = 258,
  radius = 84,
  strokeWidth = 24,
  activeIndex = null,
  onHover,
  children,
}: {
  slices: DonutSlice[]
  /** In the fixed 200×200 viewBox, not in px. */
  radius?: number
  size?: number
  strokeWidth?: number
  activeIndex?: number | null
  onHover?: (index: number | null) => void
  /** Centre label. */
  children?: React.ReactNode
}) {
  const gradientId = useId()
  const circumference = 2 * Math.PI * radius
  const total = slices.reduce((sum, slice) => sum + Math.max(0, slice.value), 0)

  let cursor = 0
  const boundaries: number[] = []
  const arcs = slices.map(slice => {
    const fraction = total > 0 ? Math.max(0, slice.value) / total : 0
    // Arcs butt directly against each other and are separated by the hairline
    // light stroke below — cutting a gap into the dash instead punches hard
    // dark wedges through the ring.
    const dash = fraction * circumference
    const offset = -cursor
    cursor += fraction * circumference
    boundaries.push(cursor)
    return { slice, dash, offset }
  })

  const glowColor = activeIndex !== null && slices[activeIndex]
    ? slices[activeIndex].color
    : '#82a9f2'

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      {/* Ambient glow. The falloff runs all the way to transparent well inside
          each layer's box — stopping it short leaves a visible disc edge under
          the ring, which is what a flat colour stop reads as. */}
      <div
        className="absolute rounded-full pointer-events-none transition-[background] duration-300"
        style={{
          inset: -size * 0.06,
          filter: `blur(${Math.round(size * 0.14)}px)`,
          background:
            `radial-gradient(circle, ${glowColor}3d 0%, ${glowColor}26 34%, rgba(99,207,204,0.07) 58%, transparent 82%)`,
        }}
      />
      <div
        className="absolute rounded-full pointer-events-none"
        style={{
          inset: size * 0.24,
          filter: `blur(${Math.round(size * 0.09)}px)`,
          background:
            'radial-gradient(circle, rgba(190,212,255,0.30) 0%, rgba(130,169,242,0.13) 46%, transparent 80%)',
        }}
      />
      <svg viewBox="0 0 200 200" className="absolute inset-0 w-full h-full" style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          {/* Per-arc gradient with an off-centre focal point, so the ring reads
              as one lit surface rather than a set of flat cut-out blocks. Same
              recipe the Recharts pie used before the redesign. */}
          {slices.map((slice, i) => (
            <radialGradient
              key={slice.key}
              id={`${gradientId}-${i}`}
              cx="42%" cy="42%" r="78%" fx="36%" fy="36%"
            >
              <stop offset="0%" stopColor={mixHex(slice.color, '#ffffff', 0.22)} stopOpacity={0.98} />
              <stop offset="48%" stopColor={slice.color} stopOpacity={0.94} />
              <stop offset="100%" stopColor={mixHex(slice.color, '#0a0c11', 0.12)} stopOpacity={0.88} />
            </radialGradient>
          ))}
        </defs>
        <circle cx="100" cy="100" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={strokeWidth} />
        <g style={{ filter: 'drop-shadow(0 6px 16px rgba(0,0,0,0.45))' }}>
          {arcs.map(({ slice, dash, offset }, i) => (
            <circle
              key={slice.key}
              cx="100"
              cy="100"
              r={radius}
              fill="none"
              stroke={`url(#${gradientId}-${i})`}
              strokeWidth={activeIndex === i ? strokeWidth + 5 : strokeWidth}
              strokeDasharray={`${dash.toFixed(2)} ${circumference.toFixed(2)}`}
              strokeDashoffset={offset.toFixed(2)}
              style={{
                cursor: onHover ? 'pointer' : 'default',
                transition: 'stroke-width .18s ease, filter .18s ease, opacity .18s ease',
                opacity: activeIndex === null || activeIndex === i ? 1 : 0.55,
                filter: activeIndex === i ? `drop-shadow(0 0 12px ${slice.color}b3)` : undefined,
              }}
              onMouseEnter={() => onHover?.(i)}
              onMouseLeave={() => onHover?.(null)}
            />
          ))}
          {/* Hairline seams at each boundary. The old pie got these free from
              the Cell stroke; with stroke-arcs the ends aren't strokeable, so
              they're drawn as radial ticks — enough to read the boundary,
              nowhere near enough to cut the ring the way a gap does. */}
          {slices.length > 1 && boundaries.map((angle, i) => {
            const rad = (angle / circumference) * 2 * Math.PI
            const inner = radius - strokeWidth / 2
            const outer = radius + strokeWidth / 2
            return (
              <line
                key={`seam-${i}`}
                x1={100 + Math.cos(rad) * inner}
                y1={100 + Math.sin(rad) * inner}
                x2={100 + Math.cos(rad) * outer}
                y2={100 + Math.sin(rad) * outer}
                stroke="rgba(255,255,255,0.10)"
                strokeWidth="0.8"
              />
            )
          })}
        </g>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center px-6">
        {children}
      </div>
    </div>
  )
}

/* ── Donut legend ─────────────────────────────────────────────────────── */

/** Right-aligned amount / label / colour-dot rows that pair with a Donut.
 *  Amount leads because it's what the eye is scanning for; the dot anchors
 *  the row to its arc. */
export function DonutLegend({
  slices,
  activeIndex = null,
  onHover,
  formatValue,
  labelWidth = 112,
  className = '',
}: {
  slices: DonutSlice[]
  activeIndex?: number | null
  onHover?: (index: number | null) => void
  formatValue: (value: number) => string
  labelWidth?: number
  className?: string
}) {
  return (
    <div className={`flex flex-col items-end ${className}`}>
      {slices.map((slice, i) => (
        <div
          key={slice.key}
          onMouseEnter={() => onHover?.(i)}
          onMouseLeave={() => onHover?.(null)}
          className="grid items-center gap-[9px] py-[3px] px-[2px] rounded-[7px] justify-items-end w-full row-hover-soft transition-opacity"
          style={{
            gridTemplateColumns: `auto minmax(${labelWidth}px, auto) 7px`,
            opacity: activeIndex === null || activeIndex === i ? 1 : 0.55,
            cursor: onHover ? 'pointer' : 'default',
          }}
        >
          <span className="text-[11.5px] font-bold tabular-nums whitespace-nowrap">{formatValue(slice.value)}</span>
          <span className="text-[11.5px] text-ledger-text-muted whitespace-nowrap truncate max-w-[150px]">{slice.label}</span>
          <span className="w-[7px] h-[7px] rounded-full" style={{ background: slice.color }} />
        </div>
      ))}
    </div>
  )
}
