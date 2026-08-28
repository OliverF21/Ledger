/**
 * Hand-rolled SVG charts for the V2 design language.
 *
 * These replace Recharts for the two hero visuals (the drawn area line and
 * the ring donut). Recharts can't produce either without fighting it:
 * the line needs a mask-faded, stroke-dashoffset draw-in that spills outside
 * its box, and the donut needs uniform-width annulus sectors with per-arc
 * hover glow. Both are a few dozen lines as raw SVG, and the result is
 * pixel-identical to the handoff. Recharts stays in use for the denser
 * analytical charts on Trends/Cash Flow, where its axes and tooltips earn
 * their weight.
 */
import { useCallback, useId, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import { alphaColor, mixHex } from '../../utils/color'

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

export interface AreaLineHover {
  index: number
  value: number
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
  /** Scrub along the series. `null` on pointer leave. */
  onHover?: (point: AreaLineHover | null) => void
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
  onHover,
}: AreaLineChartProps) {
  const gradientId = useId()
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const notifiedIndex = useRef<number | null>(null)

  const min = values.length === 0 ? 0 : Math.min(...values)
  const max = values.length === 0 ? 0 : Math.max(...values)
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

  const indexFromClientX = useCallback((clientX: number, target: HTMLElement) => {
    const rect = target.getBoundingClientRect()
    if (rect.width <= 0 || values.length === 0) return 0
    const t = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return values.length === 1 ? 0 : Math.round(t * (values.length - 1))
  }, [values.length])

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const next = indexFromClientX(event.clientX, event.currentTarget)
    if (notifiedIndex.current === next) return
    notifiedIndex.current = next
    setHoverIndex(next)
    onHover?.({ index: next, value: values[next] })
  }, [indexFromClientX, onHover, values])

  const handlePointerLeave = useCallback(() => {
    notifiedIndex.current = null
    setHoverIndex(null)
    onHover?.(null)
  }, [onHover])

  if (values.length === 0) return null

  const hoverPoint = hoverIndex !== null ? points[hoverIndex] ?? null : null
  const xPct = hoverPoint && width > 0 ? (hoverPoint.x / width) * 100 : 0
  const yPct = hoverPoint && height > 0 ? (hoverPoint.y / height) * 100 : 0

  return (
    <div
      className={`relative ${className}`}
      style={style}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        style={{ overflow: 'visible', pointerEvents: 'none', WebkitMaskImage: maskImage, maskImage }}
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

      {/* Cursor lives in HTML, not the stretched SVG: preserveAspectRatio="none"
          would squash a circle into an ellipse, and the series mask would
          fade the rail out with the line. */}
      {hoverPoint && (
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div
            className="absolute top-0 bottom-0 w-px"
            style={{
              left: `${xPct}%`,
              background: `linear-gradient(180deg, transparent 0%, ${color}99 10%, ${color} 50%, ${color}99 90%, transparent 100%)`,
              boxShadow: `0 0 12px ${color}66`,
            }}
          />
          <div
            className="absolute h-[9px] w-[9px] rounded-full"
            style={{
              left: `${xPct}%`,
              top: `${yPct}%`,
              transform: 'translate(-50%, -50%)',
              background: color,
              boxShadow: `0 0 0 2px rgba(8,11,15,0.92), 0 0 0 3.5px ${color}, 0 0 16px ${color}cc`,
            }}
          />
        </div>
      )}
    </div>
  )
}

/* ── Donut ────────────────────────────────────────────────────────────── */

export interface DonutSlice {
  key: string
  label: string
  value: number
  color: string
}

const DONUT_VB = 200
const DONUT_CX = 100
const DONUT_CY = 100
/** ViewBox units reserved so the outer arc + hover outset never meet the clip. */
const DONUT_PAD = 8
const DONUT_HOVER_OUTSET = 3
/** ~0.47% of the ring — a hair under 2° — matching the design's gap. */
const DONUT_GAP_FRAC = 0.0047

function polar(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
}

/** Closed annulus sector. Angles in radians, 0 = 3 o'clock, clockwise. */
function annulusPath(
  cx: number,
  cy: number,
  rInner: number,
  rOuter: number,
  a0: number,
  a1: number,
): string {
  const delta = a1 - a0
  if (delta <= 0.0001) return ''
  const large = delta > Math.PI ? 1 : 0
  const o0 = polar(cx, cy, rOuter, a0)
  const o1 = polar(cx, cy, rOuter, a1)
  const i1 = polar(cx, cy, rInner, a1)
  const i0 = polar(cx, cy, rInner, a0)
  return [
    `M${o0.x.toFixed(3)} ${o0.y.toFixed(3)}`,
    `A${rOuter} ${rOuter} 0 ${large} 1 ${o1.x.toFixed(3)} ${o1.y.toFixed(3)}`,
    `L${i1.x.toFixed(3)} ${i1.y.toFixed(3)}`,
    `A${rInner} ${rInner} 0 ${large} 0 ${i0.x.toFixed(3)} ${i0.y.toFixed(3)}`,
    'Z',
  ].join(' ')
}

/** Ring donut drawn as filled annulus sectors. Stroke-dash circles clip against
 *  the SVG viewBox (and get worse under a CSS rotate); filled paths stay inside
 *  the box and keep a true circular outer edge. */
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
  /** Mid-line radius in the 200×200 viewBox, not in px. Fitted down if the
   *  stroke would otherwise paint through the viewBox clip. */
  radius?: number
  size?: number
  strokeWidth?: number
  activeIndex?: number | null
  onHover?: (index: number | null) => void
  /** Centre label. */
  children?: React.ReactNode
}) {
  const gradientId = useId()
  const total = slices.reduce((sum, slice) => sum + Math.max(0, slice.value), 0)

  const requestedOuter = radius + strokeWidth / 2
  const maxOuter = DONUT_VB / 2 - DONUT_PAD - DONUT_HOVER_OUTSET
  const fit = requestedOuter > maxOuter ? maxOuter / requestedOuter : 1
  const rOuter = requestedOuter * fit
  const rInner = Math.max(0, (radius - strokeWidth / 2) * fit)
  const rMid = (rInner + rOuter) / 2
  const trackWidth = rOuter - rInner

  const gapRad = 2 * Math.PI * DONUT_GAP_FRAC
  let angle = -Math.PI / 2
  const arcs = slices.map(slice => {
    const fraction = total > 0 ? Math.max(0, slice.value) / total : 0
    const sweep = fraction * 2 * Math.PI
    const a0 = angle + gapRad / 2
    const a1 = angle + sweep - gapRad / 2
    angle += sweep
    return { slice, a0, a1 }
  })

  const glowColor = activeIndex !== null && slices[activeIndex]
    ? slices[activeIndex].color
    : '#82a9f2'

  // `filter: blur()` is clipped to the element's box. Size the wrapper past
  // 2× the blur radius so the halo can fade out instead of terminating in a
  // hard vertical edge at 3 o'clock. Fade to same-color 0-alpha — CSS
  // `transparent` interpolates through black and posters on dark glass.
  const outerBlur = Math.round(size * 0.14)
  const outerDisk = Math.round(size * 1.12)
  const outerBox = outerDisk + outerBlur * 2
  const coreBlur = Math.round(size * 0.09)
  const coreDisk = Math.round(size * 0.52)
  const coreBox = coreDisk + coreBlur * 2

  return (
    <div className="relative flex-shrink-0 overflow-visible" style={{ width: size, height: size }}>
      <div
        className="absolute left-1/2 top-1/2 pointer-events-none"
        style={{
          width: outerBox,
          height: outerBox,
          transform: 'translate(-50%, -50%)',
          filter: `blur(${outerBlur}px)`,
        }}
      >
        <div
          className="absolute left-1/2 top-1/2 rounded-full transition-[background] duration-300"
          style={{
            width: outerDisk,
            height: outerDisk,
            transform: 'translate(-50%, -50%)',
            background: `radial-gradient(circle, ${alphaColor(glowColor, 0.24)} 0%, ${alphaColor(glowColor, 0.15)} 34%, ${alphaColor(glowColor, 0.07)} 58%, ${alphaColor(glowColor, 0)} 82%)`,
          }}
        />
      </div>
      <div
        className="absolute left-1/2 top-1/2 pointer-events-none"
        style={{
          width: coreBox,
          height: coreBox,
          transform: 'translate(-50%, -50%)',
          filter: `blur(${coreBlur}px)`,
        }}
      >
        <div
          className="absolute left-1/2 top-1/2 rounded-full"
          style={{
            width: coreDisk,
            height: coreDisk,
            transform: 'translate(-50%, -50%)',
            background: `radial-gradient(circle, ${alphaColor('#bed4ff', 0.30)} 0%, ${alphaColor('#82a9f2', 0.13)} 46%, ${alphaColor('#82a9f2', 0)} 80%)`,
          }}
        />
      </div>
      <svg
        viewBox={`0 0 ${DONUT_VB} ${DONUT_VB}`}
        className="absolute inset-0 w-full h-full"
        style={{ overflow: 'visible' }}
      >
        <defs>
          {slices.map((slice, i) => (
            <radialGradient
              key={slice.key}
              id={`${gradientId}-${i}`}
              gradientUnits="userSpaceOnUse"
              cx={DONUT_CX - 16}
              cy={DONUT_CY - 16}
              r={rOuter + 8}
              fx={DONUT_CX - 22}
              fy={DONUT_CY - 22}
            >
              <stop offset="0%" stopColor={mixHex(slice.color, '#ffffff', 0.22)} stopOpacity={0.98} />
              <stop offset="48%" stopColor={slice.color} stopOpacity={0.94} />
              <stop offset="100%" stopColor={mixHex(slice.color, '#0a0c11', 0.12)} stopOpacity={0.88} />
            </radialGradient>
          ))}
        </defs>
        <circle
          cx={DONUT_CX}
          cy={DONUT_CY}
          r={rMid}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={trackWidth}
        />
        {arcs.map(({ slice, a0, a1 }, i) => {
          const hovered = activeIndex === i
          const outer = hovered ? rOuter + DONUT_HOVER_OUTSET : rOuter
          return (
            <path
              key={slice.key}
              d={annulusPath(DONUT_CX, DONUT_CY, rInner, outer, a0, a1)}
              fill={`url(#${gradientId}-${i})`}
              style={{
                cursor: onHover ? 'pointer' : 'default',
                transition: 'opacity .18s ease, filter .18s ease',
                opacity: activeIndex === null || hovered ? 1 : 0.55,
                filter: hovered ? `drop-shadow(0 0 10px ${slice.color}b3)` : undefined,
              }}
              onMouseEnter={() => onHover?.(i)}
              onMouseLeave={() => onHover?.(null)}
            />
          )
        })}
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
