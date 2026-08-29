// Plaid's official Personal Finance Category (PFC) v2 taxonomy — 16 primary
// categories, 104 detailed categories. Source: Plaid's published taxonomy CSV
// (https://plaid.com/documents/transactions-personal-finance-category-taxonomy.csv).
// Used to suggest clean, human-readable category names — e.g. "Coffee" or
// "Internet & Cable" — instead of a raw PFC key like "FOOD_AND_DRINK_COFFEE"
// or "RENT_AND_UTILITIES_INTERNET_AND_CABLE" ending up stored as-is.

export interface PlaidCategory {
  primary: string
  primaryLabel: string
  detailed: string
  label: string
}

export const PLAID_CATEGORIES: PlaidCategory[] = [
  // Income
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_DIVIDENDS', label: 'Dividends' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_INTEREST_EARNED', label: 'Interest Earned' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_RETIREMENT_PENSION', label: 'Retirement / Pension' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_TAX_REFUND', label: 'Tax Refund' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_UNEMPLOYMENT', label: 'Unemployment' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_WAGES', label: 'Wages' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_SALARY', label: 'Salary' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_CONTRACTOR', label: 'Contract / Gig Income' },
  { primary: 'INCOME', primaryLabel: 'Income', detailed: 'INCOME_OTHER_INCOME', label: 'Other Income' },

  // Transfers in
  { primary: 'TRANSFER_IN', primaryLabel: 'Transfers In', detailed: 'TRANSFER_IN_CASH_ADVANCES_AND_LOANS', label: 'Cash Advances & Loans' },
  { primary: 'TRANSFER_IN', primaryLabel: 'Transfers In', detailed: 'TRANSFER_IN_DEPOSIT', label: 'Deposit' },
  { primary: 'TRANSFER_IN', primaryLabel: 'Transfers In', detailed: 'TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS', label: 'Investment / Retirement Transfer In' },
  { primary: 'TRANSFER_IN', primaryLabel: 'Transfers In', detailed: 'TRANSFER_IN_SAVINGS', label: 'Savings Transfer In' },
  { primary: 'TRANSFER_IN', primaryLabel: 'Transfers In', detailed: 'TRANSFER_IN_ACCOUNT_TRANSFER', label: 'Account Transfer In' },
  { primary: 'TRANSFER_IN', primaryLabel: 'Transfers In', detailed: 'TRANSFER_IN_OTHER_TRANSFER_IN', label: 'Other Transfer In' },

  // Transfers out
  { primary: 'TRANSFER_OUT', primaryLabel: 'Transfers Out', detailed: 'TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS', label: 'Investment / Retirement Transfer Out' },
  { primary: 'TRANSFER_OUT', primaryLabel: 'Transfers Out', detailed: 'TRANSFER_OUT_SAVINGS', label: 'Savings Transfer Out' },
  { primary: 'TRANSFER_OUT', primaryLabel: 'Transfers Out', detailed: 'TRANSFER_OUT_WITHDRAWAL', label: 'Withdrawal' },
  { primary: 'TRANSFER_OUT', primaryLabel: 'Transfers Out', detailed: 'TRANSFER_OUT_ACCOUNT_TRANSFER', label: 'Account Transfer Out' },
  { primary: 'TRANSFER_OUT', primaryLabel: 'Transfers Out', detailed: 'TRANSFER_OUT_TRANSFER_OUT_FROM_APPS', label: 'App Transfer Out' },
  { primary: 'TRANSFER_OUT', primaryLabel: 'Transfers Out', detailed: 'TRANSFER_OUT_OTHER_TRANSFER_OUT', label: 'Other Transfer Out' },

  // Loan payments
  { primary: 'LOAN_PAYMENTS', primaryLabel: 'Loan Payments', detailed: 'LOAN_PAYMENTS_CAR_PAYMENT', label: 'Car Payment' },
  { primary: 'LOAN_PAYMENTS', primaryLabel: 'Loan Payments', detailed: 'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT', label: 'Credit Card Payment' },
  { primary: 'LOAN_PAYMENTS', primaryLabel: 'Loan Payments', detailed: 'LOAN_PAYMENTS_PERSONAL_LOAN_PAYMENT', label: 'Personal Loan Payment' },
  { primary: 'LOAN_PAYMENTS', primaryLabel: 'Loan Payments', detailed: 'LOAN_PAYMENTS_MORTGAGE_PAYMENT', label: 'Mortgage' },
  { primary: 'LOAN_PAYMENTS', primaryLabel: 'Loan Payments', detailed: 'LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT', label: 'Student Loan Payment' },
  { primary: 'LOAN_PAYMENTS', primaryLabel: 'Loan Payments', detailed: 'LOAN_PAYMENTS_OTHER_PAYMENT', label: 'Other Loan Payment' },

  // Bank fees
  { primary: 'BANK_FEES', primaryLabel: 'Bank Fees', detailed: 'BANK_FEES_ATM_FEES', label: 'ATM Fees' },
  { primary: 'BANK_FEES', primaryLabel: 'Bank Fees', detailed: 'BANK_FEES_FOREIGN_TRANSACTION_FEES', label: 'Foreign Transaction Fees' },
  { primary: 'BANK_FEES', primaryLabel: 'Bank Fees', detailed: 'BANK_FEES_INSUFFICIENT_FUNDS', label: 'Insufficient Funds Fee' },
  { primary: 'BANK_FEES', primaryLabel: 'Bank Fees', detailed: 'BANK_FEES_INTEREST_CHARGE', label: 'Interest Charge' },
  { primary: 'BANK_FEES', primaryLabel: 'Bank Fees', detailed: 'BANK_FEES_OVERDRAFT_FEES', label: 'Overdraft Fees' },
  { primary: 'BANK_FEES', primaryLabel: 'Bank Fees', detailed: 'BANK_FEES_OTHER_BANK_FEES', label: 'Other Bank Fees' },

  // Entertainment
  { primary: 'ENTERTAINMENT', primaryLabel: 'Entertainment', detailed: 'ENTERTAINMENT_CASINOS_AND_GAMBLING', label: 'Casinos & Gambling' },
  { primary: 'ENTERTAINMENT', primaryLabel: 'Entertainment', detailed: 'ENTERTAINMENT_MUSIC_AND_AUDIO', label: 'Music' },
  { primary: 'ENTERTAINMENT', primaryLabel: 'Entertainment', detailed: 'ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS', label: 'Events, Parks & Museums' },
  { primary: 'ENTERTAINMENT', primaryLabel: 'Entertainment', detailed: 'ENTERTAINMENT_TV_AND_MOVIES', label: 'TV & Movies' },
  { primary: 'ENTERTAINMENT', primaryLabel: 'Entertainment', detailed: 'ENTERTAINMENT_VIDEO_GAMES', label: 'Video Games' },
  { primary: 'ENTERTAINMENT', primaryLabel: 'Entertainment', detailed: 'ENTERTAINMENT_OTHER_ENTERTAINMENT', label: 'Other Entertainment' },

  // Food & drink
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR', label: 'Beer, Wine & Liquor' },
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_COFFEE', label: 'Coffee' },
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_FAST_FOOD', label: 'Fast Food' },
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_GROCERIES', label: 'Groceries' },
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_RESTAURANT', label: 'Restaurants' },
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_VENDING_MACHINES', label: 'Vending Machines' },
  { primary: 'FOOD_AND_DRINK', primaryLabel: 'Food & Drink', detailed: 'FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK', label: 'Other Food & Drink' },

  // General merchandise
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS', label: 'Books & Newsstands' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES', label: 'Clothing & Accessories' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_CONVENIENCE_STORES', label: 'Convenience Stores' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_DEPARTMENT_STORES', label: 'Department Stores' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_DISCOUNT_STORES', label: 'Discount Stores' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_ELECTRONICS', label: 'Electronics' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES', label: 'Gifts & Novelties' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_OFFICE_SUPPLIES', label: 'Office Supplies' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_ONLINE_MARKETPLACES', label: 'Online Marketplaces' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_PET_SUPPLIES', label: 'Pet Supplies' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_SPORTING_GOODS', label: 'Sporting Goods' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_SUPERSTORES', label: 'Superstores' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_TOBACCO_AND_VAPE', label: 'Tobacco & Vape' },
  { primary: 'GENERAL_MERCHANDISE', primaryLabel: 'Shopping', detailed: 'GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE', label: 'Other Merchandise' },

  // Home improvement
  { primary: 'HOME_IMPROVEMENT', primaryLabel: 'Home Improvement', detailed: 'HOME_IMPROVEMENT_FURNITURE', label: 'Furniture' },
  { primary: 'HOME_IMPROVEMENT', primaryLabel: 'Home Improvement', detailed: 'HOME_IMPROVEMENT_HARDWARE', label: 'Hardware' },
  { primary: 'HOME_IMPROVEMENT', primaryLabel: 'Home Improvement', detailed: 'HOME_IMPROVEMENT_REPAIR_AND_MAINTENANCE', label: 'Repair & Maintenance' },
  { primary: 'HOME_IMPROVEMENT', primaryLabel: 'Home Improvement', detailed: 'HOME_IMPROVEMENT_SECURITY', label: 'Home Security' },
  { primary: 'HOME_IMPROVEMENT', primaryLabel: 'Home Improvement', detailed: 'HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT', label: 'Other Home Improvement' },

  // Medical
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_DENTAL_CARE', label: 'Dental Care' },
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_EYE_CARE', label: 'Eye Care' },
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_NURSING_CARE', label: 'Nursing Care' },
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_PHARMACIES_AND_SUPPLEMENTS', label: 'Pharmacy' },
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_PRIMARY_CARE', label: 'Primary Care' },
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_VETERINARY_SERVICES', label: 'Veterinary' },
  { primary: 'MEDICAL', primaryLabel: 'Medical', detailed: 'MEDICAL_OTHER_MEDICAL', label: 'Other Medical' },

  // Personal care
  { primary: 'PERSONAL_CARE', primaryLabel: 'Personal Care', detailed: 'PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS', label: 'Gym & Fitness' },
  { primary: 'PERSONAL_CARE', primaryLabel: 'Personal Care', detailed: 'PERSONAL_CARE_HAIR_AND_BEAUTY', label: 'Hair & Beauty' },
  { primary: 'PERSONAL_CARE', primaryLabel: 'Personal Care', detailed: 'PERSONAL_CARE_LAUNDRY_AND_DRY_CLEANING', label: 'Laundry & Dry Cleaning' },
  { primary: 'PERSONAL_CARE', primaryLabel: 'Personal Care', detailed: 'PERSONAL_CARE_OTHER_PERSONAL_CARE', label: 'Other Personal Care' },

  // General services
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_ACCOUNTING_AND_FINANCIAL_PLANNING', label: 'Accounting & Financial Planning' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_AUTOMOTIVE', label: 'Auto Services' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_CHILDCARE', label: 'Childcare' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_CONSULTING_AND_LEGAL', label: 'Consulting & Legal' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_EDUCATION', label: 'Education' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_INSURANCE', label: 'Insurance' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_POSTAGE_AND_SHIPPING', label: 'Postage & Shipping' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_STORAGE', label: 'Storage' },
  { primary: 'GENERAL_SERVICES', primaryLabel: 'Services', detailed: 'GENERAL_SERVICES_OTHER_GENERAL_SERVICES', label: 'Other Services' },

  // Government & non-profit
  { primary: 'GOVERNMENT_AND_NON_PROFIT', primaryLabel: 'Government & Non-Profit', detailed: 'GOVERNMENT_AND_NON_PROFIT_DONATIONS', label: 'Donations' },
  { primary: 'GOVERNMENT_AND_NON_PROFIT', primaryLabel: 'Government & Non-Profit', detailed: 'GOVERNMENT_AND_NON_PROFIT_GOVERNMENT_DEPARTMENTS_AND_AGENCIES', label: 'Government Services' },
  { primary: 'GOVERNMENT_AND_NON_PROFIT', primaryLabel: 'Government & Non-Profit', detailed: 'GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT', label: 'Tax Payment' },
  { primary: 'GOVERNMENT_AND_NON_PROFIT', primaryLabel: 'Government & Non-Profit', detailed: 'GOVERNMENT_AND_NON_PROFIT_OTHER_GOVERNMENT_AND_NON_PROFIT', label: 'Other Government / Non-Profit' },

  // Catch-all primary (common on checking / P2P). "Other · Other" reads as a
  // blank chip next to Plaid's generic icon; call it Miscellaneous.
  { primary: 'OTHER', primaryLabel: 'Miscellaneous', detailed: 'OTHER_OTHER', label: 'Miscellaneous' },

  // Transportation
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_BIKES_AND_SCOOTERS', label: 'Bikes & Scooters' },
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_GAS', label: 'Gas' },
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_PARKING', label: 'Parking' },
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_PUBLIC_TRANSIT', label: 'Public Transit' },
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_TAXIS_AND_RIDE_SHARES', label: 'Rideshare & Taxis' },
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_TOLLS', label: 'Tolls' },
  { primary: 'TRANSPORTATION', primaryLabel: 'Transportation', detailed: 'TRANSPORTATION_OTHER_TRANSPORTATION', label: 'Other Transportation' },

  // Travel
  { primary: 'TRAVEL', primaryLabel: 'Travel', detailed: 'TRAVEL_FLIGHTS', label: 'Flights' },
  { primary: 'TRAVEL', primaryLabel: 'Travel', detailed: 'TRAVEL_LODGING', label: 'Lodging' },
  { primary: 'TRAVEL', primaryLabel: 'Travel', detailed: 'TRAVEL_RENTAL_CARS', label: 'Rental Cars' },
  { primary: 'TRAVEL', primaryLabel: 'Travel', detailed: 'TRAVEL_OTHER_TRAVEL', label: 'Other Travel' },

  // Rent & utilities
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_GAS_AND_ELECTRICITY', label: 'Gas & Electric' },
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_INTERNET_AND_CABLE', label: 'Internet & Cable' },
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_RENT', label: 'Rent' },
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_SEWAGE_AND_WASTE_MANAGEMENT', label: 'Sewage & Waste' },
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_TELEPHONE', label: 'Phone' },
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_WATER', label: 'Water' },
  { primary: 'RENT_AND_UTILITIES', primaryLabel: 'Rent & Utilities', detailed: 'RENT_AND_UTILITIES_OTHER_UTILITIES', label: 'Other Utilities' },
]

/** Flat, deduplicated, alphabetized list of friendly labels — for <datalist> suggestions. */
export const PLAID_CATEGORY_LABELS: string[] = Array.from(
  new Set(PLAID_CATEGORIES.map(c => c.label))
).sort((a, b) => a.localeCompare(b))

export interface CategoryGroup {
  primary: string
  label: string
  subcategories: { key: string; label: string }[]
}

function buildCategoryGroups(): CategoryGroup[] {
  const groups = new Map<string, CategoryGroup>()
  for (const c of PLAID_CATEGORIES) {
    let group = groups.get(c.primary)
    if (!group) {
      group = { primary: c.primary, label: c.primaryLabel, subcategories: [] }
      groups.set(c.primary, group)
    }
    group.subcategories.push({ key: c.detailed, label: c.label })
  }
  return Array.from(groups.values())
}

/** Plaid primaries with nested detailed subcategories — for hierarchical pickers. */
export const CATEGORY_GROUPS: CategoryGroup[] = buildCategoryGroups()

const _plaidLabelSet = new Set(
  PLAID_CATEGORIES.flatMap(c => [c.primaryLabel, c.label].map(s => s.toLowerCase())),
)

/** True when label matches a Plaid primary or detailed category name. */
export function isPlaidCategoryLabel(label: string): boolean {
  return _plaidLabelSet.has(label.trim().toLowerCase())
}

/** Find the primary group key for a stored category label, if any. */
export function primaryForCategoryLabel(label: string): string | null {
  const lower = label.trim().toLowerCase()
  for (const g of CATEGORY_GROUPS) {
    if (g.label.toLowerCase() === lower) return g.primary
    for (const sub of g.subcategories) {
      if (sub.label.toLowerCase() === lower) return g.primary
    }
  }
  return null
}

/** Common income labels stored outside Plaid's taxonomy (e.g. CSV import). */
const INCOME_SUB_LABEL_ALIASES: Record<string, string> = {
  salary: 'Salary',
  paycheck: 'Paycheck',
}

const PRIMARY_PREFIXES = Array.from(
  new Map(PLAID_CATEGORIES.map(c => [c.primary, c.primaryLabel])).entries(),
).sort(([a], [b]) => b.length - a.length)

function titleCaseSegment(segment: string): string {
  return segment
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .replace(/\bAnd\b/g, '&')
}

function joinHierarchy(parent: string, sub: string): string {
  return parent === sub ? parent : `${parent} · ${sub}`
}

/** Parent · sub label when `label` is a Plaid detailed category name. */
export function hierarchicalLabelForCategoryLabel(label: string): string | null {
  const lower = label.trim().toLowerCase()
  for (const g of CATEGORY_GROUPS) {
    for (const sub of g.subcategories) {
      if (sub.label.toLowerCase() === lower) {
        return joinHierarchy(g.label, sub.label)
      }
    }
  }
  const incomeSub = INCOME_SUB_LABEL_ALIASES[lower]
  if (incomeSub) return `Income · ${incomeSub}`
  return null
}

/** Parent · sub label when `detailed` is a Plaid PFC detailed key. */
export function hierarchicalLabelForDetailedKey(detailed: string): string | null {
  const normalized = detailed.trim().toUpperCase().replace(/\./g, '_')
  const entry = PLAID_CATEGORIES.find(c => c.detailed === normalized)
  if (entry) return joinHierarchy(entry.primaryLabel, entry.label)

  for (const [primary, primaryLabel] of PRIMARY_PREFIXES) {
    const prefix = `${primary}_`
    if (normalized.startsWith(prefix)) {
      const sub = titleCaseSegment(normalized.slice(prefix.length))
      return sub ? joinHierarchy(primaryLabel, sub) : primaryLabel
    }
  }
  return null
}
