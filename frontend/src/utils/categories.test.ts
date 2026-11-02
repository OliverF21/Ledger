import { describe, expect, it } from 'vitest'
import {
  categoryFilterOptions,
  formatCategory,
  formatTransactionCategory,
  transactionMatchesCategoryFilter,
} from './categories'

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

describe('transactionMatchesCategoryFilter', () => {
  const clothing = {
    category_plaid: 'GENERAL_MERCHANDISE',
    category_plaid_detailed: 'GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES',
  }
  const electronics = {
    category_plaid: 'GENERAL_MERCHANDISE',
    category_plaid_detailed: 'GENERAL_MERCHANDISE_ELECTRONICS',
  }
  const shoppingParent = { category_plaid: 'GENERAL_MERCHANDISE' }
  const coffee = {
    category_plaid: 'FOOD_AND_DRINK',
    category_plaid_detailed: 'FOOD_AND_DRINK_COFFEE',
  }

  it('includes every subcategory when a broad category is selected', () => {
    for (const selected of ['GENERAL_MERCHANDISE', 'Shopping', 'SHOPPING']) {
      expect(transactionMatchesCategoryFilter(clothing, selected)).toBe(true)
      expect(transactionMatchesCategoryFilter(electronics, selected)).toBe(true)
      expect(transactionMatchesCategoryFilter(shoppingParent, selected)).toBe(true)
      expect(transactionMatchesCategoryFilter({ category_user: 'Clothing & Accessories' }, selected)).toBe(true)
      expect(transactionMatchesCategoryFilter(coffee, selected)).toBe(false)
    }
  })

  it('keeps a specific subcategory from pulling in its siblings', () => {
    expect(transactionMatchesCategoryFilter(clothing, 'GENERAL_MERCHANDISE_ELECTRONICS')).toBe(false)
    expect(transactionMatchesCategoryFilter(electronics, 'GENERAL_MERCHANDISE_ELECTRONICS')).toBe(true)
    expect(transactionMatchesCategoryFilter(clothing, 'Clothing & Accessories')).toBe(false)
    expect(transactionMatchesCategoryFilter({ category_user: 'Clothing & Accessories' }, 'Clothing & Accessories')).toBe(true)
  })

  it('respects a user category instead of the Plaid parent', () => {
    expect(transactionMatchesCategoryFilter({
      category_user: 'Vacation',
      category_plaid: 'GENERAL_MERCHANDISE',
      category_plaid_detailed: 'GENERAL_MERCHANDISE_ELECTRONICS',
    }, 'Shopping')).toBe(false)
  })

  it('adds a parent option when only subcategories are present', () => {
    const options = categoryFilterOptions([
      'GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES',
      'GENERAL_MERCHANDISE_ELECTRONICS',
      'FOOD_AND_DRINK_COFFEE',
    ])
    expect(options).toContain('GENERAL_MERCHANDISE')
    expect(options).toContain('FOOD_AND_DRINK')
    expect(options).toContain('GENERAL_MERCHANDISE_ELECTRONICS')
  })
})
