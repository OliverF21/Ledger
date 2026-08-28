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
import { VALID_SCREENS, type ScreenType } from './utils/screens'

type AuthState = 'loading' | 'unauthenticated' | 'authenticated'

/** Fixed ambient background every screen sits on. Static by design — see the
 *  note in index.css. */
function Aurora() {
  return (
    <div className="aurora-root" aria-hidden>
      <div className="aurora-blob aurora-blob-blue" />
      <div className="aurora-blob aurora-blob-teal" />
      <div className="aurora-blob aurora-blob-warm" />
    </div>
  )
}

/** Rotating gradient ring shown during the initial token check (mirrors the
 *  login page's loading state). Kept inline to avoid a shared export. */
function BootLoader() {
  return (
    <div className="relative z-10 min-h-dvh flex flex-col items-center justify-center gap-4 text-ledger-text-primary">
      <div
        className="w-[92px] h-[92px] rounded-full"
        style={{
          animation: 'ledger-ring-spin 2.4s linear infinite',
          background: 'conic-gradient(from 0deg, #82a9f2, #63cfcc, #a196fa, #74d8a8, #e6bd79, #f4907f, #95c8ff, #82a9f2)',
          WebkitMask: 'radial-gradient(farthest-side, transparent calc(100% - 14px), #000 calc(100% - 13px))',
          mask: 'radial-gradient(farthest-side, transparent calc(100% - 14px), #000 calc(100% - 13px))',
        }}
      />
      <div className="text-[13px] text-ledger-text-faint">Loading…</div>
    </div>
  )
}

interface HeaderInfo {
  /** Uppercase micro-label above the page title. */
  eyebrow: string
  title: string
}

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good Morning'
  if (h < 17) return 'Good Afternoon'
  return 'Good Evening'
}

/** Eyebrow names the section, the title says what you're looking at — so the
 *  two never repeat the same word. */
const screenHeaders: Record<ScreenType, HeaderInfo> = {
  overview:     { eyebrow: 'Overview',      title: greeting() },
  transactions: { eyebrow: 'Transactions',  title: 'Every movement' },
  spending:     { eyebrow: 'Cash flow',     title: 'Money in, money out' },
  budgets:      { eyebrow: 'Budgets',       title: 'This month’s limits' },
  investments:  { eyebrow: 'Investments',   title: 'Your portfolio' },
  trends:       { eyebrow: 'Trends',        title: 'Patterns over time' },
  subscriptions:{ eyebrow: 'Subscriptions', title: 'Recurring charges' },
  advisor:      { eyebrow: 'AI advisor',    title: 'Suggestions to review' },
  settings:     { eyebrow: 'Settings',      title: 'Categories, rules & alerts' },
}

/** "Thursday, 27 August" — the Overview eyebrow is the date, not the section
 *  name, since the title beside it is already a greeting. */
function todayLabel(): string {
  return new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
}

function getScreenFromHash(): ScreenType {
  const hash = window.location.hash.replace('#', '') as ScreenType
  return VALID_SCREENS.includes(hash) ? hash : 'overview'
}

function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenType>(getScreenFromHash)
  const [railOpen, setRailOpen] = useState(false)
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
    ? { eyebrow: todayLabel(), title: userName ? `${greeting()}, ${userName}` : greeting() }
    : screenHeaders[activeScreen]

  if (auth === 'loading') {
    return (
      <>
        <Aurora />
        <BootLoader />
      </>
    )
  }

  if (auth === 'unauthenticated') {
    return (
      <>
        <Aurora />
        <Login onAuthenticated={loadMe} />
      </>
    )
  }

  if (auth === 'authenticated' && setupNeeded === null) {
    return (
      <>
        <Aurora />
        <BootLoader />
      </>
    )
  }

  if (auth === 'authenticated' && setupNeeded) {
    return (
      <>
        <Aurora />
        <Setup onDone={() => setSetupNeeded(false)} />
      </>
    )
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
    <>
      <Aurora />

      {/* The rail floats over the page (absolutely positioned inside this
          padding box) and `<main>` clears it with an animated left margin, so
          expanding the rail slides the content rather than reflowing it. */}
      <div className="relative z-10 h-dvh p-[14px] overflow-hidden text-ledger-text-primary">
        <Sidebar
          activeScreen={activeScreen}
          onScreenChange={navigate}
          onSignOut={signOut}
          advisorCount={advisor.pendingCount}
          accounts={linkedAccounts.accounts}
          open={railOpen}
          onOpenChange={setRailOpen}
        />

        <main
          className="relative z-10 h-full flex flex-col min-w-0"
          style={{
            marginLeft: railOpen ? 234 : 86,
            transition: 'margin-left .28s cubic-bezier(.22,.8,.2,1)',
          }}
        >
          <Header eyebrow={header.eyebrow} title={header.title} name={userName} />

          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden soft-scrollbar mt-[14px] pl-[2px] pr-1 pb-5">
            {renderScreen()}
          </div>
        </main>
      </div>
    </>
  )
}

export default App
