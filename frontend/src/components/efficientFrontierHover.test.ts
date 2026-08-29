import { describe, expect, it } from 'vitest'
import { MARKER_SNAP_PX, pickFrontierHover } from './efficientFrontierHover'

const PLOT = { left: 56, top: 20, right: 740, bottom: 378 }

const current = {
  name: 'current',
  label: 'Current',
  color: '#adb8cb',
  x: 200,
  y: 220,
  volatility_pct: 17.7,
  return_pct: 27.4,
  sharpe: 1.26,
}

const maxSharpe = {
  name: 'max_sharpe',
  label: 'Max Sharpe',
  color: '#f4907f',
  x: 400,
  y: 80,
  volatility_pct: 36.0,
  return_pct: 60.9,
  sharpe: 1.55,
}

const frontier = [
  { x: 199, y: 360, volatility_pct: 17.5, return_pct: 10.0 },
  { x: 250, y: 110, volatility_pct: 22.0, return_pct: 40.0 },
  { x: 401, y: 81, volatility_pct: 36.1, return_pct: 60.8 },
]

describe('pickFrontierHover', () => {
  it('returns null when the pointer is outside the plot', () => {
    expect(pickFrontierHover({ x: 10, y: 200 }, PLOT, [current], frontier)).toBeNull()
    expect(pickFrontierHover({ x: 200, y: 400 }, PLOT, [current], frontier)).toBeNull()
  })

  it('snaps to the nearest marker when the pointer is inside the marker radius', () => {
    const hover = pickFrontierHover(
      { x: current.x + 8, y: current.y - 6 },
      PLOT,
      [current, maxSharpe],
      frontier,
    )
    expect(hover?.kind).toBe('marker')
    expect(hover?.label).toBe('Current')
    expect(hover?.name).toBe('current')
    expect(hover?.sharpe).toBe(1.26)
  })

  it('prefers a marker over a closer-in-x frontier point', () => {
    const hover = pickFrontierHover(
      { x: current.x, y: current.y },
      PLOT,
      [current],
      frontier,
    )
    expect(hover?.kind).toBe('marker')
    expect(hover?.label).toBe('Current')
  })

  it('reads the frontier at the pointer volatility when no marker is nearby', () => {
    // Closer in 2D to the x=250 point, but nearer in x to the x=199 point.
    const pointer = { x: 205, y: 120 }
    const distToCurrent = Math.hypot(pointer.x - current.x, pointer.y - current.y)
    expect(distToCurrent).toBeGreaterThan(MARKER_SNAP_PX)

    const hover = pickFrontierHover(pointer, PLOT, [current, maxSharpe], frontier)
    expect(hover?.kind).toBe('frontier')
    expect(hover?.label).toBe('Efficient frontier')
    expect(hover?.volatility_pct).toBe(17.5)
    expect(hover?.return_pct).toBe(10.0)
  })

  it('returns null in empty space when there is no frontier to read', () => {
    expect(pickFrontierHover({ x: 500, y: 200 }, PLOT, [current], [])).toBeNull()
  })
})
