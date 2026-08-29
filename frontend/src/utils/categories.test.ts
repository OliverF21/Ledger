import { describe, expect, it } from 'vitest'
import { formatCategory, formatTransactionCategory } from './categories'

describe('formatCategory', () => {
  it('labels Plaid OTHER as Miscellaneous, not a blank or Other · Other', () => {
    expect(formatCategory('OTHER')).toBe('Miscellaneous')
    expect(formatCategory('OTHER_OTHER')).toBe('Miscellaneous')
    expect(formatCategory('OTHER.OTHER')).toBe('Miscellaneous')
  })

  it('does not return an empty string for whitespace-only input', () => {
    expect(formatCategory('   ')).toBe('Uncategorized')
  })
})

describe('formatTransactionCategory', () => {
  it('does not render Other · Other for the Plaid catch-all', () => {
    expect(
      formatTransactionCategory({
        category_plaid: 'OTHER',
        category_plaid_detailed: 'OTHER_OTHER',
      }),
    ).toBe('Miscellaneous')
  })

  it('keeps parent · sub labels for real subcategories', () => {
    expect(
      formatTransactionCategory({
        category_plaid: 'FOOD_AND_DRINK',
        category_plaid_detailed: 'FOOD_AND_DRINK_COFFEE',
      }),
    ).toBe('Food & Drink · Coffee')
  })
})
