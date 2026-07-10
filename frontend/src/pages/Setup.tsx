import { useEffect, useState } from 'react'
import { putPlaidConfig, testPlaidConfig, markWizardDone, importData } from '../api/plaidConfig'
import { alphaColor } from '../utils/color'

// The same Transportation blue used behind the Login card.
const BLUE = '#5b8def'

type Step = 'welcome' | 'plaid' | 'import'

export default function Setup({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<Step>(window.location.hash === '#import' ? 'import' : 'welcome')

  const [sourceDir, setSourceDir] = useState('')
  const [confirmOverwrite, setConfirmOverwrite] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<{ imported_items: number; restart_required: boolean } | null>(null)

  useEffect(() => {
    const onHashChange = () => {
      if (window.location.hash === '#import') setStep('import')
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const handleImport = async () => {
    setImporting(true)
    setImportError(null)
    setImportResult(null)
    try {
      const result = await importData(sourceDir.trim(), confirmOverwrite)
      setImportResult(result)
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  const [clientId, setClientId] = useState('')
  const [env, setEnv] = useState('sandbox')
  const [secret, setSecret] = useState('')

  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [testOk, setTestOk] = useState<boolean | null>(null)

  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [skipping, setSkipping] = useState(false)

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    setTestOk(null)
    try {
      const result = await testPlaidConfig({
        client_id: clientId.trim() || undefined,
        env,
        secret: secret.trim() || undefined,
      })
      setTestOk(result.ok)
      setTestResult(result.message)
    } catch (error) {
      setTestOk(false)
      setTestResult(error instanceof Error ? error.message : 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleFinish = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const body: { client_id: string; env: string; secret?: string } = {
        client_id: clientId.trim(),
        env,
      }
      if (secret.trim()) {
        body.secret = secret.trim()
      }
      await putPlaidConfig(body)
      await markWizardDone()
      onDone()
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Failed to save')
      setSaving(false)
    }
  }

  const handleSkip = async () => {
    setSkipping(true)
    try {
      await markWizardDone()
    } catch {
      // Even if this fails, don't block the user from reaching the dashboard.
    } finally {
      onDone()
    }
  }

  return (
    <div className="relative z-10 min-h-dvh flex items-center justify-center p-4 text-ledger-text-primary">
      {/* Large blue gradient diffusing outward from behind the glass card, matching Login. */}
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
        className="glass-modal w-[440px] max-w-full px-[36px] py-[40px] flex flex-col items-center relative overflow-hidden"
        style={{
          background: 'linear-gradient(150deg, rgba(255,255,255,0.16), rgba(255,255,255,0.05) 46%, rgba(255,255,255,0.10))',
        }}
      >
        {step === 'import' ? (
          <div className="relative w-full flex flex-col items-center">
            <div className="text-[22px] font-bold tracking-tight">Import existing data</div>
            <div className="text-[13px] text-ledger-text-faint mb-[22px] text-center">
              Point to a previous Ledger install's <code>backend</code> folder to bring over your
              accounts and Plaid configuration.
            </div>

            {importResult ? (
              <div className="w-full space-y-[12px] text-center">
                <p className="text-[13px] text-ledger-positive">
                  Imported {importResult.imported_items} linked account{importResult.imported_items === 1 ? '' : 's'}.
                  Please restart Ledger to finish.
                </p>
                <button
                  onClick={() => { window.location.hash = ''; setStep('welcome') }}
                  className="w-full glass-chip rounded-[9px] py-[9px] text-[13px] font-semibold text-ledger-text-primary hover:bg-[#161a21] transition-colors"
                >
                  Back to Welcome
                </button>
              </div>
            ) : (
              <div className="w-full space-y-[12px]">
                <div>
                  <label className="text-[12px] text-ledger-text-faint">Source folder</label>
                  <input
                    type="text"
                    value={sourceDir}
                    onChange={e => setSourceDir(e.target.value)}
                    placeholder="/path/to/old/ledger/backend"
                    className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                </div>

                <label className="flex items-center gap-[8px] text-[12px] text-ledger-text-faint select-none">
                  <input
                    type="checkbox"
                    checked={confirmOverwrite}
                    onChange={e => setConfirmOverwrite(e.target.checked)}
                    className="accent-ledger-accent"
                  />
                  Overwrite existing data
                </label>

                {importError && <p className="text-[11.5px] text-ledger-negative">{importError}</p>}

                <button
                  onClick={handleImport}
                  disabled={importing || !sourceDir.trim()}
                  className="w-full bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] text-[13px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {importing ? 'Importing…' : 'Import'}
                </button>

                <button
                  onClick={() => { window.location.hash = ''; setStep('welcome') }}
                  className="w-full text-[12px] text-ledger-text-faint hover:text-ledger-text-secondary transition-colors underline"
                >
                  Back
                </button>
              </div>
            )}
          </div>
        ) : step === 'welcome' ? (
          <div className="relative w-full flex flex-col items-center text-center">
            <div className="text-[26px] font-bold tracking-tight">Welcome to Ledger</div>
            <div className="text-[13px] text-ledger-text-secondary mt-[10px] mb-[28px] leading-relaxed">
              Ledger runs entirely on your computer. Your data stays local, and nothing
              is sent anywhere except directly to Plaid when you choose to connect a
              bank account.
            </div>

            <button
              onClick={() => setStep('plaid')}
              className="w-full py-[11px] rounded-[10px] bg-ledger-accent text-ledger-accent-on text-[13px] font-semibold hover:opacity-90 transition-opacity"
            >
              Get started
            </button>

            <button
              onClick={() => { window.location.hash = 'import' }}
              className="mt-[16px] text-[12px] text-ledger-text-faint hover:text-ledger-text-secondary transition-colors underline"
            >
              Already have a Ledger install? Import your data
            </button>
          </div>
        ) : (
          <div className="relative w-full flex flex-col items-center">
            <div className="text-[22px] font-bold tracking-tight">Connect Plaid</div>
            <div className="text-[13px] text-ledger-text-faint mb-[22px] text-center">
              Optional — add your Plaid keys now, or skip and add them later in Settings.
            </div>

            <div className="w-full space-y-[12px]">
              <div>
                <label className="text-[12px] text-ledger-text-faint">Client ID</label>
                <input
                  type="text"
                  value={clientId}
                  onChange={e => setClientId(e.target.value)}
                  placeholder="Plaid client ID"
                  className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                />
              </div>

              <div>
                <label className="text-[12px] text-ledger-text-faint">Environment</label>
                <select
                  value={env}
                  onChange={e => setEnv(e.target.value)}
                  className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary focus:outline-none focus:border-ledger-accent/60"
                >
                  <option value="sandbox">Sandbox</option>
                  <option value="production">Production</option>
                </select>
              </div>

              <div>
                <label className="text-[12px] text-ledger-text-faint">Secret</label>
                <input
                  type="password"
                  value={secret}
                  onChange={e => setSecret(e.target.value)}
                  placeholder="Plaid secret"
                  className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                />
              </div>

              {testResult && (
                <p className={`text-[11.5px] ${testOk ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
                  {testResult}
                </p>
              )}
              {saveError && <p className="text-[11.5px] text-ledger-negative">{saveError}</p>}

              <button
                onClick={handleTest}
                disabled={testing}
                className="w-full glass-chip rounded-[9px] py-[9px] text-[13px] font-semibold text-ledger-text-primary hover:bg-[#161a21] transition-colors disabled:opacity-50"
              >
                {testing ? 'Testing…' : 'Test connection'}
              </button>

              <div className="flex gap-[8px] mt-[6px]">
                <button
                  onClick={handleSkip}
                  disabled={skipping || saving}
                  className="flex-1 glass-chip rounded-[9px] py-[9px] text-[13px] font-semibold text-ledger-text-primary hover:bg-[#161a21] transition-colors disabled:opacity-50"
                >
                  {skipping ? 'Please wait…' : 'Skip for now'}
                </button>
                <button
                  onClick={handleFinish}
                  disabled={saving || skipping}
                  className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] text-[13px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? 'Saving…' : 'Finish'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
