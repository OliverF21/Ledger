import { describe, expect, it } from 'vitest'
import {
  cashFlowSpendBucket,
  displayRollupCategory,
  drillFromCashFlowNode,
  flowDrillLabel,
  incomeSourceCategory,
  readTransactionQuery,
  transactionMatchesFlow,
  transactionSearchParams,
} from './cashFlowDrill'

describe('cashFlowSpendBucket', () => {
  it('keeps the standard chart on the primary', () => {
    expect(cashFlowSpendBucket('Restaurants', 'GENERAL_MERCHANDISE', null)).toBe('FOOD_AND_DRINK')
    expect(cashFlowSpendBucket('Dining Out', 'FOOD_AND_DRINK', 'FOOD_AND_DRINK_GROCERIES')).toBe('FOOD_AND_DRINK')
    expect(cashFlowSpendBucket('Coffee', null, null)).toBe('FOOD_AND_DRINK')
    expect(cashFlowSpendBucket(null, 'FOOD_AND_DRINK', 'FOOD_AND_DRINK_GROCERIES')).toBe('FOOD_AND_DRINK')
    expect(cashFlowSpendBucket('Gas', 'GENERAL_MERCHANDISE', null)).toBe('TRANSPORTATION')
    expect(cashFlowSpendBucket('Rideshare & Taxis', null, null)).toBe('TRANSPORTATION')
    expect(cashFlowSpendBucket(null, 'TRANSPORTATION', 'TRANSPORTATION_PARKING')).toBe('TRANSPORTATION')
    expect(cashFlowSpendBucket(null, 'RENT_AND_UTILITIES', 'RENT_AND_UTILITIES_RENT')).toBe('RENT_AND_UTILITIES')
    expect(cashFlowSpendBucket('Gas & Electric', null, null)).toBe('RENT_AND_UTILITIES')
    expect(cashFlowSpendBucket('Internet & Cable', null, null)).toBe('RENT_AND_UTILITIES')
    expect(cashFlowSpendBucket(null, 'FOOD_AND_DRINK', null)).toBe('FOOD_AND_DRINK')
    expect(cashFlowSpendBucket('Flights', null, null)).toBe('TRAVEL')
    expect(cashFlowSpendBucket('Paycheck', null, null)).toBe('Paycheck')
  })

  it('splits each activity in expanded view and keeps a chosen parent together', () => {
    expect(cashFlowSpendBucket('Coffee', null, null, true)).toBe('Coffee')
    expect(cashFlowSpendBucket('Dining Out', 'FOOD_AND_DRINK', 'FOOD_AND_DRINK_GROCERIES', true)).toBe('Restaurants')
    expect(cashFlowSpendBucket(null, 'FOOD_AND_DRINK', 'FOOD_AND_DRINK_FAST_FOOD', true)).toBe('Fast Food')
    expect(cashFlowSpendBucket(null, 'FOOD_AND_DRINK', 'FOOD_AND_DRINK_GROCERIES', true)).toBe('Groceries')
    expect(cashFlowSpendBucket('Gas', null, null, true)).toBe('Gas')
    expect(cashFlowSpendBucket('Rideshare & Taxis', null, null, true)).toBe('Rideshare & Taxis')
    expect(cashFlowSpendBucket('Gas & Electric', null, null, true)).toBe('Gas & Electric')
    expect(cashFlowSpendBucket(null, 'ENTERTAINMENT', 'ENTERTAINMENT_VIDEO_GAMES', true)).toBe('Video Games')
    expect(cashFlowSpendBucket(null, 'FOOD_AND_DRINK', null, true)).toBe('FOOD_AND_DRINK')
    expect(cashFlowSpendBucket(null, 'FOOD_AND_DRINK', 'FOOD_AND_DRINK.GROCERIES', true)).toBe('Groceries')
    expect(cashFlowSpendBucket(null, 'SHOPPING', 'SHOPPING.ELECTRONICS', true)).toBe('Electronics')
    expect(cashFlowSpendBucket('Transportation', 'TRANSPORTATION', 'TRANSPORTATION_GAS', true)).toBe('TRANSPORTATION')
  })

  it('lets a user category beat a Plaid investment transfer', () => {
    expect(displayRollupCategory({
      category_user: 'Restaurants',
      category_plaid: 'TRANSFER_OUT',
      category_plaid_detailed: 'TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS',
    })).toBe('FOOD_AND_DRINK')
    expect(displayRollupCategory({
      category_plaid: 'TRANSFER_OUT',
      category_plaid_detailed: 'TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS',
    })).toBe('Investments')
  })
})

describe('transactionMatchesFlow', () => {
  const groceries = { category_plaid: 'FOOD_AND_DRINK', category_plaid_detailed: 'FOOD_AND_DRINK_GROCERIES' }
  const coffee = { category_plaid: 'FOOD_AND_DRINK', category_plaid_detailed: 'FOOD_AND_DRINK_COFFEE' }
  const dining = { category_user: 'Dining Out', category_plaid: 'FOOD_AND_DRINK' }
  const plainFood = { category_plaid: 'FOOD_AND_DRINK' }
  const gas = { category_plaid: 'TRANSPORTATION', category_plaid_detailed: 'TRANSPORTATION_GAS' }

  it('matches every transaction in a collapsed category and that month is applied separately', () => {
    const drill = { kind: 'spend' as const, id: 'FOOD_AND_DRINK' }
    expect(transactionMatchesFlow(groceries, drill)).toBe(true)
    expect(transactionMatchesFlow(coffee, drill)).toBe(true)
    expect(transactionMatchesFlow(dining, drill)).toBe(true)
    expect(transactionMatchesFlow(plainFood, drill)).toBe(true)
    expect(transactionMatchesFlow(gas, drill)).toBe(false)
  })

  it('matches one expanded activity, the parent bar, and the Other remainder', () => {
    expect(transactionMatchesFlow(coffee, { kind: 'activity', id: 'Coffee', parentId: 'FOOD_AND_DRINK' })).toBe(true)
    expect(transactionMatchesFlow(groceries, { kind: 'activity', id: 'Coffee', parentId: 'FOOD_AND_DRINK' })).toBe(false)
    expect(transactionMatchesFlow(dining, { kind: 'activity', id: 'Restaurants', parentId: 'FOOD_AND_DRINK' })).toBe(true)
    expect(transactionMatchesFlow(plainFood, { kind: 'activity', id: 'other:FOOD_AND_DRINK', parentId: 'FOOD_AND_DRINK' })).toBe(true)
    expect(transactionMatchesFlow(coffee, { kind: 'activity', id: 'other:FOOD_AND_DRINK', parentId: 'FOOD_AND_DRINK' })).toBe(false)
    expect(transactionMatchesFlow(coffee, { kind: 'group', id: 'FOOD_AND_DRINK' })).toBe(true)
    expect(transactionMatchesFlow(gas, { kind: 'group', id: 'FOOD_AND_DRINK' })).toBe(false)
  })

  it('matches income bands, including custom labels and interest credits', () => {
    expect(incomeSourceCategory({ category_user: 'Paycheck' })).toBe('Paycheck')
    expect(transactionMatchesFlow({ category_user: 'Paycheck' }, { kind: 'income', id: 'Paycheck' })).toBe(true)
    expect(transactionMatchesFlow(
      { category_plaid: 'INCOME', category_plaid_detailed: 'INCOME_WAGES' },
      { kind: 'income', id: 'INCOME_WAGES' },
    )).toBe(true)
    expect(transactionMatchesFlow(
      { category_user: 'Paycheck' },
      { kind: 'income', id: 'INCOME_WAGES' },
    )).toBe(false)
    expect(incomeSourceCategory({
      category_plaid: 'TRANSFER_IN',
      merchant: 'Interest paid',
    })).toBe('INCOME_INTEREST_EARNED')
    expect(incomeSourceCategory({
      merchant: 'Credit card cash back',
      category_plaid: 'INCOME',
    })).toBe('Cash Back')
  })
})

describe('transaction query', () => {
  it('round-trips a cash-flow drill and a manual category', () => {
    const drill = transactionSearchParams({
      month: '2026-06',
      category: 'all',
      drill: { kind: 'activity', id: 'Coffee', parentId: 'FOOD_AND_DRINK' },
      label: 'Coffee',
    })
    expect(readTransactionQuery(`?${drill.toString()}`)).toEqual({
      month: '2026-06',
      category: 'all',
      drill: { kind: 'activity', id: 'Coffee', parentId: 'FOOD_AND_DRINK' },
      label: 'Coffee',
    })

    const manual = transactionSearchParams({
      month: 'all',
      category: 'FOOD_AND_DRINK_COFFEE',
      drill: null,
      label: '',
    })
    expect(readTransactionQuery(`?${manual.toString()}`)).toEqual({
      month: 'all',
      category: 'FOOD_AND_DRINK_COFFEE',
      drill: null,
      label: '',
    })
  })

  it('labels an Other remainder when the chart label was not passed', () => {
    expect(flowDrillLabel({ kind: 'activity', id: 'other:FOOD_AND_DRINK', parentId: 'FOOD_AND_DRINK' }, '')).toBe('Other · Food & Drink')
  })

  it('describes which band was opened', () => {
    expect(drillFromCashFlowNode({ id: 'Paycheck', side: 'left' })).toEqual({ kind: 'income', id: 'Paycheck' })
    expect(drillFromCashFlowNode({ id: 'FOOD_AND_DRINK', side: 'mid' })).toEqual({ kind: 'group', id: 'FOOD_AND_DRINK' })
    expect(drillFromCashFlowNode({ id: 'Coffee', side: 'right', parent_id: 'FOOD_AND_DRINK' })).toEqual({
      kind: 'activity',
      id: 'Coffee',
      parentId: 'FOOD_AND_DRINK',
    })
    expect(drillFromCashFlowNode({ id: 'FOOD_AND_DRINK', side: 'right' })).toEqual({ kind: 'spend', id: 'FOOD_AND_DRINK' })
  })
})
