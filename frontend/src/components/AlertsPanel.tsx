import { AlertTriangle, TrendingUp } from 'lucide-react'
import { useAlerts } from '../hooks/useAlerts'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/**
 * Inline alert strip above the Overview hero. Deliberately a row of chips
 * rather than a card: alerts are transient, and a full glass panel here would
 * push the net-worth figure — the reason for the screen — below the fold.
 */
export default function AlertsPanel() {
  const { alerts, loading } = useAlerts()

  if (loading) return null
  if (alerts.budget_exceeded.length === 0 && alerts.large_transactions.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2 mb-2.5">
      {alerts.budget_exceeded.map(budget => (
        <span
          key={budget.category}
          className="inline-flex items-center gap-[7px] text-[11.5px] px-[10px] py-[5px] rounded-[9px] whitespace-nowrap"
          style={{
            color: '#f5b3a4',
            background: 'rgba(244,144,127,0.11)',
            border: '1px solid rgba(244,144,127,0.26)',
          }}
        >
          <AlertTriangle className="w-[13px] h-[13px] shrink-0" strokeWidth={2.2} />
          <span className="font-bold">{budget.category}</span>
          over budget · ${fmt(budget.spent)} of ${fmt(budget.limit)}
        </span>
      ))}
      {alerts.large_transactions.map(txn => (
        <span
          key={txn.id}
          className="inline-flex items-center gap-[7px] text-[11.5px] px-[10px] py-[5px] rounded-[9px] whitespace-nowrap"
          style={{
            color: '#f0d3a4',
            background: 'rgba(230,189,121,0.11)',
            border: '1px solid rgba(230,189,121,0.26)',
          }}
        >
          <TrendingUp className="w-[13px] h-[13px] shrink-0" strokeWidth={2.2} />
          <span className="font-bold">{txn.merchant}</span>
          ${fmt(txn.amount)} on {txn.date}
        </span>
      ))}
    </div>
  )
}
