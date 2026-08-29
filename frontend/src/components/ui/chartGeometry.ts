/** Pure layout helpers for AreaLineChart. Kept separate so the scale can be
 *  tested without mounting SVG. */

export type AreaLinePadding = number | { top?: number; right?: number; bottom?: number; left?: number }

export function resolvePadding(padding: AreaLinePadding = 20): {
  top: number
  right: number
  bottom: number
  left: number
} {
  if (typeof padding === 'number') {
    // A number is the original vertical inset. Horizontal inset stays 0 so the
    // curve still spans the full width (the Overview hero bleeds 18px off-canvas).
    return { top: padding, right: 0, bottom: padding, left: 0 }
  }
  return {
    top: padding.top ?? 20,
    right: padding.right ?? 0,
    bottom: padding.bottom ?? 20,
    left: padding.left ?? 0,
  }
}

function xAt(index: number, count: number, innerWidth: number, times: number[] | undefined): number {
  if (count <= 1) return innerWidth / 2
  if (!times || times.length !== count) {
    return (index / (count - 1)) * innerWidth
  }
  const start = times[0]
  const span = times[count - 1] - start
  if (span <= 0) return (index / (count - 1)) * innerWidth
  return ((times[index] - start) / span) * innerWidth
}

export function areaLinePoints(
  values: number[],
  width: number,
  height: number,
  padding: AreaLinePadding = 20,
  times?: number[],
): { x: number; y: number }[] {
  const pad = resolvePadding(padding)
  const min = values.length === 0 ? 0 : Math.min(...values)
  const max = values.length === 0 ? 0 : Math.max(...values)
  const span = max - min
  const usable = height - pad.top - pad.bottom
  const innerWidth = width - pad.left - pad.right
  const midY = pad.top + usable / 2

  return values.map((value, i) => ({
    x: pad.left + xAt(i, values.length, innerWidth, times),
    y: span === 0 ? midY : pad.top + (1 - (value - min) / span) * usable,
  }))
}

/** Monotone cubic (Fritsch–Carlson) through the points. Uniform Catmull-Rom
 *  loops off-canvas when two snapshots sit one day apart and the next is a
 *  month later — this stays inside the min/max band. */
export function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return ''
  if (points.length === 1) return `M${points[0].x} ${points[0].y}`
  if (points.length === 2) {
    return `M${points[0].x} ${points[0].y} L${points[1].x} ${points[1].y}`
  }

  const n = points.length
  const dx: number[] = []
  const m: number[] = []
  for (let i = 0; i < n - 1; i++) {
    const deltaX = points[i + 1].x - points[i].x
    dx.push(deltaX)
    m.push(deltaX === 0 ? 0 : (points[i + 1].y - points[i].y) / deltaX)
  }

  const t: number[] = new Array(n)
  t[0] = m[0]
  t[n - 1] = m[n - 2]
  for (let i = 1; i < n - 1; i++) {
    t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2
  }

  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) {
      t[i] = 0
      t[i + 1] = 0
      continue
    }
    const a = t[i] / m[i]
    const b = t[i + 1] / m[i]
    const s = a * a + b * b
    if (s > 9) {
      const tau = 3 / Math.sqrt(s)
      t[i] = tau * a * m[i]
      t[i + 1] = tau * b * m[i]
    }
  }

  let d = `M${points[0].x} ${points[0].y}`
  for (let i = 0; i < n - 1; i++) {
    const p1 = points[i]
    const p2 = points[i + 1]
    const seg = dx[i]
    if (seg === 0) continue
    const c1x = p1.x + seg / 3
    const c1y = p1.y + (t[i] * seg) / 3
    const c2x = p2.x - seg / 3
    const c2y = p2.y - (t[i + 1] * seg) / 3
    d += ` C${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`
  }
  return d
}

export function samplePath(d: string, stepsPerCurve = 12): { x: number; y: number }[] {
  const samples: { x: number; y: number }[] = []
  const move = /^M([-\d.]+) ([-\d.]+)/.exec(d)
  if (!move) return samples
  let x0 = Number(move[1])
  let y0 = Number(move[2])
  samples.push({ x: x0, y: y0 })
  const re = /C([-\d.]+) ([-\d.]+), ([-\d.]+) ([-\d.]+), ([-\d.]+) ([-\d.]+)/g
  let match: RegExpExecArray | null
  while ((match = re.exec(d))) {
    const c1x = Number(match[1])
    const c1y = Number(match[2])
    const c2x = Number(match[3])
    const c2y = Number(match[4])
    const x1 = Number(match[5])
    const y1 = Number(match[6])
    for (let s = 1; s <= stepsPerCurve; s++) {
      const t = s / stepsPerCurve
      const mt = 1 - t
      samples.push({
        x: mt * mt * mt * x0 + 3 * mt * mt * t * c1x + 3 * mt * t * t * c2x + t * t * t * x1,
        y: mt * mt * mt * y0 + 3 * mt * mt * t * c1y + 3 * mt * t * t * c2y + t * t * t * y1,
      })
    }
    x0 = x1
    y0 = y1
  }
  return samples
}

export function nearestIndex(points: { x: number }[], x: number): number {
  if (points.length === 0) return 0
  let best = 0
  let bestDist = Math.abs(points[0].x - x)
  for (let i = 1; i < points.length; i++) {
    const dist = Math.abs(points[i].x - x)
    if (dist < bestDist) {
      best = i
      bestDist = dist
    }
  }
  return best
}

/** ~0.47% of the ring — a hair under 2° — matching the design's gap. */
export const DONUT_GAP_FRAC = 0.0047
/** Floor so a hairline still reads at the 258px hero size (~2px of arc). */
export const DONUT_MIN_FRAC = 0.0045

/** Layout for Donut: start at 12 o'clock, clockwise. Tiny holdings get a
 *  visual floor so they still read as hairlines; a fixed gutter used to eat
 *  them and leave a hole under 12 o'clock. */
export function donutArcs(values: number[]): { a0: number; a1: number }[] {
  const total = values.reduce((sum, v) => sum + Math.max(0, v), 0)
  const positive = values.reduce((count, v) => count + (v > 0 ? 1 : 0), 0)
  const minFrac = positive > 0 ? Math.min(DONUT_MIN_FRAC, 0.5 / positive) : DONUT_MIN_FRAC
  const minValue = minFrac * total
  const weights = values.map(v => (v > 0 ? Math.max(v, minValue) : 0))
  const weightSum = weights.reduce((sum, w) => sum + w, 0)
  const gapRad = 2 * Math.PI * DONUT_GAP_FRAC
  const minPaint = 2 * Math.PI * 0.0025
  let angle = -Math.PI / 2
  return weights.map(weight => {
    const sweep = weightSum > 0 ? (weight / weightSum) * 2 * Math.PI : 0
    const gap = sweep <= 0 ? 0 : Math.min(gapRad, Math.max(0, sweep - minPaint))
    const a0 = angle + gap / 2
    const a1 = angle + sweep - gap / 2
    angle += sweep
    return { a0, a1 }
  })
}

