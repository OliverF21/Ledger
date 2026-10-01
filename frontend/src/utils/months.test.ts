import { afterEach, describe, expect, it, vi } from 'vitest'
import { currentMonthValue, getMonthOptions } from './months'

afterEach(() => {
  vi.useRealTimers()
})

describe('getMonthOptions', () => {
  it('starts at October 2026 when that is the current month', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 1, 12, 0, 0))
    const options = getMonthOptions(6)
    expect(currentMonthValue()).toBe('2026-10')
    expect(options[0]).toMatchObject({ value: '2026-10', label: 'October 2026' })
    expect(options.map(o => o.value)).toEqual([
      '2026-10',
      '2026-09',
      '2026-08',
      '2026-07',
      '2026-06',
      '2026-05',
    ])
  })
})
