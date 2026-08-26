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

const ACCOUNT_GROUPS: { key: string; label: string; match: (a: AccountItem) => boolean; liability: boolean }[] = [
  { key: 'cash', label: 'Cash', match: a => a.type === 'depository', liability: false },
  { key: 'credit', label: 'Credit cards', match: a => a.type === 'credit', liability: true },
  { key: 'investments', label: 'Investments', match: a => a.type === 'investment', liability: false },
  { key: 'loans', label: 'Loans', match: a => a.type === 'loan', liability: true },
]

function fmtBal(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function Sidebar({ activeScreen, onScreenChange, onSignOut, advisorCount = 0, accounts }: SidebarProps) {
  const grouped = ACCOUNT_GROUPS
    .map(group => ({
      ...group,
      items: accounts.filter(group.match),
    }))
    .filter(group => group.items.length > 0)

  const leftover = accounts.filter(a => !ACCOUNT_GROUPS.some(g => g.match(a)))
  if (leftover.length > 0) {
    grouped.push({ key: 'other', label: 'Other', match: () => false, liability: false, items: leftover })
  }

  return (
    <aside className="w-[232px] flex-shrink-0 glass-sidebar px-3 py-4 flex flex-col h-full min-h-0 overflow-hidden">
      <div className="flex items-center gap-2 px-2 pb-4">
        <BookOpen className="w-[18px] h-[18px] text-ledger-accent" strokeWidth={2.2} />
        <span className="font-semibold text-[15px] tracking-tight">Ledger</span>
      </div>

      <nav className="flex flex-col gap-[2px] min-h-0 overflow-y-auto soft-scrollbar">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = activeScreen === item.id
          return (
            <button
              key={item.id}
              {...(item.id === 'settings' ? { 'data-nav-settings': true } : {})}
              onClick={() => onScreenChange(item.id)}
              className={`flex items-center gap-2.5 px-2.5 py-[7px] rounded-[8px] text-[13px] ${
                isActive
                  ? 'bg-ledger-active text-ledger-text-heading font-semibold'
                  : 'text-ledger-text-muted font-medium hover:bg-ledger-hover hover:text-ledger-text-secondary'
              }`}
            >
              <Icon
                className="w-4 h-4 flex-shrink-0"
                style={isActive ? { color: '#4d8dff' } : undefined}
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

      <div className="mt-auto pt-3 min-h-0 flex flex-col">
        <div className="px-2.5 pb-2 text-[11px] font-medium text-ledger-text-faint">
          Accounts
        </div>
        <div className="flex flex-col gap-3 min-h-0 overflow-y-auto soft-scrollbar px-2.5 pb-2">
          {grouped.length === 0 ? (
            <div className="text-[11px] text-ledger-text-faintest">No accounts linked</div>
          ) : (
            grouped.map(group => {
              const total = group.items.reduce((sum, a) => sum + a.current_balance, 0)
              return (
                <div key={group.key}>
                  <div className="flex items-baseline justify-between gap-2 mb-1">
                    <span className="text-[11px] text-ledger-text-faint">{group.label}</span>
                    <span className={`text-[11px] tabular-nums ${group.liability ? 'text-ledger-negative' : 'text-ledger-text-muted'}`}>
                      {group.liability ? '−' : ''}${fmtBal(total)}
                    </span>
                  </div>
                  <div className="flex flex-col gap-[5px]">
                    {group.items.map(acc => (
                      <div key={acc.id} className="flex items-center gap-[7px] min-w-0">
                        <InstitutionAvatar
                          name={acc.institution_name || acc.name}
                          logo={acc.institution_logo ?? null}
                          color={acc.institution_color ?? null}
                          size={16}
                        />
                        <span className="text-[11.5px] text-ledger-text-secondary truncate flex-1 min-w-0">
                          {acc.name}
                        </span>
                        <span className={`text-[11px] tabular-nums flex-shrink-0 ${group.liability ? 'text-ledger-negative' : 'text-ledger-text-primary'}`}>
                          {group.liability ? '−' : ''}${fmtBal(acc.current_balance)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {onSignOut && (
          <button
            onClick={onSignOut}
            className="mt-1 w-full flex items-center gap-2.5 px-2.5 py-[7px] rounded-[8px] text-[13px] text-ledger-text-muted font-medium hover:bg-ledger-hover hover:text-ledger-text-secondary"
          >
            <LogOut className="w-4 h-4 flex-shrink-0" strokeWidth={2} />
            <span>Sign out</span>
          </button>
        )}
      </div>
    </aside>
  )
}
