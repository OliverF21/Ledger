import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { getToken, setToken } from './api/client'

// Dev-only fixture backend for design work — see src/dev/mockApi.ts. Both
// guards are static, so the import is tree-shaken out of production builds.
if (import.meta.env.DEV && import.meta.env.VITE_MOCK_API === '1') {
  const { installMockApi } = await import('./dev/mockApi')
  installMockApi()
  // Seed a session once per browser profile so the app opens straight onto the
  // dashboard — but don't re-seed after a sign-out, or the login screen would
  // be impossible to reach in demo mode.
  if (!getToken() && !localStorage.getItem('ledger_mock_seeded')) {
    localStorage.setItem('ledger_mock_seeded', '1')
    setToken('mock-session-token')
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
