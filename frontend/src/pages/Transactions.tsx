import { Download, ChevronUp, ChevronDown, ChevronsUpDown, Eye, EyeOff, Scissors, X } from 'lucide-react'
import { useState, useEffect, useMemo, Fragment, useCallback } from 'react'
import { apiFetch } from '../api/client'
import { formatCategory, formatTransactionCategory, displayCategory, categoryPickerDraft, transactionDisplayIcon, isPfcKey } from '../utils/categories'
import { isPlaidCategoryLabel, primaryForCategoryLabel } from '../utils/plaidCategories'
import CategoryPicker from '../components/CategoryPicker'
import { useOnSyncComplete } from '../hooks/useSync'

type SortField = 'date' | 'merchant' | 'amount' | 'category' | 'account'
type SortDir = 'asc' | 'desc'

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ChevronsUpDown className="w-[12px] h-[12px] opacity-30" strokeWidth={2} />
  return active && dir === 'asc'
    ? <ChevronUp className="w-[12px] h-[12px] text-ledger-accent" strokeWidth={2.5} />
    : <ChevronDown className="w-[12px] h-[12px] text-ledger-accent" strokeWidth={2.5} />
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

type ActionState =
  | { type: 'recategorize'; id: number; draft: string }
  | { type: 'split'; id: number; draft: string; originalAbs: number }
  | { type: 'similar-prompt'; id: number; merchant: string; category: string; similarIds: number[]; makeRule: boolean }
  | null

export default function Transactions() {
  const [transactions, setTransactions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [search, setSearch] = useState('')
  const [selectedMonth, setSelectedMonth] = useState<string>('all')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [selectedAccount, setSelectedAccount] = useState<string>('all')
  const [minAmount, setMinAmount] = useState('')
  const [maxAmount, setMaxAmount] = useState('')

  // Sort
  const [sortField, setSortField] = useState<SortField>('date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Pagination
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  // Inline actions
  const [action, setAction] = useState<ActionState>(null)

  useEffect(() => {
    const fetchTransactions = async () => {
      try {
        const res = await apiFetch('/api/transactions?limit=2000')
        const data = await res.json()
        setTransactions(data.transactions || [])
      } catch (error) {
        console.error('Failed to fetch transactions:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchTransactions()
  }, [])

  useOnSyncComplete(useCallback(() => {
    apiFetch('/api/transactions?limit=2000')
      .then(res => res.json())
      .then(data => setTransactions(data.transactions || []))
      .catch(error => console.error('Failed to refresh transactions after sync:', error))
  }, []))

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1) }, [search, selectedMonth, selectedCategory, selectedAccount, minAmount, maxAmount, sortField, sortDir])

  // Derive available months, categories, accounts
  const months = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach(t => { if (t.date) set.add(t.date.slice(0, 7)) })
    return Array.from(set).sort().reverse()
  }, [transactions])

  const categories = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach(t => {
      const cat = displayCategory(t)
      if (cat) set.add(cat)
    })
    return Array.from(set).sort((a, b) => {
      const labelCmp = formatCategory(a).localeCompare(formatCategory(b))
      return labelCmp !== 0 ? labelCmp : a.localeCompare(b)
    })
  }, [transactions])

  const customCategories = useMemo(() => {
    return categories.filter(c => {
      if (isPfcKey(c)) return false
      if (isPlaidCategoryLabel(c)) return false
      const formatted = formatCategory(c)
      if (isPlaidCategoryLabel(formatted)) return false
      if (primaryForCategoryLabel(c) || primaryForCategoryLabel(formatted)) return false
      return true
    })
  }, [categories])

  const accounts = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach(t => { if (t.account_name) set.add(t.account_name) })
    return Array.from(set).sort()
  }, [transactions])

  // Filter + sort
  const filtered = useMemo(() => {
    let list = transactions

    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(t =>
        t.merchant?.toLowerCase().includes(q) ||
        displayCategory(t).toLowerCase().includes(q)
      )
    }

    if (selectedMonth !== 'all') {
      list = list.filter(t => t.date?.startsWith(selectedMonth))
    }

    if (selectedCategory !== 'all') {
      list = list.filter(t =>
        displayCategory(t) === selectedCategory
      )
    }

    if (selectedAccount !== 'all') {
      list = list.filter(t => t.account_name === selectedAccount)
    }

    const min = parseFloat(minAmount)
    const max = parseFloat(maxAmount)
    if (!isNaN(min)) {
      list = list.filter(t => Math.abs(t.amount) >= min)
    }
    if (!isNaN(max)) {
      list = list.filter(t => Math.abs(t.amount) <= max)
    }

    list = [...list].sort((a, b) => {
      let av: any, bv: any
      if (sortField === 'date') { av = a.date ?? ''; bv = b.date ?? '' }
      else if (sortField === 'merchant') { av = (a.merchant ?? '').toLowerCase(); bv = (b.merchant ?? '').toLowerCase() }
      else if (sortField === 'amount') { av = a.amount ?? 0; bv = b.amount ?? 0 }
      else if (sortField === 'account') { av = (a.account_name ?? '').toLowerCase(); bv = (b.account_name ?? '').toLowerCase() }
      else if (sortField === 'category') {
        av = displayCategory(a).toLowerCase()
        bv = displayCategory(b).toLowerCase()
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })

    return list
  }, [transactions, search, selectedMonth, selectedCategory, selectedAccount, minAmount, maxAmount, sortField, sortDir])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir(field === 'date' ? 'desc' : 'asc')
    }
  }

  const formatMonth = (ym: string) => {
    const [year, month] = ym.split('-')
    const d = new Date(Number(year), Number(month) - 1)
    return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  }

  const exportCsv = () => {
    const header = 'Date,Merchant,Account,Category,Amount'
    const rows = filtered.map(t =>
      [t.date, `"${(t.merchant ?? '').replace(/"/g, '""')}"`, `"${(t.account_name ?? '').replace(/"/g, '""')}"`, displayCategory(t), t.amount].join(',')
    )
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions${selectedMonth !== 'all' ? `-${selectedMonth}` : ''}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── Action handlers ────────────────────────────────────────────────────────

  const handleHide = async (id: number) => {
    try {
      const res = await apiFetch(`/api/transactions/${id}/toggle-hide`, { method: 'POST' })
      const data = await res.json()
      setTransactions(ts => ts.map(t => t.id === id ? { ...t, hidden: data.hidden } : t))
    } catch (e) {
      console.error('Hide failed', e)
    }
  }

  const handleRecategorize = async (id: number, category: string) => {
    const trimmed = category.trim()
    if (!trimmed) return
    try {
      await apiFetch(`/api/transactions/${id}/category`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: trimmed }),
      })
      setTransactions(ts => ts.map(t =>
        t.id === id ? { ...t, category_user: trimmed } : t
      ))

      // Offer to apply the same category to other transactions from this merchant.
      const merchant = transactions.find(t => t.id === id)?.merchant ?? ''
      try {
        const res = await apiFetch(`/api/transactions/${id}/similar`)
        const data = await res.json()
        const similarIds: number[] = (data.transactions || []).map((t: any) => t.id)
        if (similarIds.length > 0) {
          setAction({ type: 'similar-prompt', id, merchant, category: trimmed, similarIds, makeRule: false })
          return
        }
      } catch (e) {
        console.error('Failed to check for similar transactions', e)
      }
      setAction(null)
    } catch (e) {
      console.error('Recategorize failed', e)
    }
  }

  const handleApplySimilar = async (action: { id: number; merchant: string; category: string; similarIds: number[]; makeRule: boolean }) => {
    try {
      await apiFetch('/api/transactions/bulk-categorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: action.similarIds, category: action.category }),
      })
      const updated = new Set(action.similarIds)
      setTransactions(ts => ts.map(t => updated.has(t.id) ? { ...t, category_user: action.category } : t))

      if (action.makeRule) {
        await apiFetch('/api/categorization-rules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ merchant_pattern: escapeRegExp(action.merchant), category_name: action.category }),
        })
      }
    } catch (e) {
      console.error('Apply to similar failed', e)
    } finally {
      setAction(null)
    }
  }

  const handleSplit = async (id: number, dollarStr: string, originalAbs: number) => {
    const dollars = parseFloat(dollarStr)
    if (isNaN(dollars) || dollars <= 0 || dollars > originalAbs) return
    const pct = dollars / originalAbs
    try {
      await apiFetch(`/api/transactions/${id}/split`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pct }),
      })
      setTransactions(ts => ts.map(t => {
        if (t.id !== id) return t
        const sign = (t.original_amount ?? t.amount) < 0 ? -1 : 1
        return { ...t, amount: +(sign * dollars).toFixed(2), user_split_pct: pct < 1 ? pct : null }
      }))
      setAction(null)
    } catch (e) {
      console.error('Split failed', e)
    }
  }

  const ThBtn = ({ field, label }: { field: SortField; label: string }) => (
    <button
      onClick={() => toggleSort(field)}
      className="flex items-center gap-[4px] text-[11.5px] text-ledger-text-faintest uppercase font-medium hover:text-ledger-text-muted transition-colors"
    >
      {label}
      <SortIcon active={sortField === field} dir={sortDir} />
    </button>
  )

  // Derived split state for the modal
  const splitAction = action?.type === 'split' ? action : null
  const splitDollar = splitAction ? parseFloat(splitAction.draft) : NaN
  const splitValid = !isNaN(splitDollar) && splitDollar > 0 && splitDollar <= (splitAction?.originalAbs ?? 0)
  const splitPct = splitValid && splitAction ? Math.round((splitDollar / splitAction.originalAbs) * 100) : null
  const splitTxn = splitAction ? transactions.find(t => t.id === splitAction.id) : null

  return (
    <div className="flex flex-col gap-[18px]">
      {/* Filter Bar */}
      <div className="flex flex-wrap gap-[10px] items-center">
        <input
          type="text"
          placeholder="Search merchant or category…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-[180px] glass-chip px-[12px] py-[8px] text-ledger-text-primary text-[13px] placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
        />

        <select
          value={selectedMonth}
          onChange={e => setSelectedMonth(e.target.value)}
          className="glass-chip px-[10px] py-[8px] text-ledger-text-primary text-[13px] cursor-pointer focus:outline-none focus:border-ledger-accent/60"
        >
          <option value="all">All months</option>
          {months.map(m => (
            <option key={m} value={m}>{formatMonth(m)}</option>
          ))}
        </select>

        <select
          value={selectedAccount}
          onChange={e => setSelectedAccount(e.target.value)}
          className="glass-chip px-[10px] py-[8px] text-ledger-text-primary text-[13px] cursor-pointer focus:outline-none focus:border-ledger-accent/60"
        >
          <option value="all">All accounts</option>
          {accounts.map(a => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>

        <select
          value={selectedCategory}
          onChange={e => setSelectedCategory(e.target.value)}
          className="glass-chip px-[10px] py-[8px] text-ledger-text-primary text-[13px] cursor-pointer focus:outline-none focus:border-ledger-accent/60"
        >
          <option value="all">All categories</option>
          {categories.map(c => (
            <option key={c} value={c}>{formatCategory(c)}</option>
          ))}
        </select>

        <div className="flex items-center gap-[6px] glass-chip px-[10px] py-[8px]">
          <span className="text-[12px] text-ledger-text-faint select-none">$</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="Min"
            value={minAmount}
            onChange={e => setMinAmount(e.target.value.replace(/[^0-9.]/g, ''))}
            className="w-[52px] bg-transparent text-ledger-text-primary text-[13px] tabular-nums placeholder-ledger-text-faint focus:outline-none"
          />
          <span className="text-[12px] text-ledger-text-faintest select-none">–</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="Max"
            value={maxAmount}
            onChange={e => setMaxAmount(e.target.value.replace(/[^0-9.]/g, ''))}
            className="w-[52px] bg-transparent text-ledger-text-primary text-[13px] tabular-nums placeholder-ledger-text-faint focus:outline-none"
          />
        </div>

        <button
          onClick={exportCsv}
          className="ml-auto flex items-center gap-[6px] glass-chip px-[12px] py-[8px] text-ledger-text-primary text-[13px] hover:opacity-80 transition-opacity"
        >
          <Download className="w-[14px] h-[14px]" strokeWidth={2} />
          Export CSV
        </button>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ledger-border-subtle">
                <th className="text-left px-[20px] py-[12px]">
                  <ThBtn field="merchant" label="Merchant" />
                </th>
                <th className="text-left px-[20px] py-[12px]">
                  <ThBtn field="account" label="Account" />
                </th>
                <th className="text-left px-[20px] py-[12px]">
                  <ThBtn field="category" label="Category" />
                </th>
                <th className="text-left px-[20px] py-[12px]">
                  <ThBtn field="date" label="Date" />
                </th>
                <th className="text-right px-[20px] py-[12px]">
                  <div className="flex justify-end">
                    <ThBtn field="amount" label="Amount" />
                  </div>
                </th>
                <th className="w-[80px]" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-[20px] py-[40px] text-center text-ledger-text-faint text-[13px]">
                    Loading…
                  </td>
                </tr>
              ) : paginated.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-[20px] py-[40px] text-center text-ledger-text-faint text-[13px]">
                    {transactions.length === 0
                      ? 'No transactions yet. Link an account or import a CSV.'
                      : 'No transactions match your filters.'}
                  </td>
                </tr>
              ) : (
                paginated.map((txn) => {
                  const isRecat = action?.type === 'recategorize' && action.id === txn.id
                  const isSplit = action?.type === 'split' && action.id === txn.id
                  const isSimilarPrompt = action?.type === 'similar-prompt' && action.id === txn.id
                  const recatDraft = isRecat ? action.draft : categoryPickerDraft(txn)
                  const recatExpandedPrimary = isRecat
                    ? primaryForCategoryLabel(recatDraft) ?? primaryForCategoryLabel(formatCategory(recatDraft))
                    : null
                  const iconUrl = transactionDisplayIcon(txn)

                  return (
                    <Fragment key={txn.id}>
                      <tr className={`border-b border-ledger-border-subtle last:border-0 hover:bg-ledger-inset transition-colors group ${txn.hidden ? 'opacity-35' : ''}`}>
                        <td className="px-[20px] py-[11px] text-[13px] text-ledger-text-primary">
                          <div className="flex items-center gap-[8px]">
                            {iconUrl ? (
                              <img
                                src={iconUrl}
                                alt=""
                                className="w-[20px] h-[20px] rounded-[4px] shrink-0 bg-ledger-inset object-contain"
                              />
                            ) : null}
                            <span>{txn.merchant}</span>
                          </div>
                          {txn.hidden && <span className="ml-[6px] text-[10px] text-ledger-text-faintest">(hidden)</span>}
                        </td>
                        <td className="px-[20px] py-[11px] text-[13px] text-ledger-text-secondary">
                          {txn.account_name ?? <span className="text-ledger-text-faintest">—</span>}
                        </td>
                        <td className="px-[20px] py-[11px]">
                          <button
                            onClick={() => setAction(isRecat ? null : { type: 'recategorize', id: txn.id, draft: categoryPickerDraft(txn) })}
                            className={`inline-flex max-w-full items-center gap-[6px] text-[11px] px-[9px] py-[3px] rounded-[7px] border transition-all ${
                              isRecat
                                ? 'bg-ledger-accent/18 text-ledger-text-primary border-ledger-accent/40'
                                : 'glass-chip text-ledger-text-muted border-white/15 hover:text-ledger-text-primary hover:border-ledger-accent/30'
                            }`}
                          >
                            <span className="truncate">{formatTransactionCategory(txn)}</span>
                            <ChevronDown className={`w-[11px] h-[11px] flex-shrink-0 transition-transform ${isRecat ? 'rotate-180 text-ledger-accent' : 'text-ledger-text-faint'}`} strokeWidth={2.2} />
                          </button>
                        </td>
                        <td className="px-[20px] py-[11px] text-[13px] text-ledger-text-faintest tabular-nums">
                          {new Date(txn.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                        </td>
                        <td className="px-[20px] py-[11px] text-right text-[14px] font-semibold tabular-nums"
                          style={{ color: txn.amount < 0 ? '#4ec38a' : undefined }}>
                          {txn.amount < 0 ? '+' : '−'}${Math.abs(txn.amount).toFixed(2)}
                          {txn.user_split_pct && txn.user_split_pct < 1 && (
                            <span className="ml-[5px] text-[10px] font-normal text-ledger-text-faintest">
                              ({Math.round(txn.user_split_pct * 100)}%)
                            </span>
                          )}
                        </td>
                        {/* Actions column */}
                        <td className="px-[12px] py-[11px]">
                          <div className="flex gap-[4px] justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              title="Split"
                              onClick={() => {
                                const abs = Math.abs(txn.original_amount ?? txn.amount)
                                setAction(isSplit ? null : { type: 'split', id: txn.id, draft: (abs / 2).toFixed(2), originalAbs: abs })
                              }}
                              className={`p-[5px] rounded-[6px] transition-colors ${isSplit ? 'bg-ledger-accent/20 text-ledger-accent' : 'text-ledger-text-faint hover:text-ledger-text-primary hover:bg-ledger-inset'}`}
                            >
                              <Scissors className="w-[13px] h-[13px]" strokeWidth={2} />
                            </button>
                            <button
                              title={txn.hidden ? 'Unhide' : 'Hide'}
                              onClick={() => handleHide(txn.id)}
                              className={`p-[5px] rounded-[6px] transition-colors ${txn.hidden ? 'text-ledger-accent hover:bg-ledger-inset' : 'text-ledger-text-faint hover:text-ledger-negative hover:bg-ledger-inset'}`}
                            >
                              {txn.hidden
                                ? <Eye className="w-[13px] h-[13px]" strokeWidth={2} />
                                : <EyeOff className="w-[13px] h-[13px]" strokeWidth={2} />
                              }
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Inline: Re-categorize */}
                      {isRecat && (
                        <tr className="bg-ledger-inset border-b border-ledger-border-subtle">
                          <td colSpan={6} className="px-[20px] py-[10px]">
                            <div className="glass-chip rounded-[12px] px-[12px] py-[12px]">
                              <div className="flex items-center gap-[8px] mb-[10px]">
                                <span className="text-[12px] text-ledger-text-faint flex-shrink-0">New category</span>
                                <input
                                  autoFocus
                                  value={recatDraft}
                                  onChange={e => setAction({ type: 'recategorize', id: txn.id, draft: e.target.value })}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter') handleRecategorize(txn.id, recatDraft)
                                    if (e.key === 'Escape') setAction(null)
                                  }}
                                  className="flex-1 glass-chip rounded-[8px] px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/50"
                                  placeholder="Type or choose a category…"
                                />
                                <button
                                  onClick={() => handleRecategorize(txn.id, recatDraft)}
                                  className="px-[10px] py-[7px] rounded-[8px] bg-ledger-accent text-ledger-accent-on text-[12px] font-semibold hover:opacity-90 transition-opacity"
                                >
                                  Save
                                </button>
                                <button
                                  onClick={() => setAction(null)}
                                  className="p-[6px] rounded-[7px] text-ledger-text-faint hover:bg-ledger-hover transition-colors"
                                >
                                  <X className="w-[14px] h-[14px]" strokeWidth={2} />
                                </button>
                              </div>

                              <div className="rounded-[10px] border border-ledger-border bg-black/10 overflow-hidden">
                                <div className="px-[10px] py-[7px] text-[10px] uppercase tracking-[0.12em] text-ledger-text-faintest border-b border-ledger-border-subtle">
                                  Categories
                                </div>
                                <CategoryPicker
                                  draft={recatDraft}
                                  customCategories={customCategories}
                                  initialExpandedPrimary={recatExpandedPrimary}
                                  onSelect={category => handleRecategorize(txn.id, category)}
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}

                      {/* Inline: apply new category to similar transactions */}
                      {isSimilarPrompt && action?.type === 'similar-prompt' && (
                        <tr className="bg-ledger-inset border-b border-ledger-border-subtle">
                          <td colSpan={6} className="px-[20px] py-[10px]">
                            <div className="flex items-center gap-[12px] flex-wrap">
                              <span className="text-[12px] text-ledger-text-secondary">
                                Apply <span className="font-semibold text-ledger-text-primary">{formatCategory(action.category)}</span> to{' '}
                                <span className="font-semibold text-ledger-text-primary">{action.similarIds.length}</span> other{' '}
                                <span className="font-semibold text-ledger-text-primary">{action.merchant}</span> transaction{action.similarIds.length !== 1 ? 's' : ''}?
                              </span>
                              <label className="flex items-center gap-[6px] text-[12px] text-ledger-text-faint cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={action.makeRule}
                                  onChange={e => setAction({ ...action, makeRule: e.target.checked })}
                                  className="cursor-pointer"
                                />
                                Always categorize {action.merchant} this way
                              </label>
                              <div className="flex gap-[6px] ml-auto">
                                <button
                                  onClick={() => handleApplySimilar(action)}
                                  className="px-[10px] py-[5px] rounded-[7px] bg-ledger-accent text-ledger-accent-on text-[12px] font-semibold hover:opacity-90 transition-opacity"
                                >
                                  Apply
                                </button>
                                <button
                                  onClick={() => setAction(null)}
                                  className="px-[10px] py-[5px] rounded-[7px] text-ledger-text-faint hover:bg-ledger-card transition-colors text-[12px]"
                                >
                                  Skip
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}

                      {/* Split opens a modal — no inline row */}
                    </Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer: count + pagination */}
        {!loading && filtered.length > 0 && (
          <div className="px-[20px] py-[11px] border-t border-ledger-border-subtle text-[12px] text-ledger-text-faint flex items-center justify-between">
            <span>
              {filtered.length} transaction{filtered.length !== 1 ? 's' : ''}
              {(search || selectedMonth !== 'all' || selectedCategory !== 'all' || selectedAccount !== 'all' || minAmount || maxAmount) && ` (filtered from ${transactions.length})`}
            </span>

            {totalPages > 1 && (
              <div className="flex items-center gap-[6px]">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-[8px] py-[3px] rounded-[6px] border border-ledger-border-input hover:bg-ledger-inset disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  ←
                </button>
                <span className="tabular-nums">{page} / {totalPages}</span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-[8px] py-[3px] rounded-[6px] border border-ledger-border-input hover:bg-ledger-inset disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  →
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Split modal */}
      {splitAction && splitTxn && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-[8px]"
          onClick={e => { if (e.target === e.currentTarget) setAction(null) }}
        >
          <div
            className="w-[440px] rounded-[22px] border p-[28px] shadow-[0_28px_80px_-32px_rgba(0,0,0,0.88),0_0_42px_rgba(110,130,255,0.10),inset_0_1px_0_rgba(255,255,255,0.18)]"
            style={{
              background: 'linear-gradient(165deg, rgba(24,27,37,0.96), rgba(16,19,27,0.94) 55%, rgba(12,14,20,0.98))',
              borderColor: 'rgba(255,255,255,0.16)',
            }}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-[20px]">
              <div>
                <div className="text-[16px] font-semibold text-ledger-text-primary">Split transaction</div>
                <div className="text-[13px] text-ledger-text-faint mt-[3px]">
                  Enter your share of this charge
                </div>
              </div>
              <button
                onClick={() => setAction(null)}
                className="p-[6px] rounded-[8px] text-ledger-text-faint hover:bg-ledger-hover transition-colors"
              >
                <X className="w-[16px] h-[16px]" strokeWidth={2} />
              </button>
            </div>

            {/* Transaction summary */}
            <div className="rounded-[12px] px-[14px] py-[12px] mb-[22px] border border-white/12 bg-white/[0.06] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
              <div className="text-[13px] font-medium text-ledger-text-primary">{splitTxn.merchant}</div>
              <div className="text-[12px] text-ledger-text-faint mt-[2px]">
                {splitTxn.account_name} · {new Date(splitTxn.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
              </div>
              <div className="text-[22px] font-bold tabular-nums mt-[6px]">
                ${splitAction.originalAbs.toFixed(2)}
                <span className="ml-[8px] text-[13px] font-normal text-ledger-text-faint">total charge</span>
              </div>
            </div>

            {/* Dollar input */}
            <div className="mb-[8px]">
              <label className="text-[12px] text-ledger-text-faint font-medium block mb-[8px]">Your share</label>
              <div className="flex items-center gap-[8px]">
                <div className="relative flex-1">
                  <span className="absolute left-[12px] top-1/2 -translate-y-1/2 text-[15px] text-ledger-text-faint select-none">$</span>
                  <input
                    autoFocus
                    type="text"
                    inputMode="decimal"
                    value={splitAction.draft}
                    onChange={e => {
                      const v = e.target.value.replace(/[^0-9.]/g, '')
                      setAction({ ...splitAction, draft: v })
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleSplit(splitAction.id, splitAction.draft, splitAction.originalAbs)
                      if (e.key === 'Escape') setAction(null)
                    }}
                    className="w-full glass-chip pl-[28px] pr-[12px] py-[10px] text-[18px] font-semibold text-ledger-text-primary tabular-nums bg-white/[0.06] focus:outline-none focus:border-ledger-accent/70"
                    placeholder="0.00"
                  />
                </div>
                <span className="text-[13px] text-ledger-text-faint flex-shrink-0">
                  of ${splitAction.originalAbs.toFixed(2)}
                </span>
              </div>
            </div>

            {/* Quick-split buttons */}
            <div className="flex gap-[8px] mb-[22px]">
              {[2, 3, 4].map(n => (
                <button
                  key={n}
                  onClick={() => setAction({ ...splitAction, draft: (splitAction.originalAbs / n).toFixed(2) })}
                  className="flex-1 py-[7px] rounded-[8px] glass-chip bg-white/[0.05] text-[12px] text-ledger-text-secondary hover:text-ledger-text-primary hover:border-ledger-accent/40 hover:bg-white/[0.08] transition-colors"
                >
                  ÷{n} = ${(splitAction.originalAbs / n).toFixed(2)}
                </button>
              ))}
            </div>

            {/* Percentage hint */}
            {splitPct !== null && (
              <div className="text-[12px] text-ledger-text-faint mb-[18px] tabular-nums">
                That's <span className="text-ledger-text-primary font-medium">{splitPct}%</span> of the total
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-[10px]">
              <button
                onClick={() => setAction(null)}
                className="flex-1 py-[10px] rounded-[10px] border border-white/14 bg-white/[0.04] text-[13px] text-ledger-text-secondary hover:bg-white/[0.08] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleSplit(splitAction.id, splitAction.draft, splitAction.originalAbs)}
                disabled={!splitValid}
                className="flex-1 py-[10px] rounded-[10px] bg-ledger-accent text-ledger-accent-on text-[13px] font-semibold hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
              >
                Apply split
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
