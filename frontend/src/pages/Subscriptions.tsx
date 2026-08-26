import { Repeat } from 'lucide-react'
import { useSubscriptions } from '../hooks/useSubscriptions'
import { formatCategory } from '../utils/categories'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatCadence(cadence: string) {
  if (cadence === 'weekly') return 'Weekly'
  if (cadence === 'monthly') return 'Monthly'
  if (cadence === 'annual') return 'Annual'
  return cadence
}

export default function Subscriptions() {
  const { subscriptions, loading } = useSubscriptions()

  const monthlyTotal = subscriptions.reduce((sum, s) => {
    if (s.cadence === 'monthly') return sum + s.average_amount
    if (s.cadence === 'weekly') return sum + s.average_amount * 4.33
    if (s.cadence === 'annual') return sum + s.average_amount / 12
    return sum
  }, 0)

  return (
    <div className="flex flex-col gap-[24px] max-w-[1000px]">
      {/* Summary bar */}
      <div className="glass-card p-[22px]">
        <div className="grid grid-cols-2 gap-[24px] items-center">
          <div>
            <div className="metric-label">Detected recurring charges</div>
            <div className="text-stat font-bold mt-[6px] font-mono text-ledger-text-heading">
              {loading ? '—' : subscriptions.length}
            </div>
          </div>
          <div>
            <div className="metric-label">Est. monthly cost</div>
            <div className="text-stat font-bold mt-[6px] font-mono text-ledger-text-heading">
              {loading ? '—' : `$${fmt(monthlyTotal)}`}
            </div>
          </div>
        </div>
      </div>

      {/* Cards */}
      {loading ? (
        <div className="text-center py-16 text-ledger-text-faint text-[13px]">Loading…</div>
      ) : subscriptions.length === 0 ? (
        <div className="glass-card p-[40px] text-center">
          <Repeat className="w-[24px] h-[24px] text-ledger-text-faint mx-auto mb-[10px]" strokeWidth={1.8} />
          <div className="text-[14px] font-semibold mb-[8px]">No recurring charges detected</div>
          <div className="text-[13px] text-ledger-text-faint">
            Subscriptions are detected from transaction history: merchants billed on a
            regular schedule for a consistent amount, at least 3 times.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-[18px]">
          {subscriptions.map((sub, i) => (
            <div key={`${sub.merchant}-${i}`} className="glass-card p-[18px]">
              <div className="flex items-center gap-[10px] mb-[12px]">
                <span className="text-title font-semibold flex-1 truncate">{sub.merchant}</span>
                <span className="text-[11px] px-[8px] py-[2px] rounded-[6px] bg-ledger-inset border border-ledger-border text-ledger-text-muted whitespace-nowrap">
                  {formatCadence(sub.cadence)}
                </span>
              </div>

              <div className="text-[19px] font-bold mb-[10px] font-mono text-ledger-text-heading">
                ${fmt(sub.average_amount)}
              </div>

              <div className="text-[11.5px] text-ledger-text-muted mb-[4px]">
                {formatCategory(sub.category)}
              </div>
              <div className="text-[11px] text-ledger-text-faint">
                Next expected {formatDate(sub.next_expected_date)} · {sub.occurrence_count} charges seen
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
