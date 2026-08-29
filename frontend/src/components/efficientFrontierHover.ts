export const MARKER_SNAP_PX = 28

export type HoverKind = 'marker' | 'frontier'

export interface PlotRect {
  left: number
  top: number
  right: number
  bottom: number
}

export interface HoverMarker {
  name: string
  label: string
  color: string
  x: number
  y: number
  volatility_pct: number
  return_pct: number
  sharpe: number | null
}

export interface HoverFrontierPoint {
  x: number
  y: number
  volatility_pct: number
  return_pct: number
}

export interface FrontierHover {
  kind: HoverKind
  name?: string
  label: string
  color: string
  volatility_pct: number
  return_pct: number
  sharpe: number | null
  x: number
  y: number
}

function inPlot(pointer: { x: number; y: number }, plot: PlotRect): boolean {
  return pointer.x >= plot.left && pointer.x <= plot.right
    && pointer.y >= plot.top && pointer.y <= plot.bottom
}

export function pickFrontierHover(
  pointer: { x: number; y: number },
  plot: PlotRect,
  markers: HoverMarker[],
  frontier: HoverFrontierPoint[],
): FrontierHover | null {
  if (!inPlot(pointer, plot)) return null

  let nearestMarker: HoverMarker | null = null
  let markerDist = Infinity
  for (const marker of markers) {
    const d = Math.hypot(pointer.x - marker.x, pointer.y - marker.y)
    if (d < markerDist) {
      markerDist = d
      nearestMarker = marker
    }
  }
  if (nearestMarker && markerDist <= MARKER_SNAP_PX) {
    return {
      kind: 'marker',
      name: nearestMarker.name,
      label: nearestMarker.label,
      color: nearestMarker.color,
      volatility_pct: nearestMarker.volatility_pct,
      return_pct: nearestMarker.return_pct,
      sharpe: nearestMarker.sharpe,
      x: nearestMarker.x,
      y: nearestMarker.y,
    }
  }

  if (frontier.length === 0) return null

  let nearest = frontier[0]
  let bestX = Math.abs(pointer.x - nearest.x)
  for (let i = 1; i < frontier.length; i++) {
    const d = Math.abs(pointer.x - frontier[i].x)
    if (d < bestX) {
      bestX = d
      nearest = frontier[i]
    }
  }
  return {
    kind: 'frontier',
    label: 'Efficient frontier',
    color: '#82a9f2',
    volatility_pct: nearest.volatility_pct,
    return_pct: nearest.return_pct,
    sharpe: null,
    x: nearest.x,
    y: nearest.y,
  }
}
