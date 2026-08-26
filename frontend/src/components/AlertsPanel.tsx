import { AlertTriangle, TrendingUp } from 'lucide-react'
import { useAlerts } from '../hooks/useAlerts'

export default function AlertsPanel() {
  const { alerts, loading } = useAlerts()

  if (loading) return null
  if (alerts.budget_exceeded.length === 0 && alerts.large_transactions.length === 0) return null

  return (
    <div className="glass-card p-3.5 mb-3 space-y-2">
      {alerts.budget_exceeded.map(b => (
        <div key={b.category} className="flex items-center gap-[10px] text-[13px]">
          <AlertTriangle className="w-[15px] h-[15px] text-ledger-negative flex-shrink-0" strokeWidth={2} />
          <span className="text-ledger-text-primary">
            <span className="font-semibold">{b.category}</span> is over budget — ${b.spent.toFixed(2)} spent of ${b.limit.toFixed(2)}
          </span>
        </div>
      ))}
      {alerts.large_transactions.map(t => (
        <div key={t.id} className="flex items-center gap-[10px] text-[13px]">
          <TrendingUp className="w-[15px] h-[15px] text-ledger-warning flex-shrink-0" strokeWidth={2} />
          <span className="text-ledger-text-primary">
            Large transaction: <span className="font-semibold">{t.merchant}</span> — ${t.amount.toFixed(2)} on {t.date}
          </span>
        </div>
      ))}
    </div>
  )
}
