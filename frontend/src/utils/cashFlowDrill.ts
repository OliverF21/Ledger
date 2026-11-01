// Cash-flow Sankey bands are not the same strings as the transaction list's
// exact category filter. A "Food & Drink" band includes Groceries, Restaurants,
// and a manual "Dining Out". This module mirrors the backend bucket rules
// (cash_flow_spending_bucket / income source category) so a double-click opens
// the same transactions the band represents.

import { formatCategory } from './categories'
import { PLAID_CATEGORIES } from './plaidCategories'

export type FlowDrill =
  | { kind: 'spend'; id: string }
  | { kind: 'activity'; id: string; parentId: string | null }
  | { kind: 'group'; id: string }
  | { kind: 'income'; id: string }

export interface TransactionQuery {
  month: string
  category: string
  drill: FlowDrill | null
  label: string
}

export interface CategoryFields {
  category_user?: string | null
  category_plaid?: string | null
  category_plaid_detailed?: string | null
  merchant?: string | null
  original_description?: string | null
}

const PLAID_PRIMARIES = new Set(PLAID_CATEGORIES.map(category => category.primary))
const KNOWN_KEYS = new Set([...PLAID_PRIMARIES, 'SHOPPING', 'EDUCATION', 'PETS'])

const DETAILED_ALIASES: Record<string, string> = {
  FOOD_AND_DRINK_RESTAURANTS: 'FOOD_AND_DRINK_RESTAURANT',
  FOOD_AND_DRINK_ALCOHOL_AND_BARS: 'FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR',
}

/** Human labels that predate the v2 taxonomy but still land in a real activity. */
const LEGACY_LABELS: Record<string, string> = {
  'dining out': 'FOOD_AND_DRINK_RESTAURANT',
  'bars & alcohol': 'FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR',
  rideshare: 'TRANSPORTATION_TAXIS_AND_RIDE_SHARES',
  interest: 'INCOME_INTEREST_EARNED',
  government: 'GOVERNMENT_AND_NON_PROFIT',
}

const INVESTMENT_TRANSFER_LABELS: Record<string, string> = {
  'investment / retirement transfer out': 'TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS',
}

const CASHBACK_RE = /(?<!\w)cash\s*back(?!\w)/i
const INTEREST_CHARGE_RE = /(?<!\w)(?:interest\s+charge|purchase\s+interest|finance\s+charge)(?!\w)/i
const INTEREST_RE = /(?<!\w)(?:interest(?:\s+(?:earned|payment|paid|credit|income|pymt))?|intrst(?:\s+pymnt)?)(?!\w)/i

const detailedByLabel = new Map<string, string>()
const primaryByLabel = new Map<string, string>()
for (const category of PLAID_CATEGORIES) {
  // Detailed wins when a primary and a subcategory share a name ("Miscellaneous").
  detailedByLabel.set(category.label.toLowerCase(), category.detailed)
  if (!primaryByLabel.has(category.primaryLabel.toLowerCase())) {
    primaryByLabel.set(category.primaryLabel.toLowerCase(), category.primary)
  }
}

const DRILL_PARAM_KEYS = ['txnMonth', 'flow', 'category', 'parent', 'label'] as const
const FLOW_KINDS = new Set<FlowDrill['kind']>(['spend', 'activity', 'group', 'income'])
const MONTH_RE = /^\d{4}-\d{2}$/

function isUpperToken(value: string): boolean {
  return value === value.toUpperCase() && value !== value.toLowerCase()
}

function aliasKey(key: string): string {
  return DETAILED_ALIASES[key] ?? key
}

export function normalizeCategoryKey(key: string): string {
  if (!key) return key
  const lower = key.toLowerCase()
  if (lower === 'shopping' || lower === 'general merchandise' || lower === 'general merch') {
    return 'GENERAL_MERCHANDISE'
  }
  const normalized = key.toUpperCase().replace(/\./g, '_')
  if (normalized === 'SHOPPING') return 'GENERAL_MERCHANDISE'
  if (normalized.startsWith('SHOPPING_')) {
    return `GENERAL_MERCHANDISE_${normalized.slice('SHOPPING_'.length)}`
  }
  if (PLAID_PRIMARIES.has(normalized) || KNOWN_KEYS.has(normalized)) return normalized
  if ([...PLAID_PRIMARIES].some(primary => normalized.startsWith(`${primary}_`))) return normalized
  return key
}

function labelToPfcKey(label: string): string | null {
  const lower = label.trim().toLowerCase()
  if (!lower) return null
  const legacy = LEGACY_LABELS[lower]
  if (legacy) return aliasKey(legacy)
  const detailed = detailedByLabel.get(lower)
  if (detailed) return aliasKey(detailed)
  const primary = primaryByLabel.get(lower)
  if (primary) return aliasKey(primary)
  return null
}

function resolveCategoryToPfcKey(category: string): string {
  if (!category) return category
  const stripped = category.trim()
  const mapped = labelToPfcKey(stripped)
  if (mapped) return mapped
  const investment = INVESTMENT_TRANSFER_LABELS[stripped.toLowerCase()]
  if (investment) return investment
  const primary = primaryByLabel.get(stripped.toLowerCase())
  if (primary) return primary
  return aliasKey(normalizeCategoryKey(stripped).toUpperCase().replace(/\./g, '_'))
}

function exclusionKey(raw: string): string {
  const investment = INVESTMENT_TRANSFER_LABELS[raw.trim().toLowerCase()]
  if (investment) return investment
  return aliasKey(normalizeCategoryKey(raw).toUpperCase().replace(/\./g, '_'))
}

function parentFromDetailed(detailed: string): string {
  const key = detailed.toUpperCase().replace(/\./g, '_')
  const primaries = [...PLAID_PRIMARIES].sort((a, b) => b.length - a.length)
  for (const primary of primaries) {
    if (key === primary || key.startsWith(`${primary}_`)) return primary
  }
  const parts = key.split('_')
  for (const size of [3, 2, 1]) {
    if (parts.length > size) return parts.slice(0, size).join('_')
  }
  return key
}

function canonicalKey(raw: string): string {
  return aliasKey(normalizeCategoryKey(raw).toUpperCase().replace(/\./g, '_'))
}

/** Short activity name, matching the backend expanded Sankey label. */
function shortActivityLabel(key: string): string {
  const normalized = key.toUpperCase().replace(/\./g, '_')
  const detailed = PLAID_CATEGORIES.find(category => category.detailed === normalized)
  if (detailed) return detailed.label
  const primary = PLAID_CATEGORIES.find(category => category.primary === normalized)
  if (primary) return primary.primaryLabel
  return formatCategory(key)
}

function rollupCategoryKey(txn: CategoryFields, fallback: string): string {
  const user = txn.category_user?.trim() || ''
  let raw: string
  if (user) raw = user
  else if (txn.category_plaid?.trim()) raw = txn.category_plaid.trim()
  else if (txn.category_plaid_detailed?.trim()) raw = parentFromDetailed(txn.category_plaid_detailed.trim())
  else return fallback

  raw = normalizeCategoryKey(raw)
  const resolved = resolveCategoryToPfcKey(raw)
  if (!resolved) return raw || fallback
  if (PLAID_PRIMARIES.has(resolved) || KNOWN_KEYS.has(resolved)) return normalizeCategoryKey(resolved)
  if (user && !isUpperToken(user)) return user
  return formatCategory(resolved)
}

export function displayRollupCategory(txn: CategoryFields, fallback = 'Uncategorized'): string {
  const user = txn.category_user?.trim() || ''
  const sources = user ? [user] : [txn.category_plaid_detailed, txn.category_plaid]
  for (const raw of sources) {
    if (raw && exclusionKey(raw) === 'TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS') return 'Investments'
  }

  const category = rollupCategoryKey(txn, fallback)
  if (!category || category === fallback) return fallback

  const resolved = resolveCategoryToPfcKey(category)
  if (resolved && (PLAID_PRIMARIES.has(resolved) || KNOWN_KEYS.has(resolved))) {
    return normalizeCategoryKey(resolved)
  }

  let mapped: string | null = null
  if (user && !isUpperToken(user)) mapped = labelToPfcKey(user)
  if (!mapped && category && !isUpperToken(category)) mapped = labelToPfcKey(category)

  const detailed = mapped
    ? canonicalKey(mapped)
    : resolved
      ? canonicalKey(resolved)
      : null
  if (detailed) {
    const parent = parentFromDetailed(detailed)
    if ((PLAID_PRIMARIES.has(parent) || KNOWN_KEYS.has(parent)) && (mapped || detailed !== parent)) {
      return normalizeCategoryKey(parent)
    }
  }
  return category
}

function pfcKeyForCashFlow(txn: CategoryFields): string | null {
  const user = txn.category_user?.trim() || ''
  if (user) {
    if (!isUpperToken(user)) {
      const mapped = labelToPfcKey(user)
      return mapped ? canonicalKey(mapped) : null
    }
    return canonicalKey(user)
  }
  if (txn.category_plaid_detailed?.trim()) return canonicalKey(txn.category_plaid_detailed)
  if (txn.category_plaid?.trim()) return canonicalKey(txn.category_plaid)
  return null
}

export function cashFlowSpendBucket(
  categoryUser: string | null | undefined,
  categoryPlaid: string | null | undefined,
  categoryPlaidDetailed: string | null | undefined,
  expanded = false,
): string {
  const txn = {
    category_user: categoryUser,
    category_plaid: categoryPlaid,
    category_plaid_detailed: categoryPlaidDetailed,
  }
  const rolled = displayRollupCategory(txn, 'Uncategorized')
  if (!expanded || rolled === 'Uncategorized' || rolled === 'Investments') return rolled
  const key = pfcKeyForCashFlow(txn)
  if (!key) return rolled
  const parent = parentFromDetailed(key)
  if (!PLAID_PRIMARIES.has(parent) && !KNOWN_KEYS.has(parent)) return rolled
  if (key === parent) return rolled
  return shortActivityLabel(key)
}

function looksLikeInterest(key: string, blob: string): boolean {
  if (key === 'INCOME_INTEREST_EARNED' || key === 'INTEREST') return true
  if (key.includes('INTEREST_CHARGE')) return false
  if (!blob.trim() || INTEREST_CHARGE_RE.test(blob)) return false
  return INTEREST_RE.test(blob)
}

export function incomeSourceCategory(txn: CategoryFields): string {
  const user = txn.category_user?.trim() || ''
  const specific = user || txn.category_plaid_detailed?.trim() || txn.category_plaid?.trim() || ''
  const key = specific ? exclusionKey(specific) : ''
  const blob = `${txn.merchant ?? ''} ${txn.original_description ?? ''}`
  if (!user && CASHBACK_RE.test(blob)) return 'Cash Back'
  if (key.startsWith('INCOME_') && key !== 'INCOME') return key
  if (looksLikeInterest(key, blob)) return 'INCOME_INTEREST_EARNED'
  return displayRollupCategory(txn, 'Other Income')
}

export function transactionMatchesFlow(txn: CategoryFields, drill: FlowDrill): boolean {
  if (drill.kind === 'income') return incomeSourceCategory(txn) === drill.id
  if (drill.kind === 'activity') {
    const bucketId = drill.id.startsWith('other:') ? drill.id.slice('other:'.length) : drill.id
    return cashFlowSpendBucket(txn.category_user, txn.category_plaid, txn.category_plaid_detailed, true) === bucketId
  }
  return cashFlowSpendBucket(txn.category_user, txn.category_plaid, txn.category_plaid_detailed, false) === drill.id
}

export function drillFromCashFlowNode(node: {
  id: string
  side: 'left' | 'right' | 'mid'
  parent_id?: string | null
}): FlowDrill {
  if (node.side === 'left') return { kind: 'income', id: node.id }
  if (node.side === 'mid') return { kind: 'group', id: node.id }
  if (node.parent_id || node.id.startsWith('other:')) {
    return { kind: 'activity', id: node.id, parentId: node.parent_id ?? null }
  }
  return { kind: 'spend', id: node.id }
}

export function flowDrillLabel(drill: FlowDrill, label: string): string {
  const trimmed = label.trim()
  if (trimmed) return trimmed
  if (drill.kind === 'activity' && drill.id.startsWith('other:')) {
    return `Other · ${formatCategory(drill.id.slice('other:'.length))}`
  }
  return formatCategory(drill.id)
}

export function readTransactionQuery(search: string): TransactionQuery {
  const params = new URLSearchParams(search)
  const monthRaw = params.get('txnMonth')
  const flow = params.get('flow')
  const category = params.get('category')
  const parent = params.get('parent')
  const label = params.get('label') ?? ''
  let drill: FlowDrill | null = null
  if (flow && category && FLOW_KINDS.has(flow as FlowDrill['kind'])) {
    const kind = flow as FlowDrill['kind']
    if (kind === 'activity') drill = { kind, id: category, parentId: parent }
    else if (kind === 'group') drill = { kind, id: category }
    else if (kind === 'income') drill = { kind, id: category }
    else drill = { kind: 'spend', id: category }
  }
  return {
    month: monthRaw && MONTH_RE.test(monthRaw) ? monthRaw : 'all',
    category: drill || !category || category === 'all' ? 'all' : category,
    drill,
    label,
  }
}

export function transactionSearchParams(query: TransactionQuery, base?: URLSearchParams): URLSearchParams {
  const params = new URLSearchParams(base?.toString() ?? '')
  for (const key of DRILL_PARAM_KEYS) params.delete(key)
  if (query.month !== 'all') params.set('txnMonth', query.month)
  if (query.drill) {
    params.set('flow', query.drill.kind)
    params.set('category', query.drill.id)
    if (query.label.trim()) params.set('label', query.label.trim())
    if (query.drill.kind === 'activity' && query.drill.parentId) params.set('parent', query.drill.parentId)
  } else if (query.category !== 'all') {
    params.set('category', query.category)
  }
  return params
}

function replaceQuery(params: URLSearchParams): void {
  const url = new URL(window.location.href)
  url.search = params.toString()
  const next = `${url.pathname}${url.search}${url.hash}`
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (next !== current) window.history.replaceState(null, '', next)
}

export function writeTransactionQuery(query: TransactionQuery): void {
  const params = transactionSearchParams(query, new URLSearchParams(window.location.search))
  replaceQuery(params)
}

export function clearTransactionDrillParams(): void {
  const current = new URLSearchParams(window.location.search)
  if (!DRILL_PARAM_KEYS.some(key => current.has(key))) return
  replaceQuery(transactionSearchParams({ month: 'all', category: 'all', drill: null, label: '' }, current))
}

/** Open Transactions for one Sankey band. Month and category stay editable there. */
export function openTransactionsForCategory(month: string, drill: FlowDrill, label: string): void {
  const params = transactionSearchParams(
    { month, category: 'all', drill, label },
    new URLSearchParams(window.location.search),
  )
  const search = params.toString()
  const prefix = search ? `?${search}` : ''
  const next = `${window.location.pathname}${prefix}#transactions`
  const onTransactions = window.location.hash.replace('#', '').split('/')[0] === 'transactions'
  if (onTransactions) {
    window.history.replaceState(null, '', next)
    window.dispatchEvent(new CustomEvent('ledger:transactions-drill'))
    return
  }
  window.history.replaceState(null, '', `${window.location.pathname}${prefix}${window.location.hash}`)
  window.location.hash = 'transactions'
}
