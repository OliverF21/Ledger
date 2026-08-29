import { useState, useEffect, useCallback } from 'react'
import Sidebar, { RAIL_TRANSITION } from './components/Sidebar'
import Header from './components/Header'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Transactions from './pages/Transactions'
import Spending from './pages/Spending'
import Budgets from './pages/Budgets'
import Goals from './pages/Goals'
import Investments from './pages/Investments'
import Trends from './pages/Trends'
import Settings from './pages/Settings'
import Advisor from './pages/Advisor'
import Setup from './pages/Setup'
import { useProposals } from './hooks/useAdvisor'
import { useAccounts } from './hooks/useAccounts'
import { useStartupSync } from './hooks/useSync'
import { apiFetchTimeout, getToken, clearToken } from './api/client'
import { LedgerLoader } from './components/ui/LedgerLoader'
import { VALID_SCREENS, type ScreenType } from './utils/screens'
import {
  getMonthOptions, resolveSelectedMonth, storeMonth, setMonthInUrl,
} from './utils/months'

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

function BootLoader() {
  return (
    <div className="relative z-10 min-h-dvh flex items-center justify-center">
      <LedgerLoader size="lg" />
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

/** Most screens are just their own name — no eyebrow, no tagline. Only
 *  Overview and Investments take the eyebrow/title pair, because the design
 *  specifies one for each (a date over a greeting; the section over "Your
 *  portfolio"). Inventing one for every other page only added noise. */
const screenHeaders: Record<ScreenType, HeaderInfo> = {
  overview:     { eyebrow: '',            title: greeting() },
  transactions: { eyebrow: '',            title: 'Transactions' },
  spending:     { eyebrow: '',            title: 'Cash Flow' },
  budgets:      { eyebrow: '',            title: 'Budgets' },
  goals:        { eyebrow: '',            title: 'Goals' },
  investments:  { eyebrow: 'Investments', title: 'Your portfolio' },
  trends:       { eyebrow: '',            title: 'Trends' },
  advisor:      { eyebrow: '',            title: 'AI Advisor' },
  settings:     { eyebrow: '',            title: 'Settings' },
}

/** "Thursday, 27 August" — the Overview eyebrow is the date, since the title
 *  beside it is already a greeting. */
function todayLabel(): string {
  return new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
}

/** Shared with Overview's month picker; kept in sync with the URL. */
const OVERVIEW_MONTH_KEY = 'ledger:overview-month-v2'

function getScreenFromHash(): ScreenType {
  const hash = window.location.hash.replace('#', '')
  if (hash === 'subscriptions') return 'budgets'
  const base = hash.split('/')[0]
  return VALID_SCREENS.includes(base as ScreenType) ? (base as ScreenType) : 'overview'
}

function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenType>(getScreenFromHash)
  const [railOpen, setRailOpen] = useState(false)
  // Month lives here rather than in Overview so the picker can sit in the
  // header cluster with Sync and the avatar, where the design puts it.
  const monthOptions = getMonthOptions(6)
  const [selectedMonth, setSelectedMonth] = useState<string>(() =>
    resolveSelectedMonth(OVERVIEW_MONTH_KEY, getMonthOptions(6)),
  )
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
    apiFetchTimeout('/api/auth/me')
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
    if (window.location.hash.replace('#', '') === 'subscriptions') {
      window.history.replaceState(null, '', '#budgets')
    }
    const onHashChange = () => {
      if (window.location.hash.replace('#', '') === 'subscriptions') {
        window.history.replaceState(null, '', '#budgets')
        setActiveScreen('budgets')
        return
      }
      setActiveScreen(getScreenFromHash())
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Check whether the first-run Plaid setup wizard still needs to run. Only
  // meaningful once authenticated; resets whenever we drop back out of auth.
  useEffect(() => {
    if (auth !== 'authenticated') { setSetupNeeded(null); return }
    apiFetchTimeout('/api/settings/plaid-config')
      .then(async r => {
        if (!r.ok) throw new Error('Failed to load Plaid config')
        return r.json()
      })
      .then(cfg => setSetupNeeded(!cfg.wizard_done && !cfg.configured))
      .catch(() => setSetupNeeded(false))
  }, [auth])

  const navigate = (screen: ScreenType) => {
    window.location.hash = screen
  }

  const selectMonth = (month: string) => {
    setSelectedMonth(month)
    storeMonth(OVERVIEW_MONTH_KEY, month)
    setMonthInUrl(month)
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
        return <Overview onNavigate={navigate} month={selectedMonth} />
      case 'transactions':
        return <Transactions />
      case 'spending':
        return <Spending />
      case 'budgets':
        return <Budgets />
      case 'goals':
        return <Goals />
      case 'investments':
        return <Investments />
      case 'trends':
        return <Trends />
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
            transition: `margin-left ${RAIL_TRANSITION}`,
          }}
        >
          <Header
            eyebrow={header.eyebrow}
            title={header.title}
            name={userName}
            controls={activeScreen === 'overview' ? (
              <label className="glass-control flex items-center gap-2 h-[34px] pl-[13px] pr-[9px] text-[12.5px] font-medium cursor-pointer">
                <span className="sr-only">Month</span>
                <select
                  value={selectedMonth}
                  onChange={e => selectMonth(e.target.value)}
                  className="bg-transparent border-none outline-none cursor-pointer text-white"
                >
                  {monthOptions.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
            ) : undefined}
          />

          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden soft-scrollbar mt-[14px] pl-[2px] pr-1 pb-5">
            {renderScreen()}
          </div>
        </main>
      </div>
    </>
  )
}

export default App
