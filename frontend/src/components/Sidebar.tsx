import {
  LayoutGrid, AlignLeft, ArrowLeftRight, PieChart, BarChart3,
  TrendingUp, Sparkles, SlidersHorizontal, LogOut, Target,
} from 'lucide-react'
import { type AccountItem } from '../hooks/useAccounts'
import { type ScreenType } from '../utils/screens'

/** Rail width / main-margin easing. Kept here and imported by App so the two
 *  never drift — if they disagree the content visibly lags the rail. The
 *  original 0.28s read as a snap at this travel distance (148px); 0.44s on a
 *  gentler curve lets the eye follow it. */
export const RAIL_TRANSITION = '.44s cubic-bezier(.32,.72,.24,1)'
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
  { id: 'goals', label: 'Goals', icon: Target },
  { id: 'trends', label: 'Trends', icon: TrendingUp },
  { id: 'advisor', label: 'AI Advisor', icon: Sparkles },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal },
]

/** Icon column width. Equals the collapsed rail's inner width
 *  (66px − 2px border − 24px px-3) so marks sit on the centerline when
 *  closed and don't shift when the rail opens. */
const ICON_COL = 'w-10 shrink-0 flex items-center justify-center'

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
    // Fading in waits for the rail to have room; fading out leads it, so text
    // never gets clipped by the closing edge.
    transition: open ? 'opacity .26s ease .14s' : 'opacity .12s ease',
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
        transition: `width ${RAIL_TRANSITION}`,
      }}
    >
      {/* Logo */}
      <div className="flex items-center pt-[3px] pb-5 overflow-hidden">
        <div className={ICON_COL}>
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
              <span className={ICON_COL}>
                <Icon className="w-[17px] h-[17px] flex-shrink-0" strokeWidth={1.8} />
              </span>
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
            <div key={inst.itemId} className="flex items-center" title={open ? undefined : inst.name}>
              <div className={ICON_COL}>
                <InstitutionAvatar name={inst.name} logo={inst.logo} color={inst.color} size={24} />
              </div>
              <span
                className="min-w-0 text-[12px] text-ledger-text-secondary truncate whitespace-nowrap"
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
            <span className={ICON_COL}>
              <LogOut className="w-[17px] h-[17px] flex-shrink-0" strokeWidth={1.8} />
            </span>
            <span className="text-[13px] font-medium whitespace-nowrap" style={labelStyle}>Sign out</span>
          </button>
        )}
      </div>
    </aside>
  )
}
