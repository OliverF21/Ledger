import { RefreshCw } from 'lucide-react'
import { useSync } from '../hooks/useSync'

interface HeaderProps {
  title: string
  subtitle: string
  name?: string
}

/** Up to two initials from a name: "Oliver Fichte" → "OF", "ofichte" → "O". */
function initials(name?: string): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return 'A'
  const first = words[0][0]
  const last = words.length > 1 ? words[words.length - 1][0] : ''
  return (first + last).toUpperCase()
}

export default function Header({ title, subtitle, name }: HeaderProps) {
  const { syncing: isSyncing, sync } = useSync()

  const handleSync = async () => {
    try {
      const data = await sync()
      if (data?.success) {
        alert(`Synced ${data.transactions_synced} transactions`)
      } else {
        alert('Sync failed: ' + (data?.message ?? 'unknown error'))
      }
    } catch (error) {
      alert('Sync error: ' + (error instanceof Error ? error.message : String(error)))
    }
  }

  return (
    <header className="glass-header px-5 short:px-6 tall:px-7 py-3 short:py-[14px] tall:py-[18px] flex items-center justify-between shrink-0">
      <div>
        <h1 className="text-lg font-bold tracking-tight">{title}</h1>
        <p className="text-sm text-ledger-text-faint mt-0.5">{subtitle}</p>
      </div>

      <div className="flex items-center gap-2.5">
        <button
          onClick={() => {
            const settingsNav = document.querySelector('[data-nav-settings]') as HTMLButtonElement
            if (settingsNav) settingsNav.click()
          }}
          className="flex items-center gap-1.5 glass-chip text-ledger-text-primary px-3.5 py-2 font-semibold text-sm cursor-pointer"
        >
          Link Account
        </button>

        <button
          onClick={handleSync}
          disabled={isSyncing}
          className="flex items-center gap-1.5 bg-ledger-accent text-ledger-accent-on border-none rounded-chip px-3.5 py-2 font-semibold text-sm cursor-pointer hover:bg-ledger-accent-hover active:bg-ledger-accent-press active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw
            className={`w-4 h-4 flex-shrink-0 ${isSyncing ? 'animate-spin' : ''}`}
            strokeWidth={2.2}
          />
          {isSyncing ? 'Syncing...' : 'Sync'}
        </button>

        <button
          onClick={() => {
            const settingsNav = document.querySelector('[data-nav-settings]') as HTMLButtonElement
            if (settingsNav) settingsNav.click()
          }}
          className="w-9 h-9 rounded-full bg-ledger-card-alt border border-ledger-border-input flex items-center justify-center text-sm font-bold text-ledger-text-secondary hover:bg-ledger-hover hover:text-ledger-text-primary cursor-pointer"
        >
          {initials(name)}
        </button>
      </div>
    </header>
  )
}
