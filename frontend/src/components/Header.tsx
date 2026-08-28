import type { ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import { useSync } from '../hooks/useSync'
import { Eyebrow } from './ui/primitives'

interface HeaderProps {
  /** Uppercase micro-label above the title — today's date, or the section.
   *  Empty on screens whose title already says everything. */
  eyebrow?: string
  title: string
  name?: string
  /** Screen-specific controls (a month picker, a filter) rendered to the left
   *  of Sync. Keeps each page's own state where it belongs while still
   *  landing in the header cluster the design calls for. */
  controls?: ReactNode
  onOpenSettings?: () => void
}

/** Up to two initials from a name: "Oliver Fichte" → "OF", "ofichte" → "O". */
function initials(name?: string): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return 'A'
  const first = words[0][0]
  const last = words.length > 1 ? words[words.length - 1][0] : ''
  return (first + last).toUpperCase()
}

function openSettingsScreen() {
  const settingsNav = document.querySelector('[data-nav-settings]') as HTMLButtonElement | null
  settingsNav?.click()
}

/**
 * Page header. Sits directly on the aurora rather than in a bar of its own —
 * the eyebrow/title pair on the left, the action cluster on the right, and
 * nothing between them. Sync is the one solid-white surface here, which is
 * what makes it read as the primary action without needing an accent colour.
 */
export default function Header({ eyebrow, title, name, controls, onOpenSettings }: HeaderProps) {
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

  const goToSettings = onOpenSettings ?? openSettingsScreen

  return (
    <header className="flex items-start justify-between gap-4 pt-[2px] pl-[2px] pr-1 shrink-0">
      <div className="min-w-0">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className={`text-[24px] font-bold tracking-[-0.035em] leading-none truncate ${eyebrow ? 'mt-[5px]' : 'mt-[7px]'}`}>
          {title}
        </h1>
      </div>

      <div className="flex items-center gap-[9px] shrink-0">
        {controls}

        <button
          type="button"
          onClick={handleSync}
          disabled={isSyncing}
          className="solid-cta rounded-[11px] flex items-center gap-[7px] h-[34px] px-[15px] text-[12.5px] font-semibold whitespace-nowrap"
        >
          <RefreshCw className={`w-[13px] h-[13px] shrink-0 ${isSyncing ? 'animate-spin' : ''}`} strokeWidth={2.2} />
          {isSyncing ? 'Syncing…' : 'Sync'}
        </button>

        <button
          type="button"
          onClick={goToSettings}
          aria-label="Open settings"
          className="w-[34px] h-[34px] rounded-full flex items-center justify-center text-[12px] font-bold text-white hover:brightness-110 transition-[filter]"
          style={{
            background: 'linear-gradient(150deg, rgba(255,255,255,0.26), rgba(255,255,255,0.06))',
            border: '1px solid rgba(255,255,255,0.26)',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.55)',
          }}
        >
          {initials(name)}
        </button>
      </div>
    </header>
  )
}
