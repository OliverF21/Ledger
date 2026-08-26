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
    <header className="glass-header px-6 py-3.5 flex items-center justify-between shrink-0">
      <div>
        <h1 className="text-[20px] font-semibold tracking-tight leading-tight">{title}</h1>
        {subtitle ? (
          <p className="text-[12.5px] text-ledger-text-faint mt-0.5">{subtitle}</p>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => {
            const settingsNav = document.querySelector('[data-nav-settings]') as HTMLButtonElement
            if (settingsNav) settingsNav.click()
          }}
          className="flex items-center gap-1.5 glass-chip text-ledger-text-primary px-3 py-[7px] font-medium text-[13px] cursor-pointer hover:bg-ledger-hover"
        >
          Link Account
        </button>

        <button
          onClick={handleSync}
          disabled={isSyncing}
          className="flex items-center gap-1.5 bg-ledger-accent text-ledger-accent-on border-none rounded-btn px-3 py-[7px] font-semibold text-[13px] cursor-pointer hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw
            className={`w-[14px] h-[14px] flex-shrink-0 ${isSyncing ? 'animate-spin' : ''}`}
            strokeWidth={2.2}
          />
          {isSyncing ? 'Syncing...' : 'Sync'}
        </button>

        <button
          onClick={() => {
            const settingsNav = document.querySelector('[data-nav-settings]') as HTMLButtonElement
            if (settingsNav) settingsNav.click()
          }}
          className="w-8 h-8 rounded-full bg-ledger-inset border border-ledger-border flex items-center justify-center text-[12px] font-semibold text-ledger-text-secondary hover:text-ledger-text-primary cursor-pointer"
        >
          {initials(name)}
        </button>
      </div>
    </header>
  )
}
