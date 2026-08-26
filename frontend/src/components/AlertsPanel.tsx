import { AlertTriangle, TrendingUp } from 'lucide-react'
import { useAlerts } from '../hooks/useAlerts'
import { formatCategory } from '../utils/categories'

function money(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function AlertsPanel() {
  const { alerts, loading } = useAlerts()

  if (loading) return null
  if (alerts.budget_exceeded.length === 0 && alerts.large_transactions.length === 0) return null

  return (
    <div className="glass-card px-3.5 py-1 mb-3 divide-y divide-ledger-border-subtle">
      {alerts.budget_exceeded.map(b => (
        <div key={b.category} className="flex items-center gap-[10px] text-[13px] py-2.5">
          <AlertTriangle className="w-[15px] h-[15px] text-ledger-negative flex-shrink-0" strokeWidth={2} />
          <span className="text-ledger-text-secondary">
            {/* Was printing the raw category key, e.g. FOOD_AND_DRINK_GROCERIES. */}
            <span className="font-semibold text-ledger-text-primary">{formatCategory(b.category)}</span>
            {' is over budget. '}
            <span className="font-mono text-ledger-negative">${money(b.spent)}</span>
            {' spent of '}
            <span className="font-mono">${money(b.limit)}</span>
          </span>
        </div>
      ))}
      {alerts.large_transactions.map(t => (
        <div key={t.id} className="flex items-center gap-[10px] text-[13px] py-2.5">
          <TrendingUp className="w-[15px] h-[15px] text-ledger-warning flex-shrink-0" strokeWidth={2} />
          <span className="text-ledger-text-secondary">
            {'Large transaction at '}
            <span className="font-semibold text-ledger-text-primary">{t.merchant}</span>
            {'. '}
            <span className="font-mono">${money(Math.abs(t.amount))}</span>
            {` on ${t.date}`}
          </span>
        </div>
      ))}
    </div>
  )
}
