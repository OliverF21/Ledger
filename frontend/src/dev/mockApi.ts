/**
 * Dev-only fixture backend.
 *
 * Ledger normally needs a FastAPI server, a database and linked Plaid items
 * before any screen has something to draw. That's a lot of setup for someone
 * who just wants to look at the UI, so `VITE_MOCK_API=1 npm run dev` swaps
 * `fetch` for this table of canned responses and the whole app renders from
 * demo data with no backend running.
 *
 * Guarded twice — on `import.meta.env.DEV` and on the flag — so it cannot
 * reach a production bundle. Nothing else imports from this directory.
 */

const TODAY = new Date()

function isoDaysAgo(days: number): string {
  const d = new Date(TODAY)
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

function monthValue(offset: number): string {
  const d = new Date(TODAY.getFullYear(), TODAY.getMonth() - offset, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** Deterministic 0..1 noise so every reload draws the same demo curves. */
function noise(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

/** Smooth upward-drifting series — the shape the hero charts are designed for. */
function series(months: number, start: number, end: number): { date: string; total: number }[] {
  const points = months * 4
  return Array.from({ length: points }, (_, i) => {
    const t = i / (points - 1)
    const trend = start + (end - start) * t
    const wobble = (noise(i * 3.7) - 0.5) * (end - start) * 0.12
    const swell = Math.sin(t * Math.PI * 2.2) * (end - start) * 0.05
    return {
      date: isoDaysAgo(Math.round((points - 1 - i) * ((months * 30) / points))),
      total: Math.round((trend + wobble + swell) * 100) / 100,
    }
  })
}

const CATEGORIES = [
  { name: 'RENT_AND_UTILITIES', value: 1850, color: '#82a9f2' },
  { name: 'FOOD_AND_DRINK', value: 742.18, color: '#63cfcc' },
  { name: 'GENERAL_MERCHANDISE', value: 562.4, color: '#e6bd79' },
  { name: 'ENTERTAINMENT', value: 512.6, color: '#f4907f' },
  { name: 'TRANSPORTATION', value: 388.45, color: '#a196fa' },
  { name: 'MEDICAL', value: 299.1, color: '#adb8cb' },
  { name: 'PERSONAL_CARE', value: 268.3, color: '#74d8a8' },
  { name: 'LOAN_PAYMENTS', value: 189.97, color: '#95c8ff' },
]

const TOTAL_SPEND = CATEGORIES.reduce((sum, c) => sum + c.value, 0)

const TRANSACTIONS = [
  { merchant: 'Whole Foods Market', account_name: 'Chase Sapphire', amount: 86.42, category_plaid: 'FOOD_AND_DRINK', day: 0 },
  { merchant: 'Spotify', account_name: 'Amex Platinum', amount: 11.99, category_plaid: 'ENTERTAINMENT', day: 2 },
  { merchant: 'Uber', account_name: 'Chase Sapphire', amount: 24.8, category_plaid: 'TRANSPORTATION', day: 2 },
  { merchant: 'Payroll — Northwind Labs', account_name: 'Schwab Checking', amount: -3620, category_plaid: 'INCOME', day: 3 },
  { merchant: 'Blue Bottle Coffee', account_name: 'Amex Platinum', amount: 7.25, category_plaid: 'FOOD_AND_DRINK', day: 3 },
  { merchant: 'Con Edison', account_name: 'Schwab Checking', amount: 142.06, category_plaid: 'RENT_AND_UTILITIES', day: 4 },
  { merchant: 'Apple', account_name: 'Amex Platinum', amount: 249, category_plaid: 'GENERAL_MERCHANDISE', day: 5 },
  { merchant: 'CVS Pharmacy', account_name: 'Chase Sapphire', amount: 38.4, category_plaid: 'MEDICAL', day: 6 },
  { merchant: 'Trader Joe’s', account_name: 'Chase Sapphire', amount: 94.12, category_plaid: 'FOOD_AND_DRINK', day: 7 },
  { merchant: 'Equinox', account_name: 'Amex Platinum', amount: 215, category_plaid: 'PERSONAL_CARE', day: 8 },
  { merchant: 'Delta Air Lines', account_name: 'Chase Sapphire', amount: 412.6, category_plaid: 'TRAVEL', day: 11 },
  { merchant: 'Rent — 214 Bergen', account_name: 'Schwab Checking', amount: 1850, category_plaid: 'RENT_AND_UTILITIES', day: 14 },
].map((t, i) => ({
  id: i + 1,
  ...t,
  date: isoDaysAgo(t.day),
  merchant_logo_url: null,
  category_user: null,
  category_plaid_detailed: null,
}))

const ACCOUNTS = [
  { id: 1, item_id: 1, institution_name: 'Schwab', name: 'Schwab Brokerage', type: 'investment', subtype: 'brokerage', current_balance: 186402.1 },
  { id: 2, item_id: 2, institution_name: 'Ally', name: 'Ally Savings', type: 'depository', subtype: 'savings', current_balance: 42300 },
  { id: 3, item_id: 1, institution_name: 'Schwab', name: 'Schwab Checking', type: 'depository', subtype: 'checking', current_balance: 12480.22 },
  { id: 4, item_id: 3, institution_name: 'Coinbase', name: 'Coinbase', type: 'investment', subtype: 'crypto', current_balance: 9148.55 },
  { id: 5, item_id: 4, institution_name: 'Chase', name: 'Chase Sapphire', type: 'credit', subtype: 'credit card', current_balance: 1038.45 },
  { id: 6, item_id: 5, institution_name: 'Amex', name: 'Amex Platinum', type: 'credit', subtype: 'credit card', current_balance: 382 },
].map(a => ({ ...a, institution_logo: null, institution_color: null }))

const HOLDINGS = [
  {
    id: 1,
    name: 'Schwab Brokerage',
    institution_name: 'Schwab',
    subtype: 'brokerage',
    total_value: 186402.1,
    positions: [
      { ticker: 'VTI', name: 'Vanguard Total Stock Market ETF', type: 'etf', quantity: 340.2, price: 268.4, value: 91309.68, cost_basis: 78240, gain: 13069.68, gain_pct: 16.7, currency: 'USD' },
      { ticker: 'VOO', name: 'Vanguard S&P 500 ETF', type: 'etf', quantity: 82.5, price: 512.18, value: 42254.85, cost_basis: 38900, gain: 3354.85, gain_pct: 8.6, currency: 'USD' },
      { ticker: 'AAPL', name: 'Apple Inc.', type: 'equity', quantity: 120, price: 232.9, value: 27948, cost_basis: 21600, gain: 6348, gain_pct: 29.4, currency: 'USD' },
      { ticker: 'NVDA', name: 'NVIDIA Corporation', type: 'equity', quantity: 42, price: 128.6, value: 5401.2, cost_basis: 6820, gain: -1418.8, gain_pct: -20.8, currency: 'USD' },
      { ticker: 'BND', name: 'Vanguard Total Bond Market ETF', type: 'etf', quantity: 258, price: 73.6, value: 18988.8, cost_basis: 19740, gain: -751.2, gain_pct: -3.8, currency: 'USD' },
      { ticker: 'SCHD', name: 'Schwab US Dividend Equity ETF', type: 'etf', quantity: 62, price: 8.05, value: 499.57, cost_basis: 470, gain: 29.57, gain_pct: 6.3, currency: 'USD' },
    ],
  },
  {
    id: 4,
    name: 'Coinbase',
    institution_name: 'Coinbase',
    subtype: 'crypto',
    total_value: 9148.55,
    positions: [
      { ticker: 'BTC', name: 'Bitcoin', type: 'cryptocurrency', quantity: 0.082, price: 88420, value: 7250.44, cost_basis: 5100, gain: 2150.44, gain_pct: 42.2, currency: 'USD' },
      { ticker: 'ETH', name: 'Ethereum', type: 'cryptocurrency', quantity: 0.62, price: 3061.47, value: 1898.11, cost_basis: 2240, gain: -341.89, gain_pct: -15.3, currency: 'USD' },
    ],
  },
]

const PORTFOLIO_TOTAL = HOLDINGS.reduce((sum, a) => sum + a.total_value, 0)

const INVESTMENT_ACTIVITY = [
  { name: 'Buy VTI', ticker: 'VTI', type: 'buy', subtype: 'buy', amount: 4200, quantity: 15.8, price: 265.82, day: 6 },
  { name: 'Dividend VOO', ticker: 'VOO', type: 'dividend', subtype: 'dividend', amount: -318.4, quantity: null, price: null, day: 12 },
  { name: 'Sell NVDA', ticker: 'NVDA', type: 'sell', subtype: 'sell', amount: -2810, quantity: 20, price: 140.5, day: 24 },
  { name: 'Buy BND', ticker: 'BND', type: 'buy', subtype: 'buy', amount: 3000, quantity: 40.9, price: 73.34, day: 41 },
  { name: 'Dividend SCHD', ticker: 'SCHD', type: 'dividend', subtype: 'dividend', amount: -62.8, quantity: null, price: null, day: 58 },
  { name: 'Buy AAPL', ticker: 'AAPL', type: 'buy', subtype: 'buy', amount: 5400, quantity: 25, price: 216, day: 74 },
  { name: 'Buy BTC', ticker: 'BTC', type: 'buy', subtype: 'buy', amount: 2500, quantity: 0.031, price: 80645, day: 96 },
].map((t, i) => ({ id: i + 1, account_name: 'Schwab Brokerage', ...t, date: isoDaysAgo(t.day) }))

const BUDGETS = [
  { id: 1, category: 'FOOD_AND_DRINK', limit: 800, spent: 742.18, color: '#63cfcc' },
  { id: 2, category: 'ENTERTAINMENT', limit: 450, spent: 512.6, color: '#f4907f' },
  { id: 3, category: 'GENERAL_MERCHANDISE', limit: 600, spent: 562.4, color: '#e6bd79' },
  { id: 4, category: 'TRANSPORTATION', limit: 450, spent: 388.45, color: '#a196fa' },
  { id: 5, category: 'RENT_AND_UTILITIES', limit: 2100, spent: 1850, color: '#82a9f2' },
  { id: 6, category: 'PERSONAL_CARE', limit: 300, spent: 268.3, color: '#74d8a8' },
]

const TOTAL_ASSETS = 250330.87
const TOTAL_LIABILITIES = 1420.45
const NET_WORTH = TOTAL_ASSETS - TOTAL_LIABILITIES

const SP500_SECTORS: Record<string, number> = {
  Technology: 32, 'Financial Services': 14, Healthcare: 10, 'Consumer Cyclical': 10,
  'Communication Services': 9, Industrials: 8, 'Consumer Defensive': 6, Energy: 4,
}

/** Weights the optimizer demo uses for both the current and suggested books. */
const OPTIMIZER_TICKERS = [
  { ticker: 'VTI', current_weight_pct: 46.7, suggested_weight_pct: 38.2, current_dollar: 91309.68, suggested_dollar: 74680.35 },
  { ticker: 'VOO', current_weight_pct: 21.6, suggested_weight_pct: 26.4, current_dollar: 42254.85, suggested_dollar: 51625.37 },
  { ticker: 'AAPL', current_weight_pct: 14.3, suggested_weight_pct: 11.8, current_dollar: 27948, suggested_dollar: 23074.98 },
  { ticker: 'NVDA', current_weight_pct: 2.8, suggested_weight_pct: 6.9, current_dollar: 5401.2, suggested_dollar: 13493 },
  { ticker: 'BND', current_weight_pct: 9.7, suggested_weight_pct: 14.4, current_dollar: 18988.8, suggested_dollar: 28159.29 },
  { ticker: 'SCHD', current_weight_pct: 0.3, suggested_weight_pct: 2.3, current_dollar: 499.57, suggested_dollar: 4497.67 },
]

/**
 * Frontier + reference cloud for the optimizer panel. Shapes a plausible
 * concave frontier and a Dirichlet-ish cloud beneath it so the panel can be
 * reviewed without scipy — the real numbers come from
 * backend/app/services/optimization_service.py.
 *
 * The returned object matches OptimizationResponse (see Investments.tsx /
 * useInvestmentsOptimization), not the older internal field names.
 */
function optimizerSuggestion() {
  const frontier_points = Array.from({ length: 40 }, (_, i) => {
    const t = i / 39
    const vol = 6 + t * 16
    return { volatility_pct: Math.round(vol * 100) / 100, return_pct: Math.round((5 + 17 * Math.sqrt(t) + t * 2) * 100) / 100 }
  })
  const random_portfolios = Array.from({ length: 80 }, (_, i) => {
    const t = noise(i * 1.7)
    const vol = 5 + t * 20
    const ceiling = 5 + 17 * Math.sqrt((vol - 6) / 16 > 0 ? (vol - 6) / 16 : 0) + 2
    const ret = ceiling - noise(i * 3.1) * 12
    return {
      volatility_pct: Math.round(vol * 100) / 100,
      return_pct: Math.round(ret * 100) / 100,
      sharpe: Math.round((ret / Math.max(vol, 0.01)) * 100) / 100,
    }
  })
  const maxSharpeTickers = OPTIMIZER_TICKERS
  const maxUtilityTickers = OPTIMIZER_TICKERS.map(t => ({
    ...t,
    suggested_weight_pct: Math.round((t.suggested_weight_pct * 0.92 + 1.4) * 10) / 10,
    suggested_dollar: Math.round(t.suggested_dollar * 1.08 * 100) / 100,
  }))
  return {
    tickers: OPTIMIZER_TICKERS,
    current_expected_return_pct: 12.4,
    current_volatility_pct: 14.24,
    current_sharpe: 0.94,
    suggested_expected_return_pct: 15.1,
    suggested_volatility_pct: 12.86,
    suggested_sharpe: 1.21,
    data_points: 248,
    insufficient_data: false,
    advanced_enabled: false,
    position_cap_pct: 10,
    cap_relaxed: null,
    objectives: [
      { name: 'max_sharpe', tickers: maxSharpeTickers, expected_return_pct: 15.1, volatility_pct: 12.86, sharpe: 1.21 },
      { name: 'max_quadratic_utility', tickers: maxUtilityTickers, expected_return_pct: 18.2, volatility_pct: 17.4, sharpe: 1.08 },
    ],
    frontier_points,
    random_portfolios,
    sector_breakdown: [
      { sector: 'Technology', weight_pct: 17.1, floor_pct: 0, cap_pct: 100 },
      { sector: 'Financial Services', weight_pct: 9.4, floor_pct: 0, cap_pct: 100 },
      { sector: 'Healthcare', weight_pct: 6.2, floor_pct: 0, cap_pct: 100 },
      { sector: 'Unclassified', weight_pct: 67.3, floor_pct: 0, cap_pct: 100 },
    ],
    clip_log: [],
  }
}

const GOALS = [
  {
    id: 1,
    name: 'Emergency fund',
    kind: 'emergency_fund',
    kind_label: 'Emergency fund',
    target_amount: 18000,
    opening_amount: 8000,
    labeled_in: 2400,
    labeled_out: 0,
    progress: 10400,
    remaining: 7600,
    monthly_contribution: 800,
    annual_return: 0.04,
    target_date: null,
    status: 'active',
    color: '#82a9f2',
    months_remaining: 10,
    months_exact: 9.5,
    projected_end_month: 'Jun 2027',
    percent_funded: 57.8,
  },
  {
    id: 2,
    name: 'Japan trip',
    kind: 'sinking_fund',
    kind_label: 'Sinking fund',
    target_amount: 4500,
    opening_amount: 500,
    labeled_in: 1200,
    labeled_out: 0,
    progress: 1700,
    remaining: 2800,
    monthly_contribution: 350,
    annual_return: 0,
    target_date: '2027-03-01',
    status: 'active',
    color: '#63cfcc',
    months_remaining: 8,
    months_exact: 8,
    projected_end_month: 'Apr 2027',
    percent_funded: 37.8,
  },
]

/** path (without query) → JSON body. Matched longest-prefix-first. */
function routes(url: URL): unknown | undefined {
  const path = url.pathname
  const months = Number(url.searchParams.get('months') ?? 6)

  switch (path) {
    case '/api/auth/me':
      return { name: 'Oliver', email: 'demo@ledger.local' }

    case '/api/settings/plaid-config':
      return { client_id: 'demo', env: 'sandbox', redirect_uri: null, has_secret: true, configured: true, wizard_done: true }

    case '/api/setup/status':
      return { done: true }

    case '/api/plaid/accounts':
      return { accounts: ACCOUNTS }

    case '/api/plaid/sync/status':
      return { syncing: false, last_synced_at: isoDaysAgo(0), item_count: 3 }

    case '/api/plaid/sync':
      return {
        success: true,
        message: 'Synced 3 new transactions',
        transactions_synced: 3,
        enrichment_backfilled: 0,
        failed_count: 0,
        items: [
          { item_id: 1, institution_name: 'Chase', status: 'ok', synced: 2 },
          { item_id: 2, institution_name: 'Fidelity', status: 'ok', synced: 1 },
        ],
      }

    case '/api/analytics/summary':
      return {
        month: url.searchParams.get('month') ?? monthValue(0),
        total_spending: TOTAL_SPEND,
        total_income: 7240,
        savings_rate: Math.round(((7240 - TOTAL_SPEND) / 7240) * 100),
        spending_by_category: CATEGORIES,
        recent_transactions: [],
        prev_month_spending: TOTAL_SPEND * 0.9,
      }

    case '/api/analytics/net-worth':
      return {
        current_net_worth: NET_WORTH,
        total_assets: TOTAL_ASSETS,
        total_liabilities: TOTAL_LIABILITIES,
        accounts: ACCOUNTS.map(a => ({
          id: a.id,
          name: a.name,
          type: a.type,
          subtype: a.subtype,
          balance: a.current_balance,
          is_liability: a.type === 'credit',
        })),
        snapshots: series(months, NET_WORTH * 0.83, NET_WORTH),
        change_amount: NET_WORTH * 0.17,
        change_pct: 17.2,
      }

    case '/api/analytics/cash-flow':
      return {
        month: url.searchParams.get('month') ?? monthValue(0),
        total_income: 7240,
        total_spending: TOTAL_SPEND,
        savings: 7240 - TOTAL_SPEND,
        income_sources: [
          { id: 'payroll', label: 'Payroll', amount: 6480, color: '#74d8a8', top_transactions: [{ merchant: 'Northwind Labs', amount: -3620, date: isoDaysAgo(3) }] },
          { id: 'dividends', label: 'Dividends', amount: 520, color: '#63cfcc', top_transactions: [] },
          { id: 'refunds', label: 'Refunds', amount: 240, color: '#95c8ff', top_transactions: [] },
        ],
        spending_categories: CATEGORIES.map(c => ({
          id: c.name,
          label: c.name,
          amount: c.value,
          color: c.color,
          top_transactions: TRANSACTIONS.filter(t => t.category_plaid === c.name).slice(0, 3),
        })),
      }

    case '/api/analytics/trends': {
      const range = Number(url.searchParams.get('months') ?? 6)
      const monthRows = Array.from({ length: range }, (_, i) => {
        const offset = range - 1 - i
        const at = new Date(TODAY.getFullYear(), TODAY.getMonth() - offset, 1)
        const spending = Math.round(TOTAL_SPEND * (0.82 + noise(offset * 5) * 0.36) * 100) / 100
        return {
          month_key: monthValue(offset),
          label: at.toLocaleDateString('en-US', { month: 'short' }),
          full_label: at.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }),
          total_spending: spending,
          total_income: 7240,
          net: Math.round((7240 - spending) * 100) / 100,
          is_partial: offset === 0,
        }
      })
      const categories = CATEGORIES.map(c => {
        const monthly = monthRows.map((_, i) => Math.round(c.value * (0.72 + noise(i * 11 + c.value) * 0.56) * 100) / 100)
        const total = monthly.reduce((sum, v) => sum + v, 0)
        const lastFull = monthly[monthly.length - 2] ?? monthly[0]
        const priorAvg = monthly.slice(0, -2).reduce((sum, v) => sum + v, 0) / Math.max(1, monthly.length - 2)
        return {
          name: c.name,
          color: c.color,
          monthly,
          total: Math.round(total * 100) / 100,
          monthly_avg: Math.round((total / monthly.length) * 100) / 100,
          share_pct: Math.round((c.value / TOTAL_SPEND) * 1000) / 10,
          last_full: lastFull,
          prior_avg: Math.round(priorAvg * 100) / 100,
          change_vs_prior_pct: Math.round(((lastFull - priorAvg) / priorAvg) * 1000) / 10,
        }
      })
      const periodSpending = monthRows.reduce((sum, m) => sum + m.total_spending, 0)
      return {
        months: monthRows,
        categories,
        period_spending: Math.round(periodSpending * 100) / 100,
        period_income: 7240 * monthRows.length,
        monthly_avg_spending: Math.round((periodSpending / monthRows.length) * 100) / 100,
        prev_monthly_avg_spending: Math.round((periodSpending / monthRows.length) * 0.94 * 100) / 100,
        spending_change_pct: 6.4,
      }
    }

    case '/api/transactions': {
      const limit = Number(url.searchParams.get('limit') ?? 50)
      return { transactions: TRANSACTIONS.slice(0, limit), total: TRANSACTIONS.length, has_more: false }
    }

    case '/api/budgets':
      return {
        month: url.searchParams.get('month') ?? monthValue(0),
        budgets: BUDGETS,
        total_limit: BUDGETS.reduce((s, b) => s + b.limit, 0),
        total_spent: BUDGETS.reduce((s, b) => s + b.spent, 0),
      }

    case '/api/goals':
      return { goals: GOALS }

    case '/api/subscriptions':
      return {
        subscriptions: [
          { merchant: 'Spotify', category: 'ENTERTAINMENT', cadence: 'monthly', average_amount: 11.99, last_date: isoDaysAgo(2), next_expected_date: isoDaysAgo(-28), occurrence_count: 14 },
          { merchant: 'Equinox', category: 'PERSONAL_CARE', cadence: 'monthly', average_amount: 215, last_date: isoDaysAgo(8), next_expected_date: isoDaysAgo(-22), occurrence_count: 9 },
          { merchant: 'iCloud+', category: 'GENERAL_SERVICES', cadence: 'monthly', average_amount: 9.99, last_date: isoDaysAgo(16), next_expected_date: isoDaysAgo(-14), occurrence_count: 22 },
          { merchant: 'The New York Times', category: 'ENTERTAINMENT', cadence: 'monthly', average_amount: 17, last_date: isoDaysAgo(20), next_expected_date: isoDaysAgo(-10), occurrence_count: 11 },
        ],
      }

    case '/api/settings/alerts/active':
      return {
        budget_exceeded: [{ category: 'ENTERTAINMENT', spent: 512.6, limit: 450 }],
        large_transactions: [{ id: 11, merchant: 'Delta Air Lines', amount: 412.6, date: isoDaysAgo(11) }],
      }

    case '/api/proposals':
      return {
        proposals: [
          {
            id: 1, kind: 'budget_limit', status: 'pending', source: 'claude',
            rationale: 'Entertainment has run over its limit three months running; the trailing median is $505.',
            payload: {}, undo: null, superseded_by: null,
            created_at: new Date().toISOString(), applied_at: null,
            summary: 'Raise the Entertainment budget to $520',
            category_name: 'ENTERTAINMENT', basis_limit: 450, proposed_limit: 520, month: monthValue(0),
          },
          {
            id: 2, kind: 'budget_limit', status: 'pending', source: 'claude',
            rationale: 'Transport has come in under budget for five months; $380 still leaves headroom.',
            payload: {}, undo: null, superseded_by: null,
            created_at: new Date().toISOString(), applied_at: null,
            summary: 'Lower the Transport budget to $380',
            category_name: 'TRANSPORTATION', basis_limit: 450, proposed_limit: 380, month: monthValue(0),
          },
        ],
        pending_count: 2,
      }

    case '/api/investments/summary':
      return {
        total_value: PORTFOLIO_TOTAL,
        total_cost_basis: 173110,
        unrealized_gain: PORTFOLIO_TOTAL - 173110,
        allocation: [
          { type: 'etf', value: 153052.9, pct: 78.2, color: '#82a9f2' },
          { type: 'equity', value: 33349.2, pct: 17, color: '#63cfcc' },
          { type: 'cryptocurrency', value: 9148.55, pct: 4.7, color: '#e6bd79' },
        ],
        account_count: HOLDINGS.length,
        position_count: HOLDINGS.reduce((s, a) => s + a.positions.length, 0),
        last_synced_at: new Date().toISOString(),
      }

    case '/api/investments/holdings':
      return { accounts: HOLDINGS }

    case '/api/investments/history':
      return {
        snapshots: series(months, PORTFOLIO_TOTAL * 0.92, PORTFOLIO_TOTAL),
        change_amount: PORTFOLIO_TOTAL * 0.08,
        change_pct: 8.2,
      }

    case '/api/investments/transactions':
      return { transactions: INVESTMENT_ACTIVITY }

    case '/api/investments/risk/metrics':
      return {
        lookback_days: 365,
        as_of: isoDaysAgo(0),
        volatility_pct: 14.24,
        sharpe_ratio: 1.18,
        max_drawdown_pct: -9.41,
        drawdown_duration_days: 38,
        beta_vs_spy: 0.92,
        cagr_pct: 11.62,
        twr_pct: 15.8,
        mwr_pct: 13.2,
        risk_free_rate_pct: 4.42,
        data_points: 248,
        var_horizons: [
          { days: 1, var_95_pct: -1.42, var_95_dollar: -2779.4, var_99_pct: -2.31, var_99_dollar: -4520.3 },
          { days: 5, var_95_pct: -3.18, var_95_dollar: -6221.8, var_99_pct: -5.16, var_99_dollar: -10096.7 },
          { days: 20, var_95_pct: -6.35, var_95_dollar: -12424.6, var_99_pct: -10.32, var_99_dollar: -20193.4 },
        ],
        var_data_points: 340,
        var_excluded_tickers: [],
        var_coverage_pct: 100,
        portfolio_value_used: PORTFOLIO_TOTAL,
      }

    case '/api/investments/risk/optimize':
      return optimizerSuggestion()

    case '/api/investments/optimization-settings':
      return { advanced_enabled: false, position_cap_pct: 10, concentration_strength: 0.5 }

    case '/api/investments/sector-constraints':
      return []

    case '/api/investments/ticker-constraints':
      return []

    case '/api/investments/risk/sector-reference':
      return { weights: SP500_SECTORS }

    case '/api/crypto/wallets':
      return { wallets: [] }

    case '/api/crypto/alchemy-config':
      return { configured: false }

    case '/api/settings/alerts':
      return { budget_threshold_pct: 90, large_transaction_amount: 400, enabled: true }

    case '/api/categorization-rules':
      return { rules: [] }

    case '/api/settings/sync-config':
      return { auto_sync: true, sync_hour: 6 }

    case '/api/settings/advisor-config':
      return {
        configured: true,
        service_key: 'ledger_demo_key_8f3a',
        config_snippet: '{ "mcpServers": { "ledger": { "command": "uv", "args": ["run", "mcp"] } } }',
        enabled: true,
        prompt: '',
        model: 'claude-sonnet-4-5',
      }

    case '/api/settings/weekly-email':
      return { enabled: false, day: 'monday', email: null }

    case '/api/settings/security/email':
      return { email: 'demo@ledger.local', verified: true }

    case '/api/settings/security/recovery-code':
      return { has_code: true, generated_at: isoDaysAgo(120) }

    case '/api/settings/import':
      return { imported: 0 }

    default:
      return undefined
  }
}

export function installMockApi(): void {
  const realFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (!raw.includes('/api/')) return realFetch(input as RequestInfo, init)

    const url = new URL(raw, window.location.origin)
    const body = routes(url)

    if (body === undefined) {
      // Unmapped write endpoints (POST/PUT/DELETE) resolve as a no-op success
      // so demo clicks don't throw; unmapped reads 404 loudly enough to notice.
      const method = (init?.method ?? 'GET').toUpperCase()
      if (method !== 'GET') return jsonResponse({ success: true }, 200)
      console.warn(`[mock-api] no fixture for ${url.pathname}`)
      return jsonResponse({ detail: 'Not mocked' }, 404)
    }

    // A touch of latency so loading states are visible while designing.
    // Sync is slower so the header button and completion toast can be seen.
    const method = (init?.method ?? 'GET').toUpperCase()
    const delay = url.pathname === '/api/plaid/sync' && method === 'POST' ? 700 : 90
    await new Promise(resolve => setTimeout(resolve, delay))
    return jsonResponse(body, 200)
  }

  console.info('[mock-api] serving demo fixtures — no backend required')
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
