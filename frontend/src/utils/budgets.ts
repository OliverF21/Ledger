/** Signed leftover from earlier months. Missing or non-finite values count as zero. */
export function budgetRollover(budget: { rollover?: number | null }): number {
  const value = budget.rollover
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

/** Amount that can be spent this month: the monthly plan plus any rollover. */
export function budgetAvailable(budget: {
  limit: number
  rollover?: number | null
  virtual?: boolean
}): number {
  if (budget.virtual) return budget.limit
  return budget.limit + budgetRollover(budget)
}
