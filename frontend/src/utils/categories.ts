// Maps Plaid PFC category strings to human-readable display names.
// Plaid returns things like "FOOD_AND_DRINK", "FOOD_AND_DRINK.RESTAURANTS",
// "RENT_AND_UTILITIES.GAS_AND_ELECTRICITY", etc.

import {
  PLAID_CATEGORIES,
  hierarchicalLabelForCategoryLabel,
  hierarchicalLabelForDetailedKey,
} from './plaidCategories'

const DETAILED_LABEL_BY_KEY = Object.fromEntries(
  PLAID_CATEGORIES.map(c => [c.detailed, c.label]),
)
const PRIMARY_LABEL_BY_KEY = Object.fromEntries(
  PLAID_CATEGORIES.map(c => [c.primary, c.primaryLabel]),
)

/** Merchant logo, else Plaid category icon from enrichment, else null. */
export function transactionDisplayIcon(txn: {
  merchant_logo_url?: string | null
  enrichment?: { category_icon_url?: string | null } | null
}): string | null {
  return txn.merchant_logo_url || txn.enrichment?.category_icon_url || null
}

const OVERRIDES: Record<string, string> = {
  FOOD_AND_DRINK: 'Food & Drink',
  'FOOD_AND_DRINK.GROCERIES': 'Groceries',
  'FOOD_AND_DRINK.RESTAURANTS': 'Dining Out',
  'FOOD_AND_DRINK.FAST_FOOD': 'Fast Food',
  'FOOD_AND_DRINK.COFFEE': 'Coffee',
  'FOOD_AND_DRINK.ALCOHOL_AND_BARS': 'Bars & Alcohol',
  TRANSPORTATION: 'Transportation',
  'TRANSPORTATION.GAS': 'Gas',
  'TRANSPORTATION.PARKING': 'Parking',
  'TRANSPORTATION.PUBLIC_TRANSIT': 'Public Transit',
  'TRANSPORTATION.TAXIS_AND_RIDE_SHARES': 'Rideshare',
  TRAVEL: 'Travel',
  'TRAVEL.FLIGHTS': 'Flights',
  'TRAVEL.LODGING': 'Lodging',
  'TRAVEL.RENTAL_CARS': 'Rental Cars',
  SHOPPING: 'Shopping',
  'SHOPPING.CLOTHING_AND_ACCESSORIES': 'Clothing & Accessories',
  'SHOPPING.ELECTRONICS': 'Electronics',
  'SHOPPING.SPORTING_GOODS': 'Sporting Goods',
  GENERAL_MERCHANDISE: 'Shopping',
  RENT_AND_UTILITIES: 'Rent & Utilities',
  'RENT_AND_UTILITIES.RENT': 'Rent',
  'RENT_AND_UTILITIES.GAS_AND_ELECTRICITY': 'Gas & Electric',
  'RENT_AND_UTILITIES.INTERNET_AND_CABLE': 'Internet & Cable',
  'RENT_AND_UTILITIES.TELEPHONE': 'Phone',
  'RENT_AND_UTILITIES.WATER': 'Water',
  ENTERTAINMENT: 'Entertainment',
  'ENTERTAINMENT.STREAMING_SERVICES': 'Streaming',
  'ENTERTAINMENT.MUSIC_AND_AUDIO': 'Music',
  'ENTERTAINMENT.VIDEO_GAMES': 'Video Games',
  PERSONAL_CARE: 'Personal Care',
  'PERSONAL_CARE.GYMS_AND_FITNESS_CENTERS': 'Gym & Fitness',
  'PERSONAL_CARE.HAIR_AND_BEAUTY': 'Hair & Beauty',
  MEDICAL: 'Medical',
  'MEDICAL.PHARMACIES_AND_SUPPLEMENTS': 'Pharmacy',
  'MEDICAL.DOCTOR_VISITS': 'Doctor',
  HOME_IMPROVEMENT: 'Home Improvement',
  LOAN_PAYMENTS: 'Loan Payments',
  'LOAN_PAYMENTS.CREDIT_CARD_PAYMENT': 'Credit Card Payment',
  'LOAN_PAYMENTS.MORTGAGE_PAYMENT': 'Mortgage',
  BANK_FEES: 'Bank Fees',
  INCOME: 'Income',
  'INCOME.WAGES': 'Wages',
  'INCOME.INTEREST_EARNED': 'Interest',
  TRANSFER_IN: 'Transfer In',
  TRANSFER_OUT: 'Transfer Out',
  TRANSFER: 'Transfer',
  GOVERNMENT_AND_NON_PROFIT: 'Government',
  EDUCATION: 'Education',
  'EDUCATION.TUITION': 'Tuition',
  PETS: 'Pets',
  GIFTS_AND_DONATIONS: 'Gifts & Donations',
  BUSINESS_SERVICES: 'Business Services',
  GENERAL_SERVICES: 'General Services',
  'GENERAL_SERVICES.AUTOMOTIVE': 'Auto Services',
  HYSA: 'HYSA',
  OTHER: 'Miscellaneous',
  'OTHER.OTHER': 'Miscellaneous',
  Other: 'Miscellaneous',
}

const NORMALIZED_OVERRIDES: Record<string, string> = Object.fromEntries(
  Object.entries(OVERRIDES).flatMap(([key, value]) => {
    const variants = new Set([key, key.replace(/\./g, '_')])
    return Array.from(variants).map(variant => [variant, value])
  })
)

export function displayCategory(t: {
  category_user?: string | null
  category_plaid_detailed?: string | null
  category_plaid?: string | null
}): string {
  return t.category_user || t.category_plaid_detailed || t.category_plaid || ''
}

/** True when a stored value looks like a Plaid PFC key (e.g. INCOME_SALARY). */
export function isPfcKey(raw: string): boolean {
  const normalized = raw.trim().toUpperCase().replace(/\./g, '_')
  return /^[A-Z][A-Z0-9_]*_[A-Z0-9_]+$/.test(normalized)
}

/** Label to seed the category picker input — never a raw PFC key. */
export function categoryPickerDraft(t: {
  category_user?: string | null
  category_plaid?: string | null
  category_plaid_detailed?: string | null
}): string {
  const raw = displayCategory(t)
  if (!raw) return ''

  if (t.category_user && !isPfcKey(t.category_user)) {
    return t.category_user.trim()
  }

  const normalized = raw.trim().toUpperCase().replace(/\./g, '_')
  const plaidEntry = PLAID_CATEGORIES.find(c => c.detailed === normalized)
  if (plaidEntry) return plaidEntry.label

  const hierarchical = hierarchicalLabelForDetailedKey(raw)
  if (hierarchical) {
    const parts = hierarchical.split(' · ')
    return parts[parts.length - 1] ?? hierarchical
  }

  const fromLabel = hierarchicalLabelForCategoryLabel(raw)
  if (fromLabel) {
    const parts = fromLabel.split(' · ')
    return parts[parts.length - 1] ?? fromLabel
  }

  if (isPfcKey(raw)) return formatCategory(raw)

  return raw.trim()
}

/** Human label: parent · subcategory when enrichment provides both; otherwise best available. */
export function formatTransactionCategory(t: {
  category_user?: string | null
  category_plaid?: string | null
  category_plaid_detailed?: string | null
}): string {
  if (
    !t.category_user &&
    t.category_plaid &&
    t.category_plaid_detailed &&
    t.category_plaid_detailed !== t.category_plaid
  ) {
    const hierarchical = hierarchicalLabelForDetailedKey(t.category_plaid_detailed)
    if (hierarchical) return hierarchical
    const parent = formatCategory(t.category_plaid)
    const sub = formatCategory(t.category_plaid_detailed)
    return parent === sub ? parent : `${parent} · ${sub}`
  }

  const raw = displayCategory(t)
  if (!raw) return 'Uncategorized'

  const fromLabel = hierarchicalLabelForCategoryLabel(raw)
  if (fromLabel) return fromLabel

  const trimmed = raw.trim()
  const fromDetailed = hierarchicalLabelForDetailedKey(trimmed)
  if (fromDetailed) return fromDetailed

  return formatCategory(raw)
}

export function formatCategory(raw: string | null | undefined): string {
  if (!raw || !raw.trim()) return 'Uncategorized'
  const trimmed = raw.trim()
  const normalizedKey = trimmed.toUpperCase().replace(/\./g, '_')

  if (NORMALIZED_OVERRIDES[trimmed]) return NORMALIZED_OVERRIDES[trimmed]
  if (NORMALIZED_OVERRIDES[normalizedKey]) return NORMALIZED_OVERRIDES[normalizedKey]
  if (DETAILED_LABEL_BY_KEY[normalizedKey]) return DETAILED_LABEL_BY_KEY[normalizedKey]
  if (PRIMARY_LABEL_BY_KEY[normalizedKey]) return PRIMARY_LABEL_BY_KEY[normalizedKey]

  const fromDetailed = hierarchicalLabelForDetailedKey(trimmed)
  if (fromDetailed) return fromDetailed

  const fromLabel = hierarchicalLabelForCategoryLabel(trimmed)
  if (fromLabel) return fromLabel

  // Fall back: take the most specific segment (after last dot),
  // replace underscores with spaces, title-case, swap "And" → "&"
  const segment = trimmed.includes('.')
    ? trimmed.split('.').pop()!
    : /^[A-Z0-9_]+$/.test(trimmed) && trimmed.includes('_')
      ? trimmed.replace(/^[A-Z]+(?:_[A-Z]+)?(?:_[A-Z]+)?_/, '')
      : trimmed
  const formatted = segment
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .replace(/\bAnd\b/g, '&')
    .trim()
  return formatted || 'Uncategorized'
}
