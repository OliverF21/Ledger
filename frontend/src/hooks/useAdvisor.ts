import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../api/client'

export interface Proposal {
  id: number
  kind: string
  status: string
  source: string
  rationale: string | null
  payload: Record<string, unknown>
  undo: Record<string, unknown> | null
  superseded_by: number | null
  created_at: string | null
  applied_at: string | null
  summary: string
  category_name: string | null
  basis_limit: number | null
  proposed_limit: number | null
  month: string | null
}

export interface ApplyResult {
  success: boolean
  proposal_id: number
  kind?: string
  entity_id?: number | null
  summary?: string
  created: boolean
  budget_id?: number | null
  category_name?: string | null
  prev_limit?: number | null
  new_limit?: number | null
}

const POLL_MS = 30_000

/**
 * Pending AI advisor proposals. Follows the manual-refetch pattern used across
 * the app (see useInvestments) — no React Query. Polls every 30s so proposals
 * created from Claude appear without a manual refresh.
 */
export function useProposals(enabled: boolean = true) {
  const [pending, setPending] = useState<Proposal[]>([])
  const [history, setHistory] = useState<Proposal[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef(false)

  const refetch = useCallback(async () => {
    if (!enabled || inFlight.current) return
    inFlight.current = true
    try {
      // Fetch everything, then split: pending (queue) vs resolved (history).
      const res = await apiFetch('/api/proposals?status=all')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const all: Proposal[] = data.proposals ?? []
      setPending(all.filter(p => p.status === 'pending'))
      setHistory(all.filter(p => p.status !== 'pending'))
      setPendingCount(data.pending_count ?? all.filter(p => p.status === 'pending').length)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load proposals')
    } finally {
      setLoading(false)
      inFlight.current = false
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) return
    refetch()
    const id = window.setInterval(refetch, POLL_MS)
    return () => window.clearInterval(id)
  }, [enabled, refetch])

  const apply = useCallback(async (id: number): Promise<ApplyResult> => {
    const res = await apiFetch(`/api/proposals/${id}/apply`, { method: 'POST' })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.detail || `Apply failed (HTTP ${res.status})`)
    await refetch()
    return json as ApplyResult
  }, [refetch])

  const dismiss = useCallback(async (id: number): Promise<void> => {
    const res = await apiFetch(`/api/proposals/${id}/dismiss`, { method: 'POST' })
    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.detail || `Dismiss failed (HTTP ${res.status})`)
    }
    await refetch()
  }, [refetch])

  const undo = useCallback(async (id: number): Promise<void> => {
    const res = await apiFetch(`/api/proposals/${id}/undo`, { method: 'POST' })
    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.detail || `Undo failed (HTTP ${res.status})`)
    }
    await refetch()
  }, [refetch])

  return { pending, history, pendingCount, loading, error, refetch, apply, dismiss, undo }
}
