import { useState, useEffect, useCallback } from 'react'
import { apiFetch, setToken } from '../api/client'
import { alphaColor } from '../utils/color'

// The pie-chart Transportation blue (#5b8def). Rendered as a large glow that
// diffuses outward from behind the liquid-glass card, not a tint on the card.
const BLUE = '#5b8def'

/** Minimal ring spinner for the "checking" state (no donut chart). */
function Spinner() {
  return (
    <div
      className="w-[34px] h-[34px] rounded-full"
      style={{
        animation: 'ledger-ring-spin 0.9s linear infinite',
        border: `2px solid ${alphaColor(BLUE, 0.25)}`,
        borderTopColor: BLUE,
      }}
    />
  )
}

interface SetupStatus {
  account_exists: boolean
  plaid_env: string
  plaid_ok: boolean
  missing_plaid_vars: string[]
}

type Phase = 'checking' | 'blocked' | 'setup' | 'login' | 'reset' | 'reveal-code'

export default function Login({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [phase, setPhase] = useState<Phase>('checking')
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // "Forgot password?" — reset via one-time recovery code (no email transport
  // for a single-user local app).
  const [recoveryCode, setRecoveryCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  // Shown exactly once after register/reset, before entering the app.
  const [revealedCode, setRevealedCode] = useState<string | null>(null)
  const [pendingToken, setPendingToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const check = useCallback(() => {
    setPhase('checking')
    setError(null)
    apiFetch('/api/setup/status')
      .then(r => r.json())
      .then((s: SetupStatus) => {
        // Missing Plaid keys no longer block the app — they're configured in the
        // first-run wizard / Settings (BYOK). 'blocked' now means only that the
        // backend is unreachable (see .catch below).
        setPhase(s.account_exists ? 'login' : 'setup')
      })
      .catch(() => {
        setError('Could not reach the backend. Is it running?')
        setPhase('blocked')
      })
  }, [])

  useEffect(() => { check() }, [check])

  const submit = async () => {
    setError(null)
    if (phase === 'setup') {
      if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
      if (password !== confirm) { setError('Passwords do not match.'); return }
    }
    setSubmitting(true)
    try {
      const endpoint = phase === 'setup' ? '/api/auth/register' : '/api/auth/login'
      const body = phase === 'setup'
        ? { username, password, name: name.trim() }
        : { username, password }
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.detail || 'Something went wrong. Try again.')
        setSubmitting(false)
        return
      }
      // Registration issues a one-time recovery code — hold the token and show
      // it before entering the app. Login never returns one.
      if (data.recovery_code) {
        setPendingToken(data.token)
        setRevealedCode(data.recovery_code)
        setPhase('reveal-code')
        setSubmitting(false)
        return
      }
      setToken(data.token)
      onAuthenticated()
    } catch {
      setError('Could not reach the backend. Is it running?')
      setSubmitting(false)
    }
  }

  const submitReset = async () => {
    setError(null)
    if (newPassword.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (newPassword !== confirmNewPassword) { setError('Passwords do not match.'); return }
    setSubmitting(true)
    try {
      const res = await apiFetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recovery_code: recoveryCode, new_password: newPassword }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.detail || 'Could not reset the password. Check your recovery code.')
        setSubmitting(false)
        return
      }
      setPendingToken(data.token)
      setRevealedCode(data.recovery_code)
      setPhase('reveal-code')
      setSubmitting(false)
    } catch {
      setError('Could not reach the backend. Is it running?')
      setSubmitting(false)
    }
  }

  const copyCode = async () => {
    if (!revealedCode) return
    try {
      await navigator.clipboard.writeText(revealedCode)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable — ignore */
    }
  }

  const continueFromReveal = () => {
    if (pendingToken) setToken(pendingToken)
    onAuthenticated()
  }

  return (
    <div className="relative z-10 min-h-dvh flex items-center justify-center p-4 text-ledger-text-primary">
      {/* Large blue gradient diffusing outward from behind the glass card */}
      <div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
        style={{
          width: 900,
          height: 760,
          filter: 'blur(80px)',
          background: `radial-gradient(circle at 50% 46%, ${alphaColor(BLUE, 0.55)} 0%, ${alphaColor(BLUE, 0.30)} 28%, ${alphaColor(BLUE, 0.12)} 52%, ${alphaColor(BLUE, 0.04)} 68%, transparent 80%)`,
        }}
      />

      <div
        className="glass-modal w-[400px] max-w-full px-[36px] py-[40px] flex flex-col items-center relative overflow-hidden"
        style={{
          // Translucent frosted fill (overrides glass-modal's near-opaque dark
          // one) so the blue glow behind shows through the backdrop blur.
          background: 'linear-gradient(150deg, rgba(255,255,255,0.16), rgba(255,255,255,0.05) 46%, rgba(255,255,255,0.10))',
        }}
      >
        {phase === 'checking' ? (
          <div className="relative flex flex-col items-center gap-[16px] py-[20px]">
            <Spinner />
            <div className="text-[13px] text-ledger-text-faint">Loading…</div>
          </div>
        ) : (
          <div className="relative w-full flex flex-col items-center">
            <div className="text-[26px] font-bold tracking-tight">Ledger</div>
            <div className="text-[13px] text-ledger-text-faint mb-[24px]">
              {phase === 'blocked' ? 'Connection problem'
                : phase === 'setup' ? 'Create your account'
                : phase === 'reset' ? 'Reset your password'
                : phase === 'reveal-code' ? 'Save your recovery code'
                : 'Welcome back'}
            </div>

            {/* Blocked: the backend could not be reached */}
            {phase === 'blocked' && (
              <div className="w-full">
                <div className="text-[13px] text-ledger-text-secondary mb-[18px]">
                  {error ?? 'Could not reach the backend. Is it running?'}
                </div>
                <button
                  onClick={check}
                  className="w-full py-[11px] rounded-[10px] bg-ledger-accent text-ledger-accent-on text-[13px] font-semibold hover:opacity-90 transition-opacity"
                >
                  Re-check
                </button>
              </div>
            )}

            {/* Setup / login form */}
            {(phase === 'setup' || phase === 'login') && (
              <form
                className="w-full flex flex-col gap-[12px]"
                onSubmit={e => { e.preventDefault(); if (!submitting) submit() }}
              >
                {phase === 'setup' && (
                  <input
                    autoFocus
                    type="text"
                    placeholder="Your name"
                    autoComplete="name"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    className="glass-chip px-[14px] py-[11px] text-[14px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                  />
                )}
                <input
                  autoFocus={phase === 'login'}
                  type="text"
                  placeholder="Username"
                  autoComplete="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className="glass-chip px-[14px] py-[11px] text-[14px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                />
                <input
                  type="password"
                  placeholder="Password"
                  autoComplete={phase === 'setup' ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="glass-chip px-[14px] py-[11px] text-[14px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                />
                {phase === 'setup' && (
                  <input
                    type="password"
                    placeholder="Confirm password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    className="glass-chip px-[14px] py-[11px] text-[14px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                  />
                )}

                {error && <div className="text-[12.5px] text-ledger-negative">{error}</div>}

                <button
                  type="submit"
                  disabled={submitting || !username || !password}
                  className="mt-[4px] w-full py-[11px] rounded-[10px] bg-ledger-accent text-ledger-accent-on text-[13px] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
                >
                  {submitting ? 'Please wait…' : phase === 'setup' ? 'Create account' : 'Sign in'}
                </button>

                {phase === 'setup' && (
                  <div className="text-[11.5px] text-ledger-text-faintest text-center mt-[2px]">
                    This is a single-user app. Your account secures this dashboard.
                  </div>
                )}

                {phase === 'login' && (
                  <button
                    type="button"
                    onClick={() => { setError(null); setRecoveryCode(''); setNewPassword(''); setConfirmNewPassword(''); setPhase('reset') }}
                    className="text-[12px] text-ledger-text-faint hover:text-ledger-accent transition-colors mt-[2px]"
                  >
                    Forgot password?
                  </button>
                )}
              </form>
            )}

            {/* Reset via recovery code */}
            {phase === 'reset' && (
              <form
                className="w-full flex flex-col gap-[12px]"
                onSubmit={e => { e.preventDefault(); if (!submitting) submitReset() }}
              >
                <div className="text-[12px] text-ledger-text-faint leading-[1.5] mb-[2px]">
                  Enter the recovery code you saved when you created this account.
                </div>
                <input
                  autoFocus
                  type="text"
                  placeholder="Recovery code (XXXX-XXXX-XXXX)"
                  autoComplete="off"
                  value={recoveryCode}
                  onChange={e => setRecoveryCode(e.target.value)}
                  className="glass-chip px-[14px] py-[11px] text-[14px] font-mono text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                />
                <input
                  type="password"
                  placeholder="New password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  className="glass-chip px-[14px] py-[11px] text-[14px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                />
                <input
                  type="password"
                  placeholder="Confirm new password"
                  autoComplete="new-password"
                  value={confirmNewPassword}
                  onChange={e => setConfirmNewPassword(e.target.value)}
                  className="glass-chip px-[14px] py-[11px] text-[14px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                />

                {error && <div className="text-[12.5px] text-ledger-negative">{error}</div>}

                <button
                  type="submit"
                  disabled={submitting || !recoveryCode || !newPassword}
                  className="mt-[4px] w-full py-[11px] rounded-[10px] bg-ledger-accent text-ledger-accent-on text-[13px] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
                >
                  {submitting ? 'Please wait…' : 'Reset password'}
                </button>

                <button
                  type="button"
                  onClick={() => { setError(null); setPhase('login') }}
                  className="text-[12px] text-ledger-text-faint hover:text-ledger-accent transition-colors"
                >
                  Back to sign in
                </button>

                <div className="text-[11.5px] text-ledger-text-faintest text-center mt-[2px]">
                  No recovery code? There's no email-based recovery for this local app —
                  the only fallback is wiping the app's local data and starting over.
                </div>
              </form>
            )}

            {/* One-time reveal: shown after register or a successful reset */}
            {phase === 'reveal-code' && revealedCode && (
              <div className="w-full flex flex-col gap-[14px]">
                <div className="text-[12.5px] text-ledger-text-secondary leading-[1.5]">
                  This is the <span className="text-ledger-text-primary font-semibold">only</span> way
                  to reset your password without wiping your data. Save it somewhere safe —
                  it won't be shown again.
                </div>
                <div className="flex items-center gap-[8px]">
                  <code className="glass-chip rounded-[9px] px-[14px] py-[12px] text-[16px] font-mono tracking-wide text-ledger-text-primary flex-1 text-center">
                    {revealedCode}
                  </code>
                  <button
                    onClick={copyCode}
                    className="glass-chip rounded-[9px] px-[12px] py-[12px] text-[12px] text-ledger-text-secondary hover:text-ledger-accent transition-colors"
                  >
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <button
                  onClick={continueFromReveal}
                  className="w-full py-[11px] rounded-[10px] bg-ledger-accent text-ledger-accent-on text-[13px] font-semibold hover:opacity-90 transition-opacity"
                >
                  I've saved it — Continue
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
