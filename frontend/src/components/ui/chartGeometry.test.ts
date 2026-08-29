import { describe, expect, it } from 'vitest'
import { areaLinePoints, donutArcs, nearestIndex, samplePath, smoothPath } from './chartGeometry'

const W = 1000
const H = 300
const PAD = 20

describe('areaLinePoints', () => {
  it('spaces points evenly by index when no times are given', () => {
    const points = areaLinePoints([10, 20, 30], W, H, PAD)
    expect(points.map(p => p.x)).toEqual([0, 500, 1000])
  })

  it('maps the min to the bottom padding and the max to the top padding', () => {
    const [lo, mid, hi] = areaLinePoints([10, 20, 30], W, H, PAD)
    expect(lo.y).toBe(H - PAD)
    expect(hi.y).toBe(PAD)
    expect(mid.y).toBe((PAD + (H - PAD)) / 2)
  })

  it('centres a flat series instead of pinning it to the floor', () => {
    const points = areaLinePoints([24, 24, 24], W, H, PAD)
    expect(points.every(p => p.y === H / 2)).toBe(true)
  })

  it('plots sparse snapshots on a time axis so a one-day pair does not eat half the width', () => {
    // Production shape: two July snapshots, then today. Index spacing put
    // the $6k rise in the right half (then the Overview mask erased it).
    const jul7 = Date.parse('2026-07-07T00:00:00')
    const jul8 = Date.parse('2026-07-08T00:00:00')
    const aug28 = Date.parse('2026-08-28T00:00:00')
    const day = 24 * 60 * 60 * 1000
    const span = aug28 - jul7

    const points = areaLinePoints(
      [18646.68, 18637.42, 24649.61],
      W,
      H,
      PAD,
      [jul7, jul8, aug28],
    )

    expect(points[0].x).toBe(0)
    expect(points[2].x).toBe(W)
    expect(points[1].x).toBeCloseTo((day / span) * W, 5)
    expect(points[1].x).toBeLessThan(W * 0.05)
    expect(points[2].y).toBe(PAD)
    expect(points[1].y).toBe(H - PAD)
  })

  it('does not loop left or below the min when two snapshots are one day apart', () => {
    const jul7 = Date.parse('2026-07-07T00:00:00')
    const jul8 = Date.parse('2026-07-08T00:00:00')
    const aug28 = Date.parse('2026-08-28T00:00:00')
    const points = areaLinePoints(
      [18646.68, 18637.42, 24649.61],
      W,
      H,
      PAD,
      [jul7, jul8, aug28],
    )
    const minY = Math.min(...points.map(p => p.y))
    const maxY = Math.max(...points.map(p => p.y))
    const samples = samplePath(smoothPath(points), 40)
    expect(Math.min(...samples.map(p => p.x))).toBeGreaterThanOrEqual(-0.5)
    expect(Math.min(...samples.map(p => p.y))).toBeGreaterThanOrEqual(minY - 0.5)
    expect(Math.max(...samples.map(p => p.y))).toBeLessThanOrEqual(maxY + 0.5)
  })

  it('honours asymmetric top/bottom padding', () => {
    const padding = { top: 10, bottom: 80 }
    const [lo, hi] = areaLinePoints([0, 100], W, H, padding)
    expect(hi.y).toBe(10)
    expect(lo.y).toBe(H - 80)
  })
})

describe('donutArcs', () => {
  // $40 is ~0.19% of this book — under the 0.47% design gutter, so the old
  // layout skipped those paths and left a hole under 12 o'clock.
  const tail = Array(25).fill(40)
  const values = [6983, 2374, 1875, 1517, 983, 895, 680, ...tail]

  it('still paints holdings smaller than the design gap', () => {
    const arcs = donutArcs(values)
    expect(arcs).toHaveLength(values.length)
    for (const arc of arcs) {
      expect(arc.a1 - arc.a0).toBeGreaterThan(0.01)
    }
  })

  it('does not leave a hole at 12 o\'clock when the tail is many tiny holdings', () => {
    const arcs = donutArcs(values)
    const wrapGap = arcs[0].a0 + 2 * Math.PI - arcs[arcs.length - 1].a1
    expect(wrapGap).toBeGreaterThan(0)
    expect(wrapGap).toBeLessThan(0.05)
  })

  it('keeps a gutter between large slices', () => {
    const [a, b] = donutArcs([6000, 4000, 3000])
    expect(b.a0 - a.a1).toBeGreaterThan(0.01)
  })
})

describe('nearestIndex', () => {
  it('picks the closest point by x, not by uniform index', () => {
    const points = areaLinePoints(
      [1, 1, 2],
      W,
      H,
      PAD,
      [0, 10, 1000],
    )
    expect(nearestIndex(points, 0)).toBe(0)
    expect(nearestIndex(points, 30)).toBe(1)
    expect(nearestIndex(points, 800)).toBe(2)
  })
})
