import {
  LayoutGrid, AlignLeft, ArrowLeftRight, PieChart, BarChart3,
  TrendingUp, Repeat, Sparkles, SlidersHorizontal, LogOut,
} from 'lucide-react'
import { type AccountItem } from '../hooks/useAccounts'
import { type ScreenType } from '../utils/screens'
import InstitutionAvatar from './InstitutionAvatar'

interface SidebarProps {
  activeScreen: ScreenType
  onScreenChange: (screen: ScreenType) => void
  onSignOut?: () => void
  advisorCount?: number
  accounts: AccountItem[]
  /** Rail expansion is owned by App because `<main>`'s left margin animates
   *  in lockstep with the rail's width. */
  open: boolean
  onOpenChange: (open: boolean) => void
}

const navItems: { id: ScreenType; label: string; icon: typeof LayoutGrid }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutGrid },
  { id: 'transactions', label: 'Transactions', icon: AlignLeft },
  { id: 'spending', label: 'Cash Flow', icon: ArrowLeftRight },
  { id: 'investments', label: 'Investments', icon: PieChart },
  { id: 'budgets', label: 'Budgets', icon: BarChart3 },
  { id: 'trends', label: 'Trends', icon: TrendingUp },
  { id: 'subscriptions', label: 'Subscriptions', icon: Repeat },
  { id: 'advisor', label: 'AI Advisor', icon: Sparkles },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal },
]

function groupByItem(accounts: AccountItem[]): {
  itemId: number
  name: string
  logo: string | null
  color: string | null
}[] {
  const seen = new Map<number, { itemId: number; name: string; logo: string | null; color: string | null }>()
  for (const acc of accounts) {
    if (!seen.has(acc.item_id)) {
      const inst = acc.institution_name || acc.name
      seen.set(acc.item_id, {
        itemId: acc.item_id,
        name: inst,
        logo: acc.institution_logo ?? null,
        color: acc.institution_color ?? null,
      })
    }
  }
  return Array.from(seen.values())
}

/**
 * Collapsed icon rail that widens on hover (66px → 214px). It floats over the
 * page rather than taking a column, so the content behind it stays put and
 * only `<main>`'s left margin animates — see App.tsx.
 *
 * Hover alone would strand keyboard users, so `focus-within` opens it too:
 * tabbing into a nav row reveals its label instead of leaving nine unlabelled
 * icons.
 */
export default function Sidebar({
  activeScreen, onScreenChange, onSignOut, advisorCount = 0, accounts, open, onOpenChange,
}: SidebarProps) {
  const institutions = groupByItem(accounts)

  // Every label in the rail fades on the same curve, slightly delayed on the
  // way in so text doesn't appear before the rail has room for it.
  const labelStyle = {
    opacity: open ? 1 : 0,
    transition: open ? 'opacity .18s ease .08s' : 'opacity .08s ease',
  } as const

  return (
    <aside
      onMouseEnter={() => onOpenChange(true)}
      onMouseLeave={() => onOpenChange(false)}
      onFocus={() => onOpenChange(true)}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) onOpenChange(false)
      }}
      aria-label="Main navigation"
      className="glass-rail absolute left-[14px] top-[14px] bottom-[14px] z-20 flex flex-col overflow-hidden px-3 pt-[18px] pb-4"
      style={{
        width: open ? 214 : 66,
        transition: 'width .28s cubic-bezier(.22,.8,.2,1)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-[11px] pt-[3px] pb-5 pl-1 overflow-hidden">
        <div
          className="w-[27px] h-[27px] flex-shrink-0 rounded-[9px] flex items-center justify-center"
          style={{
            background: 'linear-gradient(150deg, #ffffff, rgba(203,218,244,0.62))',
            boxShadow: '0 6px 18px -6px rgba(196,214,248,0.6), inset 0 1px 0 rgba(255,255,255,0.95)',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0a0c10" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 7v14" />
            <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
          </svg>
        </div>
        <span
          className="text-[15.5px] font-bold tracking-[-0.03em] whitespace-nowrap"
          style={labelStyle}
        >
          Ledger
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-[3px]">
        {navItems.map(item => {
          const Icon = item.icon
          const isActive = activeScreen === item.id
          return (
            <button
              key={item.id}
              type="button"
              {...(item.id === 'settings' ? { 'data-nav-settings': true } : {})}
              onClick={() => onScreenChange(item.id)}
              aria-current={isActive ? 'page' : undefined}
              title={open ? undefined : item.label}
              className={`rail-item ${isActive ? 'rail-item-active' : ''}`}
            >
              <Icon className="w-[17px] h-[17px] flex-shrink-0" strokeWidth={1.8} />
              <span
                className="text-[13px] whitespace-nowrap"
                style={{
                  ...labelStyle,
                  fontWeight: isActive ? 600 : 500,
                  letterSpacing: isActive ? '-0.01em' : undefined,
                  flex: item.id === 'advisor' ? (open ? 1 : '0 0 0px') : undefined,
                }}
              >
                {item.label}
              </span>
              {item.id === 'advisor' && advisorCount > 0 && (
                <span
                  className="flex-shrink-0 h-[18px] rounded-full bg-white text-ledger-accent-on text-[10px] font-extrabold flex items-center justify-center overflow-hidden tabular-nums"
                  style={{
                    ...labelStyle,
                    minWidth: open ? 18 : 0,
                    width: open ? undefined : 0,
                    padding: open ? '0 5px' : 0,
                  }}
                >
                  {advisorCount}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Linked institutions — pinned to the bottom of the rail */}
      <div className="mt-auto flex flex-col gap-[9px] pt-4 overflow-hidden">
        <div
          className="text-[9.5px] uppercase tracking-[0.16em] text-ledger-text-faintest whitespace-nowrap"
          style={labelStyle}
        >
          Linked
        </div>
        {institutions.length === 0 ? (
          <span className="text-[12px] text-ledger-text-faintest whitespace-nowrap" style={labelStyle}>
            No accounts
          </span>
        ) : (
          institutions.map(inst => (
            <div key={inst.itemId} className="flex items-center gap-[10px]" title={open ? undefined : inst.name}>
              <InstitutionAvatar name={inst.name} logo={inst.logo} color={inst.color} size={24} />
              <span
                className="text-[12px] text-ledger-text-secondary truncate whitespace-nowrap"
                style={labelStyle}
              >
                {inst.name}
              </span>
            </div>
          ))
        )}

        {onSignOut && (
          <button
            type="button"
            onClick={onSignOut}
            title={open ? undefined : 'Sign out'}
            className="rail-item mt-1"
          >
            <LogOut className="w-[17px] h-[17px] flex-shrink-0" strokeWidth={1.8} />
            <span className="text-[13px] font-medium whitespace-nowrap" style={labelStyle}>Sign out</span>
          </button>
        )}
      </div>
    </aside>
  )
}
