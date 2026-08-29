import { describe, expect, it } from 'vitest'
import { visibleAllocationSlices } from './allocationSlices'

function slice(label: string, value: number) {
  return { key: label, label, value, color: '#82a9f2' }
}

describe('visibleAllocationSlices', () => {
  it('keeps every holding instead of folding the tail into Miscellaneous', () => {
    const slices = [
      slice('VOO', 6983),
      slice('NVDA', 2374),
      slice('TSM', 1875),
      slice('SCHD', 1517),
      slice('GLD', 983),
      slice('QQQ', 895),
      slice('WMT', 680),
      slice('MSFT', 1200),
      slice('AMZN', 1100),
      slice('COST', 900),
      slice('BRK.B', 800),
    ]
    const visible = visibleAllocationSlices(slices)
    expect(visible.map(s => s.label)).toEqual(slices.map(s => s.label))
    expect(visible.find(s => s.key === '__other')).toBeUndefined()
  })
})
