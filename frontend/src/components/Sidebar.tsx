import { Grid3x3, List, Workflow, BarChart3, PieChart, TrendingUp, Repeat, Sparkles, Settings, BookOpen, LogOut } from 'lucide-react'
import { type AccountItem } from '../hooks/useAccounts'
import InstitutionAvatar from './InstitutionAvatar'

interface SidebarProps {
  activeScreen: string
  onScreenChange: (screen: any) => void
  onSignOut?: () => void
  advisorCount?: number
  accounts: AccountItem[]
}

const navItems = [
  { id: 'overview', label: 'Overview', icon: Grid3x3 },
  { id: 'transactions', label: 'Transactions', icon: List },
  { id: 'spending', label: 'Cash Flow', icon: Workflow },
  { id: 'investments', label: 'Investments', icon: PieChart },
  { id: 'budgets', label: 'Budgets', icon: BarChart3 },
  { id: 'trends', label: 'Trends', icon: TrendingUp },
  { id: 'subscriptions', label: 'Subscriptions', icon: Repeat },
  { id: 'advisor', label: 'AI Advisor', icon: Sparkles },
  { id: 'settings', label: 'Settings', icon: Settings },
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

export default function Sidebar({ activeScreen, onScreenChange, onSignOut, advisorCount = 0, accounts }: SidebarProps) {
  const institutions = groupByItem(accounts)

  return (
    <aside className="w-[232px] flex-shrink-0 glass-sidebar px-4 py-[22px] short:py-4 flex flex-col h-full min-h-0 overflow-hidden">
      {/* Logo */}
      <div className="flex items-center gap-2.5 pb-[18px]">
        <div className="w-[26px] h-[26px] rounded-lg bg-ledger-accent flex items-center justify-center">
          <BookOpen className="w-[14px] h-[14px] text-ledger-accent-on" strokeWidth={2.25} />
        </div>
        <span className="font-bold text-base tracking-tighter">Ledger</span>
      </div>

      {/* Navigation — anchored near the top of the sidebar */}
      <nav className="flex flex-col gap-[6px] pt-[4px] min-h-0 overflow-y-auto soft-scrollbar">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = activeScreen === item.id
          return (
            <button
              key={item.id}
              {...(item.id === 'settings' ? { 'data-nav-settings': true } : {})}
              onClick={() => onScreenChange(item.id)}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm relative transition-all ${
                isActive
                  ? 'bg-ledger-inset text-ledger-text-heading font-semibold'
                  : 'text-ledger-text-muted font-medium hover:bg-[#121519] hover:text-[#cfd3da]'
              }`}
            >
              {isActive && (
                <div className="absolute -left-4 top-2 bottom-2 w-1 bg-ledger-accent rounded-r" />
              )}
              <Icon
                className="w-[17px] h-[17px] flex-shrink-0"
                style={isActive ? { color: '#5b8def' } : undefined}
                strokeWidth={2}
              />
              <span>{item.label}</span>
              {item.id === 'advisor' && advisorCount > 0 && (
                <span className="ml-auto min-w-[18px] h-[18px] px-[5px] rounded-full bg-ledger-accent text-ledger-accent-on text-[10px] font-bold flex items-center justify-center tabular-nums">
                  {advisorCount}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      <div className="mt-auto pt-[18px]">
        <div className="glass-card px-[14px] py-[12px]">
          <div className="text-[10px] uppercase tracking-widest text-ledger-text-faintest mb-[10px]">
            Linked accounts
          </div>
          <div className="flex flex-col gap-[8px]">
            {institutions.length === 0 ? (
              <div className="text-[11px] text-ledger-text-faintest">No accounts linked</div>
            ) : (
              institutions.map(inst => (
                <div key={inst.itemId} className="flex items-center gap-[9px]">
                  <InstitutionAvatar
                    name={inst.name}
                    logo={inst.logo}
                    color={inst.color}
                    size={22}
                  />
                  <span className="text-[12px] text-ledger-text-secondary truncate">{inst.name}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {onSignOut && (
          <button
            onClick={onSignOut}
            className="mt-[10px] w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-ledger-text-muted font-medium hover:bg-[#121519] hover:text-[#cfd3da] transition-all"
          >
            <LogOut className="w-[17px] h-[17px] flex-shrink-0" strokeWidth={2} />
            <span>Sign out</span>
          </button>
        )}
      </div>
    </aside>
  )
}
