import { useState, useEffect, useCallback } from 'react'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Transactions from './pages/Transactions'
import Spending from './pages/Spending'
import Budgets from './pages/Budgets'
import Investments from './pages/Investments'
import Trends from './pages/Trends'
import Subscriptions from './pages/Subscriptions'
import Settings from './pages/Settings'
import Advisor from './pages/Advisor'
import Setup from './pages/Setup'
import { useProposals } from './hooks/useAdvisor'
import { useAccounts } from './hooks/useAccounts'
import { useStartupSync } from './hooks/useSync'
import { apiFetch, getToken, clearToken } from './api/client'
import { getPlaidConfig } from './api/plaidConfig'

type AuthState = 'loading' | 'unauthenticated' | 'authenticated'

/** Minimal spinner shown during the initial token check. */
function BootLoader() {
  return (
    <div className="min-h-dvh flex flex-col items-center justify-center gap-3 bg-ledger-bg text-ledger-text-primary">
      <div
        className="w-8 h-8 rounded-full"
        style={{
          animation: 'ledger-ring-spin 0.9s linear infinite',
          border: '2px solid rgba(77,141,255,0.22)',
          borderTopColor: '#4d8dff',
        }}
      />
      <div className="text-[13px] text-ledger-text-faint">Loading…</div>
    </div>
  )
}

type ScreenType = 'overview' | 'transactions' | 'spending' | 'budgets' | 'investments' | 'trends' | 'subscriptions' | 'advisor' | 'settings'

interface HeaderInfo {
  title: string
  subtitle: string
}

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good Morning'
  if (h < 17) return 'Good Afternoon'
  return 'Good Evening'
}

const screenHeaders: Record<ScreenType, HeaderInfo> = {
  overview:     { title: greeting(),        subtitle: '' },
  transactions: { title: 'Transactions',    subtitle: '' },
  spending:     { title: 'Cash Flow',       subtitle: '' },
  budgets:      { title: 'Budgets',         subtitle: '' },
  investments:  { title: 'Investments',     subtitle: 'Portfolio holdings & activity' },
  trends:       { title: 'Trends',          subtitle: 'Spending patterns over time' },
  subscriptions:{ title: 'Subscriptions',   subtitle: 'Detected recurring charges' },
  advisor:      { title: 'AI Advisor',      subtitle: 'Review & apply Claude’s suggestions' },
  settings:     { title: 'Settings',        subtitle: 'Manage categories, rules & alerts' },
}

const VALID_SCREENS: ScreenType[] = ['overview', 'transactions', 'spending', 'budgets', 'investments', 'trends', 'subscriptions', 'advisor', 'settings']

function getScreenFromHash(): ScreenType {
  const hash = window.location.hash.replace('#', '') as ScreenType
  return VALID_SCREENS.includes(hash) ? hash : 'overview'
}

function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenType>(getScreenFromHash)
  const [auth, setAuth] = useState<AuthState>('loading')
  const [userName, setUserName] = useState('')
  const [setupNeeded, setSetupNeeded] = useState<boolean | null>(null)

  // Pending AI advisor proposals — lifted so the sidebar badge and the Advisor
  // page share one fetch/poll. Only polls once authenticated.
  const advisor = useProposals(auth === 'authenticated')
  const linkedAccounts = useAccounts(auth === 'authenticated')

  // Pull latest transactions from Plaid once per session when the main app loads.
  useStartupSync(auth === 'authenticated' && setupNeeded === false)

  // Fetch the current user's display name; sets auth based on token validity.
  const loadMe = useCallback(() => {
    apiFetch('/api/auth/me')
      .then(async r => {
        if (!r.ok) { setAuth('unauthenticated'); return }
        const data = await r.json().catch(() => ({}))
        setUserName(data.name || '')
        setAuth('authenticated')
      })
      .catch(() => setAuth('unauthenticated'))
  }, [])

  // Validate any stored token on boot; 401 clears it.
  useEffect(() => {
    if (!getToken()) { setAuth('unauthenticated'); return }
    loadMe()
  }, [loadMe])

  // apiFetch dispatches this when any call 401s (expired session).
  useEffect(() => {
    const onUnauth = () => setAuth('unauthenticated')
    window.addEventListener('ledger:unauthorized', onUnauth)
    return () => window.removeEventListener('ledger:unauthorized', onUnauth)
  }, [])

  useEffect(() => {
    const onHashChange = () => setActiveScreen(getScreenFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Check whether the first-run Plaid setup wizard still needs to run. Only
  // meaningful once authenticated; resets whenever we drop back out of auth.
  useEffect(() => {
    if (auth !== 'authenticated') { setSetupNeeded(null); return }
    getPlaidConfig()
      .then(cfg => setSetupNeeded(!cfg.wizard_done && !cfg.configured))
      .catch(() => setSetupNeeded(false))
  }, [auth])

  const navigate = (screen: ScreenType) => {
    window.location.hash = screen
  }

  const signOut = () => {
    clearToken()
    setAuth('unauthenticated')
  }

  // Personalize the homepage greeting with the user's name when we have one.
  const header = activeScreen === 'overview'
    ? { title: userName ? `${greeting()}, ${userName}` : greeting(), subtitle: '' }
    : screenHeaders[activeScreen]

  if (auth === 'loading') {
    return <BootLoader />
  }

  if (auth === 'unauthenticated') {
    return <Login onAuthenticated={loadMe} />
  }

  if (auth === 'authenticated' && setupNeeded === null) {
    return <BootLoader />
  }

  if (auth === 'authenticated' && setupNeeded) {
    return <Setup onDone={() => setSetupNeeded(false)} />
  }

  const renderScreen = () => {
    switch (activeScreen) {
      case 'overview':
        return <Overview onNavigate={navigate} />
      case 'transactions':
        return <Transactions />
      case 'spending':
        return <Spending />
      case 'budgets':
        return <Budgets />
      case 'investments':
        return <Investments />
      case 'trends':
        return <Trends />
      case 'subscriptions':
        return <Subscriptions />
      case 'advisor':
        return <Advisor advisor={advisor} />
      case 'settings':
        return (
          <Settings
            accounts={linkedAccounts.accounts}
            loadingAccounts={linkedAccounts.loading}
            onAccountsChange={linkedAccounts.refetch}
          />
        )
    }
  }

  return (
    <div className="h-dvh flex bg-ledger-bg text-ledger-text-primary overflow-hidden">
      <Sidebar
        activeScreen={activeScreen}
        onScreenChange={navigate}
        onSignOut={signOut}
        advisorCount={advisor.pendingCount}
        accounts={linkedAccounts.accounts}
      />

      <main className="flex-1 flex flex-col min-h-0 min-w-0 glass-shell overflow-hidden">
        <Header title={header.title} subtitle={header.subtitle} name={userName} />

        <div className="flex-1 min-h-0 overflow-auto px-6 py-5 soft-scrollbar">
          {renderScreen()}
        </div>
      </main>
    </div>
  )
}

export default App
