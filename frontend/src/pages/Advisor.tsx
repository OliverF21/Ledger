import { useState, useEffect, useRef } from 'react'
import { Sparkles, Check, X, Undo2, AlertCircle, Copy, KeyRound, RefreshCw } from 'lucide-react'
import type { useProposals } from '../hooks/useAdvisor'
import { getAdvisorConfig, generateAdvisorKey, type AdvisorConfig } from '../api/plaidConfig'

interface AdvisorProps {
  advisor: ReturnType<typeof useProposals>
}

function money(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

/** Read the ?proposal=<id> deep-link param (set by Claude's apply_url). */
function deepLinkedId(): number | null {
  const raw = new URLSearchParams(window.location.search).get('proposal')
  if (!raw) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  applied: { label: 'Applied', color: '#74d8a8' },
  dismissed: { label: 'Dismissed', color: '#9096a0' },
  undone: { label: 'Undone', color: '#e6bd79' },
  expired: { label: 'Expired', color: '#7a808c' },
  superseded: { label: 'Superseded', color: '#7a808c' },
}

function fmtWhen(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function Advisor({ advisor }: AdvisorProps) {
  const { pending, history, loading, error, apply, dismiss, undo } = advisor
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const highlightId = useRef<number | null>(deepLinkedId())
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({})

  // Scroll the deep-linked proposal into view once it's present in the list.
  useEffect(() => {
    const id = highlightId.current
    if (id && cardRefs.current[id]) {
      cardRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [pending])

  const run = async (id: number, fn: (id: number) => Promise<unknown>, label: string) => {
    setBusyId(id)
    setActionError(null)
    try {
      await fn(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : `${label} failed`)
    } finally {
      setBusyId(null)
    }
  }

  // ── AI Advisor (MCP) connection setup ──────────────────────────────────────
  const [cfg, setCfg] = useState<AdvisorConfig | null>(null)
  const [genLoading, setGenLoading] = useState(false)
  const [showSetup, setShowSetup] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  useEffect(() => {
    getAdvisorConfig().then(setCfg).catch(() => setCfg(null))
  }, [])

  const generateKey = async () => {
    setGenLoading(true)
    setActionError(null)
    try {
      const next = await generateAdvisorKey()
      setCfg(next)
      setShowSetup(true)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not generate a connection key')
    } finally {
      setGenLoading(false)
    }
  }

  const copy = async (text: string, which: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(which)
      setTimeout(() => setCopied(c => (c === which ? null : c)), 1500)
    } catch {
      /* clipboard unavailable — ignore */
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-[1000px]">
      {/* Intro */}
      <div className="glass-card p-[22px]">
        <div className="flex items-start gap-[14px]">
          <div className="icon-well w-[34px] h-[34px] rounded-lg flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-[18px] h-[18px]" strokeWidth={2} />
          </div>
          <div>
            <div className="text-[14px] font-semibold mb-[4px]">AI Advisor</div>
            <div className="text-[12.5px] text-ledger-text-faint leading-[1.5]">
              Suggestions you asked Claude for show up here as proposals. Nothing changes
              until you apply one — review the before → after and click Apply. Applied
              budgets land on Budgets, applied goals on the Goals tab, and applied labels
              show as named sinks on Cash Flow. You can undo from the history below.
            </div>
          </div>
        </div>
      </div>

      {actionError && (
        <div className="glass-card p-[14px] flex items-center gap-[10px] border border-[#f4907f]/40">
          <AlertCircle className="w-[16px] h-[16px] text-[#f4907f] flex-shrink-0" strokeWidth={2} />
          <span className="text-[12.5px] text-ledger-text-secondary">{actionError}</span>
        </div>
      )}

      {/* First-run setup: connect Claude Desktop to the advisor */}
      {cfg && !cfg.configured && (
        <div className="glass-card p-[22px]">
          <div className="flex items-center gap-[10px] mb-[10px]">
            <KeyRound className="w-[18px] h-[18px] text-white" strokeWidth={2} />
            <div className="text-[14px] font-semibold">Set up the AI Advisor</div>
          </div>
          <p className="text-[12.5px] text-ledger-text-faint leading-[1.5] mb-[14px]">
            The AI Advisor runs through Claude Desktop. Generate a connection key, add it to your
            Claude Desktop config, and Claude can propose budgets for you to approve here. The key
            only lets Claude <span className="text-ledger-text-secondary">suggest</span> changes —
            you always apply them yourself.
          </p>
          <button
            onClick={generateKey}
            disabled={genLoading}
            className="solid-cta rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] disabled:opacity-50"
          >
            {genLoading ? 'Generating…' : 'Generate connection key'}
          </button>
        </div>
      )}

      {cfg && cfg.configured && (
        <div className="glass-card p-[22px]">
          <button
            onClick={() => setShowSetup(s => !s)}
            className="flex items-center justify-between w-full"
          >
            <span className="flex items-center gap-[8px] text-[13px] font-semibold">
              <Check className="w-[16px] h-[16px] text-ledger-positive" strokeWidth={2.2} />
              AI Advisor connected
            </span>
            <span className="text-[12px] text-white/70">{showSetup ? 'Hide setup' : 'Show setup'}</span>
          </button>

          {showSetup && (
            <div className="mt-[16px] flex flex-col gap-[16px]">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-ledger-text-faint mb-[6px]">Connection key</div>
                <div className="flex items-center gap-[8px]">
                  <code className="glass-chip rounded-[8px] px-[12px] py-[8px] text-[12px] text-ledger-text-primary font-mono truncate flex-1">
                    {cfg.service_key}
                  </code>
                  <button
                    onClick={() => copy(cfg.service_key ?? '', 'key')}
                    className="glass-chip rounded-[8px] px-[10px] py-[8px] text-[12px] text-ledger-text-secondary hover:text-white transition-colors flex items-center gap-[5px]"
                  >
                    <Copy className="w-[13px] h-[13px]" strokeWidth={2} />
                    {copied === 'key' ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-[6px]">
                  <div className="text-[11px] uppercase tracking-wide text-ledger-text-faint">
                    Claude Desktop config
                  </div>
                  <button
                    onClick={() => copy(cfg.config_snippet, 'snippet')}
                    className="text-[12px] text-ledger-text-secondary hover:text-white transition-colors flex items-center gap-[5px]"
                  >
                    <Copy className="w-[13px] h-[13px]" strokeWidth={2} />
                    {copied === 'snippet' ? 'Copied' : 'Copy config'}
                  </button>
                </div>
                <pre className="glass-chip rounded-[8px] px-[12px] py-[10px] text-[11.5px] text-ledger-text-secondary font-mono overflow-auto max-h-[240px] leading-[1.5]">
{cfg.config_snippet}
                </pre>
              </div>

              <ol className="text-[12.5px] text-ledger-text-faint leading-[1.6] list-decimal pl-[18px] space-y-[2px]">
                <li>Paste the block above into your Claude Desktop <span className="font-mono text-ledger-text-secondary">claude_desktop_config.json</span>.</li>
                <li>Fully quit and reopen Claude Desktop.</li>
                <li>Ask Claude, e.g. “Am I overspending on dining? Propose a budget.” — its suggestions appear below.</li>
              </ol>

              <button
                onClick={generateKey}
                disabled={genLoading}
                className="self-start text-[12px] text-ledger-text-faint hover:text-ledger-negative transition-colors flex items-center gap-[6px] disabled:opacity-50"
              >
                <RefreshCw className="w-[13px] h-[13px]" strokeWidth={2} />
                {genLoading ? 'Regenerating…' : 'Regenerate key'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Pending queue */}
      <div className="flex flex-col gap-[14px]">
        <div className="text-[11px] uppercase tracking-widest text-ledger-text-faintest">Pending</div>
        {loading && pending.length === 0 ? (
          <div className="text-center py-10 text-ledger-text-faint text-[13px]">Loading…</div>
        ) : error ? (
          <div className="glass-card p-[20px] text-center text-[13px] text-ledger-text-faint">
            Couldn’t load proposals ({error}).
          </div>
        ) : pending.length === 0 ? (
          <div className="glass-card p-[36px] text-center">
            <Sparkles className="w-[24px] h-[24px] text-ledger-text-faint mx-auto mb-[10px]" strokeWidth={1.8} />
            <div className="text-[14px] font-semibold mb-[8px]">No pending suggestions</div>
            <div className="text-[13px] text-ledger-text-faint leading-[1.5]">
              Ask Claude about your budget (e.g. “Am I overspending on dining? Propose a budget.”).
              Its suggestions land here for you to review and apply.
            </div>
          </div>
        ) : (
          pending.map(p => {
            const isHighlighted = highlightId.current === p.id
            const hasBasis = p.basis_limit !== null && p.basis_limit !== undefined
            return (
              <div
                key={p.id}
                ref={el => { cardRefs.current[p.id] = el }}
                className={`glass-card p-[18px] transition-all ${isHighlighted ? 'ring-2 ring-white/50' : ''}`}
              >
                <div className="flex items-start gap-[14px]">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-[8px] mb-[8px]">
                      <span className="text-[10px] uppercase tracking-widest glass-chip px-[8px] py-[2px] rounded-[6px] text-ledger-text-muted">
                        Budget · {p.month}
                      </span>
                    </div>
                    <div className="flex items-baseline gap-[10px] mb-[10px] flex-wrap">
                      <span className="text-[15px] font-semibold">{p.category_name}</span>
                      {hasBasis && (
                        <>
                          <span className="text-[14px] text-ledger-text-faint line-through tabular-nums">
                            {money(p.basis_limit)}
                          </span>
                          <span className="text-ledger-text-faint">→</span>
                        </>
                      )}
                      <span className="text-[16px] font-bold text-white tabular-nums">
                        {money(p.proposed_limit)}
                      </span>
                    </div>
                    {p.rationale && (
                      <div className="text-[12.5px] text-ledger-text-faint leading-[1.5]">{p.rationale}</div>
                    )}
                  </div>
                  <div className="flex flex-col gap-[8px] flex-shrink-0">
                    <button
                      onClick={() => run(p.id, apply, 'Apply')}
                      disabled={busyId === p.id}
                      className="flex items-center justify-center gap-[6px] text-[12.5px] font-semibold px-[14px] py-[7px] rounded-[8px] solid-cta disabled:opacity-50"
                    >
                      <Check className="w-[14px] h-[14px]" strokeWidth={2.5} />
                      Apply
                    </button>
                    <button
                      onClick={() => run(p.id, dismiss, 'Dismiss')}
                      disabled={busyId === p.id}
                      className="flex items-center justify-center gap-[6px] text-[12.5px] px-[14px] py-[7px] rounded-[8px] glass-chip text-ledger-text-muted hover:text-ledger-text-heading transition-all disabled:opacity-50"
                    >
                      <X className="w-[14px] h-[14px]" strokeWidth={2} />
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* History */}
      {history.length > 0 && (
        <div className="flex flex-col gap-[10px]">
          <div className="text-[11px] uppercase tracking-widest text-ledger-text-faintest">History</div>
          {history.map(p => {
            const meta = STATUS_META[p.status] ?? { label: p.status, color: '#7a808c' }
            return (
              <div key={p.id} className="glass-card p-[14px] flex items-center gap-[12px]">
                <span
                  className="text-[10px] uppercase tracking-widest px-[8px] py-[2px] rounded-[6px] font-semibold whitespace-nowrap"
                  style={{ backgroundColor: `${meta.color}22`, color: meta.color }}
                >
                  {meta.label}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] text-ledger-text-secondary truncate">
                    {p.category_name} · {money(p.proposed_limit)}
                    <span className="text-ledger-text-faint"> · {p.month}</span>
                  </div>
                </div>
                <span className="text-[11px] text-ledger-text-faint whitespace-nowrap">
                  {fmtWhen(p.applied_at ?? p.created_at)}
                </span>
                {p.status === 'applied' && (
                  <button
                    onClick={() => run(p.id, undo, 'Undo')}
                    disabled={busyId === p.id}
                    className="flex items-center gap-[6px] text-[12px] px-[10px] py-[5px] rounded-[7px] glass-chip text-ledger-text-muted hover:text-ledger-text-heading transition-all disabled:opacity-50"
                  >
                    <Undo2 className="w-[13px] h-[13px]" strokeWidth={2} />
                    Undo
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
