import { describe, expect, it } from 'vitest'
import { budgetAvailable, budgetRollover } from './budgets'

describe('budgetAvailable', () => {
  it('adds unspent rollover on top of the monthly limit', () => {
    expect(budgetAvailable({ limit: 400, rollover: 100 })).toBe(500)
  })

  it('shrinks the cap when prior months were overspent', () => {
    expect(budgetAvailable({ limit: 400, rollover: -50 })).toBe(350)
  })

  it('ignores rollover on the virtual misc bucket', () => {
    expect(budgetAvailable({ limit: 0, rollover: 40, virtual: true })).toBe(0)
  })

  it('treats a missing rollover as zero', () => {
    expect(budgetRollover({})).toBe(0)
    expect(budgetAvailable({ limit: 400 })).toBe(400)
  })
})
